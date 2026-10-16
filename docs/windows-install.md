# Windows 安装

支持 Windows x64、Python 3.12 x64、Windows PowerShell 5.1 或 PowerShell 7。应用不需要 Node.js；开发验证需要 Node.js 24。

## 首次使用

在 PowerShell 执行：

```powershell
git clone https://github.com/20triplexx-arch/document-rag-assistant.git
cd document-rag-assistant
.\setup.ps1
.\start.ps1
```

安装脚本创建独立 `.venv`，按原锁文件安装依赖，下载固定提交的默认216文件，建立索引并完整校验。安装过程不调用模型、不创建管理员或普通账号。完成后打开 <http://127.0.0.1:8765/>，在网页注册。

如 Python 不在 PATH：

```powershell
.\setup.ps1 -PythonPath 'C:\path\to\Python312\python.exe'
```

如系统禁止运行脚本，可仅对本次进程指定策略，不修改系统或用户级设置：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\start.ps1
```

若组织策略仍然禁止执行，安装会停止；不要修改组织策略。Python入口可用于诊断：`.\.venv\Scripts\python.exe starter.py doctor --json`。

## 模型配置

不设置密钥可以使用“只查原文”。需要生成讲解时，在启动服务的同一个终端设置：

```powershell
$env:DEEPSEEK_API_KEY = '你的 API Key'
.\start.ps1
```

程序不会自动读取 `.env`；完整配置项见 [示例](../.env.example)。诊断仅检查配置是否存在，不验证账户余额、网络或生成可用性。Pro/Max 继续禁用，百炼仍需要先确认免费保护。不要把密钥放入脚本或提交到 Git。

## 重复安装、失败与恢复

- 重复运行 `setup.ps1` 会复核并复用有效原文和索引，不覆盖账号或讨论。
- 下载按文件显示进度，缓存位于 `output/install-cache/`。失败时停止，不自动重试；重新运行复用已核对文件，只下载缺失项。
- 下载完成、索引建立且校验通过后才发布新快照。网络失败不会留下可误用的半套默认库。
- 缓存核对失败会给出具体缓存文件；保留故障记录后，可只删除被指出的缓存文件，再重新安装。不要删除整个 `data/` 或 `output/`。
- 缺少索引时可由安装脚本在原文校验后重建；已有索引或原文损坏时停止，不自动覆盖。应恢复可信备份或使用另一份干净克隆核对。
- 已有 `.venv` 的 Python 版本或架构不符时不会被替换。请在另一个目录重新克隆，并显式选择 Python 3.12 x64。
- pip安装失败会返回非零退出码；先解决日志中的网络或依赖问题，再重新运行，不要先启动应用。
- `setup.ps1 -SkipCorpus` 仅准备依赖，明确不代表教材或完整安装通过；供 CI 和维护使用。

## 检查与启停

```powershell
.\.venv\Scripts\python.exe starter.py doctor --json
.\background.ps1
.\stop.ps1
```

前台、后台和停止脚本共用端口顺序：显式 `-Port`，然后 `RAG_PORT`，最后8765。始终只绑定127.0.0.1。端口被占用时不会停止其他进程；可用 `-Port 8766` 换端口。

后台启动最长等待90秒，只有核对进程归属和真实资料接口后才报告成功。失败时检查 `output/server-*.stderr.log`；超时未强杀进程，可使用相同端口的停止脚本检查并停止。正在生成时停止脚本会拒绝中断。脚本不会自动打开浏览器或创建管理员。

## 开发验证

```powershell
.\verify.ps1                    # App：代码、前端、默认库及默认题集静态校验
.\verify.ps1 -Profile Code      # 无教材也可执行；用于每次提交的 CI
.\verify.ps1 -Profile Research  # 额外严格检查301/2164候选快照；缺失即失败
```

所有验证均不调用真实模型。可选向量测试在没有相应依赖时明确列为 skipped；不会据此宣称向量功能通过。Research 校验不运行冻结题生成或检索调参。

GitHub 的 Windows checks 自动执行离线 Code 检查；Windows full installation 需手动触发，执行真实公开教材安装、重复安装、App验证及隔离账号的回环HTTP测试。不会向工作流提供模型密钥。

本轮结果：[全新安装验收](windows-install-validation-2026-10-16.md) · [已有环境保全](windows-install-preservation-2026-10-16.md)。
