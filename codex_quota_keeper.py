#!/usr/bin/env python3

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo


TIMEZONE_NAME = os.environ.get("CODEX_QUOTA_TIMEZONE", "Asia/Shanghai")
TIMEZONE = ZoneInfo(TIMEZONE_NAME)


def format_usage(value):
    """使用全角字符显示百分比，个位数用全角空格补齐。"""
    if value is None:
        return "暂未获取"
    text = f"{value:>2}%"
    return text.translate(str.maketrans("0123456789.% ", "０１２３４５６７８９．％　"))


def format_reset(value):
    """日期有意保留半角数字，便于复制和识别。"""
    if value is None:
        return "暂未获取"
    return datetime.fromtimestamp(float(value), TIMEZONE).strftime("%m-%d %H:%M")


def bark_url():
    value = os.environ.get("BARK_URL")
    if value:
        return value.strip().rstrip("/")

    path = Path(
        os.environ.get(
            "BARK_URL_FILE",
            "~/.config/codex-quota-keeper/bark-url",
        )
    ).expanduser()
    try:
        return path.read_text(encoding="utf-8").strip().rstrip("/")
    except FileNotFoundError:
        return ""


def notify_refresh_success(info):
    """仅在确认新窗口后发送；推送失败不影响额度状态。"""
    try:
        base = bark_url()
    except Exception as e:
        log(f'WARNING: Bark 配置读取失败（{type(e).__name__}）')
        return False

    if not base:
        return False

    try:
        weekly = info.get('weekly') or {}
        title = '✅ Codex 额度刷新成功'
        body = (
            f"５小时 · 已用 {format_usage(info.get('used_percent'))} · {format_reset(info.get('reset_at'))}\n"
            f"周额度 · 已用 {format_usage(weekly.get('used_percent'))} · {format_reset(weekly.get('reset_at'))}"
        )
        url = base + '/' + quote(title, safe='') + '/' + quote(body, safe='')
        url += '?' + urlencode({
            'group': os.environ.get('BARK_GROUP', 'codex-quota'),
            'ttl': 600,
            'isArchive': 1,
            'icon': 'https://raw.githubusercontent.com/lobehub/lobe-icons/8a1b2821bb768c484fe8da20c5e1838b6bf551a9/packages/static-png/light/codex-color.png',
        })
        with urlopen(url, timeout=10) as response:
            result = json.load(response)
        if result.get('code') != 200:
            raise RuntimeError('Bark 返回非成功状态')
        log('SUCCESS: 额度刷新 Bark 通知已被服务端接受')
        return True
    except Exception as e:
        # 不记录异常原文，避免 URL 中的推送密钥泄露到日志。
        log(f'WARNING: 额度刷新 Bark 通知失败（{type(e).__name__}）')
        return False


# ============================================================
# 配置
# ============================================================

# 默认从 PATH 查找；定时任务可用 CODEX_BIN 指定完整路径
CODEX = os.environ.get("CODEX_BIN") or shutil.which("codex") or "codex"

STATE_FILE = Path(
    os.environ.get(
        "CODEX_QUOTA_STATE_FILE",
        "~/.local/state/codex-quota-keeper/state.json",
    )
).expanduser()
LOG_FILE = Path(
    os.environ.get(
        "CODEX_QUOTA_LOG_FILE",
        "~/.local/state/codex-quota-keeper/keeper.log",
    )
).expanduser()

# reset 后至少等多少秒再激活
RESET_GRACE_SECONDS = 30

# 激活后等多久再查询额度
VERIFY_DELAY_SECONDS = 15

# 查询 app-server 超时
QUERY_TIMEOUT_SECONDS = 15

# Codex 激活任务超时
ACTIVATE_TIMEOUT_SECONDS = 120

# 防止异常情况下短时间连续激活
MIN_ACTIVATION_INTERVAL = 300

# 激活 Codex 的轻量任务
ACTIVATE_PROMPT = (
    "Reply with exactly OK. "
    "Do not read files. "
    "Do not use tools. "
    "Do not modify anything."
)


# ============================================================
# 日志
# ============================================================

def log(message):
    now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    line = f"[{now} {TIMEZONE_NAME}] {message}"

    print(line, flush=True)

    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        LOG_FILE.chmod(0o600)
    except Exception:
        pass


# ============================================================
# 时间格式
# ============================================================

def format_ts(ts):

    if not ts:
        return "UNKNOWN"

    try:
        return datetime.fromtimestamp(
            float(ts),
            TIMEZONE
        ).strftime("%Y-%m-%d %H:%M:%S")

    except Exception:
        return str(ts)


