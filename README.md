# ⏱️ Codex Quota Keeper

自动检查 Codex 额度窗口，到期后轻量激活，确认成功再发 Bark 通知。

🐍 Python 标准库 · 🤖 Agent 配置 · 🔔 Bark 推送 · 📄 MIT

> ⚠️ 不增加或绕过额度；激活会发出真实 Codex 请求并消耗额度。

## 🤖 交给 Agent 安装

复制给有本机终端权限的 Codex、Claude Code 或 Hermes：

```text
帮我部署 https://github.com/Crazy1wh/codex-quota-keeper 。
读取 README.md 和 AGENTS.md，自动检查依赖、登录状态并配置每 5 分钟检查。
Bark 可选；启用定时任务前向我确认额度消耗，真实测试另行确认。
不要展示凭据、覆盖其他任务。完成后报告验证结果和停用方法。
```

你只需完成 Codex 登录、确认启用；其余按 [AGENTS.md](AGENTS.md) 执行。

## 🔔 通知效果

```text
✅ Codex 额度刷新成功
５小时 · 已用 　０％ · 10-29 10:00
周额度 · 已用 ３１％ · 11-04 14:44
```

示例数据。全角用量、半角时间；确认新窗口才推送，普通检查不打扰。

## 🛠️ 手动安装

需要 Python 3.10+、时区数据库，以及同一用户下已登录的 Codex CLI。

```bash
git clone https://github.com/Crazy1wh/codex-quota-keeper.git
cd codex-quota-keeper
python3 -m unittest discover -s tests -v
python3 codex_quota_keeper.py  # 满足条件时会执行真实激活
```

<details>
<summary>🔔 配置 Bark（可选）</summary>

不配置则跳过通知。将完整 Bark 地址保存在仓库外的私有文件：

```bash
umask 077
mkdir -p ~/.config/codex-quota-keeper
printf '%s\n' 'https://api.day.app/YOUR_PRIVATE_KEY' > ~/.config/codex-quota-keeper/bark-url
chmod 600 ~/.config/codex-quota-keeper/bark-url
```

已有配置请勿覆盖。通知使用 `isArchive=1`、`ttl=600`；图标引用 LobeHub lobe-icons 公开资源。

</details>

<details>
<summary>⚙️ 环境变量</summary>

| 变量 | 默认值 / 用途 |
| --- | --- |
| `CODEX_BIN` | 从 PATH 查找 `codex` |
| `CODEX_QUOTA_STATE_FILE` | `~/.local/state/codex-quota-keeper/state.json` |
| `CODEX_QUOTA_LOG_FILE` | `~/.local/state/codex-quota-keeper/keeper.log` |
| `CODEX_QUOTA_TIMEZONE` | `Asia/Shanghai` |
| `BARK_URL` | 完整推送地址，优先于文件 |
| `BARK_URL_FILE` | `~/.config/codex-quota-keeper/bark-url` |
| `BARK_GROUP` | `codex-quota` |

状态与日志目录自动创建，敏感配置不要提交到 Git。

</details>

<details>
<summary>🕒 Linux 定时运行</summary>

用 `command -v python3 codex flock timeout` 查找路径，替换以下占位符；先创建可写的锁文件目录。

```cron
*/5 * * * * /usr/bin/flock -n /ABSOLUTE/PATH/TO/keeper.lock /usr/bin/env CODEX_BIN=/ABSOLUTE/PATH/TO/codex /usr/bin/timeout 240s /ABSOLUTE/PATH/TO/python3 /ABSOLUTE/PATH/TO/codex-quota-keeper/codex_quota_keeper.py
```

以已登录 Codex 的用户运行，并确保 cron 的 PATH 能找到 Codex 所需的 Node.js 等运行时。不要重复添加任务。停用时只移除本项目任务，不要使用 `crontab -r`。

</details>

## 📌 注意事项

- 通过本机 Codex CLI 查询与激活；CLI 接口变化可能需要适配。
- 用 `flock` 防并发、`timeout` 防阻塞；完整部署流程见 [AGENTS.md](AGENTS.md)。
- 本地日志可能包含命令输出；启用 Bark 后额度与时间会发送到配置的推送服务。
- 系统字体无法保证严格对齐，100% 或缺失值会改变列宽。
- 非 OpenAI / Bark 官方项目；使用者自行遵守服务条款并承担费用。

## 📄 开源协议

[MIT License](LICENSE)
