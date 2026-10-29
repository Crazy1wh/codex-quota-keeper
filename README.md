# codex-quota-keeper

一个小型定时脚本：读取已登录 Codex CLI 的 5 小时额度窗口，在窗口到期后发起一次轻量真实请求，并再次查询额度，只有确认新窗口已建立时才可选发送 Bark 通知。

> **重要：本项目不会增加、绕过或恢复任何额度。真实激活请求本身会消耗 Codex 额度，也可能产生与账户方案相关的费用。** 请遵守 OpenAI、Bark 和所在地区的条款、政策与法律，自行评估自动化调用是否适合你的账户。

## 要求与安装

- Python 3.10 或更高版本（只使用标准库）
- 已安装 Codex CLI，并已在运行脚本的同一用户下完成登录
- 可选：Bark 推送地址

```bash
git clone https://github.com/Crazy1wh/codex-quota-keeper.git
cd codex-quota-keeper
python3 -m unittest discover -s tests -v
python3 -m compileall -q codex_quota_keeper.py tests
```

先手动运行一次以检查配置。注意：满足激活条件时，这会执行真实 Codex 请求并消耗额度。

```bash
python3 codex_quota_keeper.py
```

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CODEX_BIN` | 从 `PATH` 查找 `codex` | Codex CLI 可执行文件；cron 中建议使用绝对路径 |
| `CODEX_QUOTA_STATE_FILE` | `~/.local/state/codex-quota-keeper/state.json` | 状态文件路径 |
| `CODEX_QUOTA_LOG_FILE` | `~/.local/state/codex-quota-keeper/keeper.log` | 日志文件路径 |
| `CODEX_QUOTA_TIMEZONE` | `Asia/Shanghai` | IANA 时区名 |
| `BARK_URL` | 未设置 | 完整 Bark 基础地址；设置后优先于文件 |
| `BARK_URL_FILE` | `~/.config/codex-quota-keeper/bark-url` | 保存 Bark 地址的私有文件 |
| `BARK_GROUP` | `codex-quota` | Bark 通知分组 |

Bark 未配置或配置文件不存在时，脚本会静默跳过通知。通知保留 `ttl=600` 和 `isArchive=1`。用量百分比使用全角字符，日期时间使用半角数字。

通知示例（示例数据，不代表真实账户）：

```text
✅ Codex 额度刷新成功
５小时 · 已用 　０％ · 10-29 10:00
周额度 · 已用 ３１％ · 11-04 14:44
```

Bark 系统通知不能由本脚本指定等宽字体；全角字符只能改善对齐，100% 或缺失值也会改变列宽。图标引用 LobeHub lobe-icons 的公开资源，未在本仓库分发图标文件。

### 已知限制

- 依赖 Codex CLI 的 `app-server` 返回结构，CLI 升级后可能需要适配。
- 查询循环的超时不能打断底层阻塞读取；无人值守运行建议加外层 `timeout`（例如在 cron 命令的 Python 前添加 `/usr/bin/timeout 240s`）。
- 请勿绕过 `flock` 同时运行多个实例；脚本本身没有进程锁。


建议把含 Bark 密钥的文件设为仅本人可读写：

```bash
mkdir -p ~/.config/codex-quota-keeper
printf '%s\n' 'https://api.day.app/YOUR_PRIVATE_KEY' > ~/.config/codex-quota-keeper/bark-url
chmod 600 ~/.config/codex-quota-keeper/bark-url
chmod 600 ~/.local/state/codex-quota-keeper/state.json 2>/dev/null || true
```

不要把 Bark URL、状态文件或日志提交到版本库，也不要把它们发给他人。

## cron 示例

先用 `command -v python3` 和 `command -v codex` 找到真实绝对路径，再替换下面所有 `/ABSOLUTE/PATH/...` 占位符。`flock` 防止上一次任务未结束时重复运行。

```cron
*/5 * * * * /usr/bin/flock -n /ABSOLUTE/PATH/TO/codex-quota-keeper.lock /usr/bin/env CODEX_BIN=/ABSOLUTE/PATH/TO/codex CODEX_QUOTA_STATE_FILE=/ABSOLUTE/PATH/TO/state.json CODEX_QUOTA_LOG_FILE=/ABSOLUTE/PATH/TO/keeper.log /ABSOLUTE/PATH/TO/python3 /ABSOLUTE/PATH/TO/codex-quota-keeper/codex_quota_keeper.py
```

cron 必须以已登录 Codex CLI 的用户运行。状态和日志的父目录会由脚本自动创建。

## 工作方式与隐私

脚本通过本机 Codex CLI 的 `app-server` 查询额度；到期后运行一次受限提示词的 `codex exec`，随后重新查询并验证 reset 时间确实前进。仅在确认成功后发送 Bark，推送失败不会撤销或破坏已经保存的成功状态。

状态文件和日志保存在本机，但可能包含额度、时间、错误信息和命令输出摘要。Bark 开启后，通知内容会发送给你配置的 Bark 服务；脚本还会在通知参数中引用公开图标 URL。请审阅代码、保护私有文件，并根据你的隐私要求决定是否启用通知。

本项目与 OpenAI、Codex 或 Bark **无隶属、授权或背书关系**。使用者负责账户安全、费用、服务条款合规、自动化频率和运行环境安全。

## 许可证

[MIT](LICENSE)
