# Agent 安装与维护指南

本文件供有用户本机终端权限的 AI Agent 使用。目标是代用户完成配置，而不是把全部命令再交给用户执行。仅处理本项目，不修改其他服务。

## 安全边界

- 本项目不增加或绕过额度。启用后会定期检查，到期时运行一次真实 `codex exec`，消耗账户额度。启用定时任务前告知用户并取得确认；用户已明确授权时不重复询问。
- 不读取、打印、复制或上传 Codex 登录凭据。登录状态用 `codex login status` 检查；未登录时由用户通过 CLI 官方交互登录流程完成。
- 不把 Bark URL、密钥、真实状态或日志写入仓库、聊天记录或提交。优先请用户在本机私有文件中配置 Bark，Agent 只检查是否存在和权限，不展示内容。
- 不执行下载即运行的未知脚本，不擅自安装系统软件、使用 sudo 或修改全局环境。缺依赖时说明并征得安装授权。
- 不直接运行 `python3 codex_quota_keeper.py` 当作无副作用的配置检查：它可能立即激活。真实端到端测试和测试推送均需明确授权；测试通知必须标注“预览/测试”。

## 1. 发现环境与取得源码

1. 确认当前用户、HOME、系统和 shell；以完成 Codex 登录的同一用户部署，不默认使用 root。
2. 选择用户可写的独立目录（例如 `~/apps/codex-quota-keeper`）。已有仓库先检查远端、分支和工作区，不覆盖本地改动、不强制重置。
3. 没有源码时克隆 `https://github.com/Crazy1wh/codex-quota-keeper.git`，然后读取 README 和本文件。
4. 用 `command -v python3`、`python3 --version`、`command -v codex`、`codex login status` 检查依赖；需要 Python 3.10+ 和可用时区数据库。记录可执行文件绝对路径，确认 cron 环境中 Codex 的解释器（如 Node.js）也能从 PATH 找到。
5. Linux 默认采用用户 crontab，检查 `crontab`、`flock`、`timeout` 和 cron 服务是否可用。其他系统或无 cron 的环境先说明差异，提出其原生调度方案，不照搬 Linux 命令。

## 2. 私有配置

默认路径与环境变量以 README 和源码为准：

- 状态、日志：`~/.local/state/codex-quota-keeper/`。
- Bark 地址文件：`~/.config/codex-quota-keeper/bark-url`；缺失时不启用推送，不必阻塞安装。
- 时区默认 `Asia/Shanghai`，用户指定其他时区时改为对应 IANA 名称。

创建所需私有目录（权限 0700）。Bark 文件权限应为 0600，不覆盖已有内容。状态和日志不放到源码仓库；不要复制任何现有真实数据到仓库。用 `umask 077` 创建新增私有文件。

建议生成私有启动脚本 `~/.config/codex-quota-keeper/run.sh`（0700），明确设置 HOME、PATH、CODEX_BIN、CODEX_QUOTA_STATE_FILE、CODEX_QUOTA_LOG_FILE、CODEX_QUOTA_TIMEZONE、BARK_URL_FILE、BARK_GROUP。路径必须来自当前机器实际发现的结果，使用正确的 shell 引号，不拼接用户输入为可执行代码。

启动脚本最后通过实际找到的绝对路径执行以下结构（尖括号均为待替换项，不能原样写入）：

```sh
exec <flock绝对路径> -n <私有状态目录>/keeper.lock <timeout绝对路径> 240s <python3绝对路径> <仓库绝对路径>/codex_quota_keeper.py
```

PATH 必须包含 Codex 的运行时解释器目录和所需系统命令目录；不能只设置 Codex 的绝对路径却漏掉其 shebang 依赖。不要在启动脚本中复制 Bark 密钥，引用 BARK_URL_FILE 即可。

## 3. 离线验证

在源码目录执行：

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q codex_quota_keeper.py tests
```

另外验证启动脚本 shell 语法、路径和权限，但不要执行它。可以导入模块检查配置解析；不要调用 `main()`、`get_rate_limits()` 或 `activate_codex()` 进行所谓离线测试。

离线测试不能证明真实账户激活和手机收到通知；最终报告必须区分这些结果。

## 4. 启用定时任务（需授权）

1. 先读取当前用户 crontab。若命令失败，区分“无 crontab”和权限/服务错误，后者不得作为空表覆盖。
2. 查找本项目已有任务及旧部署，避免同一账户重复运行。无法确定旧任务用途时先询问，不删除无关条目。
3. 私下备份原 crontab（0600，不输出可能包含的其他密钥），保留所有无关行，只新增/更新一条带 `# codex-quota-keeper` 标记的每 5 分钟任务。
4. cron 调用私有启动脚本绝对路径。路径含空格需引用；cron 中的 `%` 具有特殊含义，应避免出现在任务命令里，复杂设置放启动脚本。
5. 标准输出与错误输出重定向到私有目录的 `cron.log`，不要与脚本内部 `keeper.log` 使用相同文件，避免重复记录。启用前以 0600 创建 cron.log。
6. 写入后重新读取 crontab，核对任务只存在一条、路径正确、无关行未改变；重新检查 cron 服务状态。
7. 不为验证而额外手动执行激活。若用户同意真实测试，记录实际结果；Bark 返回成功仅表示服务端接受，手机展示及历史保存需用户确认。

## 5. 交付与停用

交付短报告：源码目录、私有启动脚本、状态/日志位置、调度频率与时区、Bark 是否启用、离线测试结果、是否做过真实测试、未解决的问题。不要输出密钥或账户身份信息。

停用时备份并编辑用户 crontab，只移除本项目标记行，读回确认；保留状态和配置，除非用户明确要求删除。不要用 `crontab -r`，不要停止全局 cron 服务。

## 维护代码

改动前检查 Git 状态并创建分支；保留用户确认的“全角用量、半角时间”通知布局。新增测试时 mock 外部进程、网络与睡眠，禁止使用真实账户或发送真实推送。发布前审查差异、扫描凭据并运行测试。不因文档更新修改部署任务或真实运行状态。