# ============================================================
# JSON 状态
# ============================================================

def default_state():

    return {
        "last_check_at": None,

        "last_successful_check_at": None,

        "reset_at": None,

        "used_percent": None,

        "window_minutes": None,

        "last_activation_at": None,

        "last_activation_reason": None,

        "last_activation_success": None,

        "last_error": None
    }


def load_state():

    if not STATE_FILE.exists():
        return default_state()

    try:

        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        state = default_state()

        state.update(data)

        return state

    except Exception as e:

        log(f"WARNING: 状态文件读取失败: {e}")

        return default_state()


def save_state(state):

    temp_file = STATE_FILE.with_suffix(".tmp")

    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        temp_file.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )
        temp_file.chmod(0o600)

        os.replace(temp_file, STATE_FILE)

    except Exception as e:

        log(f"ERROR: 状态文件写入失败: {e}")


# ============================================================
# Codex app-server 查询
# ============================================================

def get_rate_limits():

    """
    使用：

        codex app-server --listen stdio://

    调用：

        account/rateLimits/read

    查找 windowDurationMins ≈ 300 的窗口。

    返回：

    {
        "used_percent": 20,
        "reset_at": 1234567890,
        "window_minutes": 300
    }

    如果没有找到 5h 窗口：
        return None
    """

    proc = None

    try:

        proc = subprocess.Popen(
            [
                CODEX,
                "app-server",
                "--listen",
                "stdio://"
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1
        )

        # ----------------------------------------------------
        # initialize
        # ----------------------------------------------------

        initialize = {
            "id": 1,
            "method": "initialize",
            "params": {
                "clientInfo": {
                    "name": "codex-quota-keeper",
                    "version": "1.0"
                }
            }
        }

        proc.stdin.write(
            json.dumps(initialize) + "\n"
        )

        proc.stdin.flush()

        # ----------------------------------------------------
        # initialized
        # ----------------------------------------------------

        initialized = {
            "method": "initialized",
            "params": {}
        }

        proc.stdin.write(
            json.dumps(initialized) + "\n"
        )

        proc.stdin.flush()

        # ----------------------------------------------------
        # rate limits
        # ----------------------------------------------------

        request = {
            "id": 2,
            "method": "account/rateLimits/read",
            "params": {}
        }

        proc.stdin.write(
            json.dumps(request) + "\n"
        )

        proc.stdin.flush()

        deadline = (
            time.time()
            + QUERY_TIMEOUT_SECONDS
        )

        # ----------------------------------------------------
        # 读取结果
        # ----------------------------------------------------

        while time.time() < deadline:

            line = proc.stdout.readline()

            if not line:
                time.sleep(0.1)
                continue

            try:
                data = json.loads(line)

            except json.JSONDecodeError:
                continue

            if data.get("id") != 2:
                continue

            # RPC error
            if "error" in data:

                raise RuntimeError(
                    f"Codex RPC error: {data['error']}"
                )

            result = data.get("result", {})

            candidates = []

            # =================================================
            # 结构1：
            #
            # rateLimitsByLimitId
            # =================================================

            by_id = result.get(
                "rateLimitsByLimitId",
                {}
            )

            if isinstance(by_id, dict):

                for limit_id, group in by_id.items():

                    if not isinstance(group, dict):
                        continue

                    for key in (
                        "primary",
                        "secondary"
                    ):

                        window = group.get(key)

                        if isinstance(window, dict):

                            candidates.append(
                                (
                                    limit_id,
                                    key,
                                    window
                                )
                            )

            # =================================================
            # 结构2：
            #
            # rateLimits
            # =================================================

            limits = result.get(
                "rateLimits",
                {}
            )

            if isinstance(limits, dict):

                for key in (
                    "primary",
                    "secondary"
                ):

                    window = limits.get(key)

                    if isinstance(window, dict):

                        candidates.append(
                            (
                                "default",
                                key,
                                window
                            )
                        )

            # =================================================
            # 找 5h = 300min
            # =================================================

            for limit_id, slot, window in candidates:

                duration = window.get(
                    "windowDurationMins"
                )

                if duration is None:
                    continue

                try:
                    duration = int(duration)

                except Exception:
                    continue

                # 给接口变化留一点容差
                if not 280 <= duration <= 320:
                    continue

                reset_at = window.get(
                    "resetsAt"
                )

                used_percent = window.get(
                    "usedPercent"
                )

                if reset_at is not None:

                    try:
                        reset_at = float(
                            reset_at
                        )

                    except Exception:
                        reset_at = None

                weekly = None
                for week_id, _, week_window in candidates:
                    if week_id != limit_id:
                        continue
                    try:
                        if int(week_window.get('windowDurationMins')) != 10080:
                            continue
                        week_reset = week_window.get('resetsAt')
                        weekly = {
                            'used_percent': week_window.get('usedPercent'),
                            'reset_at': float(week_reset) if week_reset is not None else None,
                            'window_minutes': 10080,
                        }
                        break
                    except (TypeError, ValueError):
                        continue

                return {
                    "weekly": weekly,
                    "limit_id": limit_id,

                    "slot": slot,

                    "used_percent":
                        used_percent,

                    "reset_at":
                        reset_at,

                    "window_minutes":
                        duration
                }

            return None

        raise TimeoutError(
            "Codex rate limits 查询超时"
        )

    finally:

        if proc:

            try:
                proc.terminate()

                proc.wait(timeout=3)

            except Exception:

                try:
                    proc.kill()

                except Exception:
                    pass


# ============================================================
# 激活 Codex
# ============================================================

def activate_codex(reason):

    log(
        f"准备激活 Codex，reason={reason}"
    )

    try:

        result = subprocess.run(
            [
                CODEX,

                "exec",

                "--skip-git-repo-check",

                ACTIVATE_PROMPT
            ],

            stdout=subprocess.PIPE,

            stderr=subprocess.STDOUT,

            text=True,

            timeout=ACTIVATE_TIMEOUT_SECONDS
        )

        output = (
            result.stdout
            .strip()
            .replace("\n", " ")
        )

        log(
            f"Codex 请求结束 "
            f"exit={result.returncode} "
            f"output={output[:200]}"
        )

        return (
            result.returncode == 0
        )

    except subprocess.TimeoutExpired:

        log(
            "ERROR: Codex 激活请求超时"
        )

        return False

    except Exception as e:

        log(
            f"ERROR: Codex 激活异常: {e}"
        )

        return False


# ============================================================
# 更新查询结果
# ============================================================

def update_state_from_info(
    state,
    info
):

    now = int(time.time())

    state[
        "last_check_at"
    ] = now

    if not info:
        return

    state[
        "last_successful_check_at"
    ] = now

    state[
        "reset_at"
    ] = info.get(
        "reset_at"
    )

    state[
        "used_percent"
    ] = info.get(
        "used_percent"
    )

    state[
        "window_minutes"
    ] = info.get(
        "window_minutes"
    )

    state[
        "last_error"
    ] = None


# ============================================================
# 激活后二次验证
# ============================================================

def verify_after_activation(
    state,
    old_reset
):

    log(
        f"等待 {VERIFY_DELAY_SECONDS}s "
        f"后验证新窗口..."
    )

    time.sleep(
        VERIFY_DELAY_SECONDS
    )

    try:

        info = get_rate_limits()

    except Exception as e:

        log(
            f"WARNING: 激活后二次查询失败: {e}"
        )

        state[
            "last_error"
        ] = str(e)

        save_state(state)

        return False

    if not info:

        log(
            "WARNING: 激活后没有检测到 "
            "5H 窗口"
        )

        save_state(state)

        return False

    update_state_from_info(
        state,
        info
    )

    new_reset = info.get(
        "reset_at"
    )

    log(
        "激活后状态: "
        f"used={info.get('used_percent')}% "
        f"reset={format_ts(new_reset)}"
    )

    success = False

    try:
        numeric_used = float(info.get("used_percent"))
        numeric_reset = float(new_reset)
        reset_advanced = (
            old_reset is None
            or
            numeric_reset >= float(old_reset) + 60
        )
        success = (
            numeric_used > 0
            and
            numeric_reset > time.time()
            and
            reset_advanced
        )
    except (TypeError, ValueError):
        success = False

    # 小请求可能仍显示 0%，此时必须再隔 15 秒确认 reset 固定，
    # 不能把闲置接口“当前时间 + 5h”的滚动值误认成新窗口。
    if not success and info.get("used_percent") == 0:
        sampled_at = time.time()
        time.sleep(VERIFY_DELAY_SECONDS)
        try:
            second = get_rate_limits()
            if not second or new_reset is None:
                raise ValueError("missing verification window")
            second_reset = float(second["reset_at"])
            second_used = float(second["used_percent"])
            success = (
                time.time() - sampled_at >= 10
                and second_used >= 0
                and second_reset > time.time()
                and (old_reset is None or second_reset >= float(old_reset) + 60)
                and abs(second_reset - float(new_reset)) <= 5
            )
            if success:
                info = second
                update_state_from_info(state, info)
        except (TypeError, ValueError, KeyError, RuntimeError, OSError):
            success = False

    if not success:
        state["reset_at"] = old_reset
        state["last_error"] = "activation_window_not_confirmed"

    state[
        "last_activation_success"
    ] = success

    save_state(state)

    if success:

        log(
            "SUCCESS: 新 5H 窗口确认成功"
        )
        notify_refresh_success(info)

    else:

        log(
            "WARNING: Codex 请求成功，"
            "但未确认 reset 时间变化"
        )

    return success


# ============================================================
# 主程序
# ============================================================

def main():

    now = time.time()

    state = load_state()

    local_reset_at = state.get(
        "reset_at"
    )

    state[
        "last_check_at"
    ] = int(now)

    # ========================================================
    # 1. 查询真实 Codex 额度
    # ========================================================

    try:

        info = get_rate_limits()

    except Exception as e:

        log(
            f"ERROR: 查询 Codex 额度失败: {e}"
        )

        state[
            "last_error"
        ] = str(e)

        save_state(state)

        # 查询失败绝对不要瞎激活
        return 1

    # ========================================================
    # 2. 没有找到 5H 窗口
    # ========================================================

    if not info:

        log(
            "WARNING: 当前没有检测到 "
            "5H Codex 窗口"
        )

        state[
            "last_error"
        ] = "5h_window_not_found"

        save_state(state)

        # 不确定状态下不要乱发请求
        return 0

    # ========================================================
    # 3. 更新 JSON
    # ========================================================

    update_state_from_info(
        state,
        info
    )

    observed_reset_at = info.get("reset_at")
    used = info.get("used_percent")

    try:
        numeric_used = float(used)
    except (TypeError, ValueError):
        numeric_used = None

    manual_new_window = False

    if (
        numeric_used is not None
        and
        numeric_used > 0
        and
        local_reset_at is not None
        and
        observed_reset_at is not None
    ):
        try:
            manual_new_window = (
                float(observed_reset_at) > now
                and
                float(observed_reset_at) >= float(local_reset_at) + 60
            )
        except (TypeError, ValueError):
            manual_new_window = False

    # 闲置窗口的接口 reset 会不断滚到未来，不能覆盖本地保存的
    # 实际 deadline；有用量时也只接受明确前进的新窗口。
    if (
        numeric_used == 0
        or
        (
            local_reset_at is not None
            and
            not manual_new_window
        )
    ):
        state["reset_at"] = local_reset_at

    save_state(state)

    reset_at = state.get(
        "reset_at"
    )

    log(
        f"Codex 5H: "
        f"used={used}% "
        f"reset={format_ts(reset_at)}"
    )

    # ========================================================
    # 4. reset_at 不存在
    # ========================================================

    if not reset_at:

        if used == 0:
            activation_reason = "initial_idle_window"
            old_reset = None
            log(
                "首次检测到闲置窗口，"
                "执行一次轻量激活"
            )
        else:
            log(
                "WARNING: 没有 reset_at，"
                "本次不执行激活"
            )

            return 0

    # ========================================================
    # 5. 窗口还没有 reset
    # ========================================================

    else:
        activate_after = (
            reset_at
            + RESET_GRACE_SECONDS
        )

        if now < activate_after:

            remaining = int(
                activate_after
                - now
            )

            log(
                f"窗口仍有效，"
                f"距离可激活约 {remaining}s"
            )

            return 0

        # ====================================================
        # 6. 已经过 reset 时间
        # ====================================================

        log(
            "检测到 5H 窗口已经到期"
        )
        activation_reason = "5h_reset_reached"
        old_reset = reset_at

    # ========================================================
    # 7. 防止重复激活
    # ========================================================

    last_activation = state.get(
        "last_activation_at"
    )

    if last_activation:

        since = (
            now
            - float(last_activation)
        )

        if (
            since
            < MIN_ACTIVATION_INTERVAL
        ):

            log(
                "距离上次激活不足 "
                f"{MIN_ACTIVATION_INTERVAL}s，"
                "跳过"
            )

            return 0

    # ========================================================
    # 8. 激活
    # ========================================================

    success = activate_codex(
        activation_reason
    )

    state[
        "last_activation_at"
    ] = int(time.time())

    state[
        "last_activation_reason"
    ] = activation_reason

    state[
        "last_activation_success"
    ] = success

    save_state(state)

    # ========================================================
    # 9. Codex exec 本身失败
    # ========================================================

    if not success:

        log(
            "ERROR: Codex 激活请求失败"
        )

        return 1

    # ========================================================
    # 10. 二次验证
    # ========================================================

    verified = verify_after_activation(
        state,
        old_reset
    )

    return 0 if verified else 1


if __name__ == "__main__":

    sys.exit(
        main()
    )
