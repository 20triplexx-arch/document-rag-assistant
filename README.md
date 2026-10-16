# 学有据

面向 Agent 学习的本地 RAG 问答助手，结合课程和实战案例回答问题，并提供可核对的原文引用。

## 功能

- 带引用问答、连续追问，也可只检索原文。
- 按课程或案例筛选资料，浏览和搜索目录。
- 独立账号与讨论记录，支持调用配额管理。

使用 Python、FastAPI、SQLite 和原生 JavaScript，无前端构建步骤。

## 快速开始

需要 Python 3.12，以下命令在 PowerShell 中执行：

```powershell
git clone https://github.com/20triplexx-arch/document-rag-assistant.git
cd document-rag-assistant
.\setup.ps1
.\.venv\Scripts\python.exe starter.py import
```

配置当前终端的 DeepSeek 密钥并启动：

```powershell
$env:DEEPSEEK_API_KEY = "你的 API Key"
.\start.ps1
```

打开 <http://127.0.0.1:8765/>，注册账号后使用。默认模型为 DeepSeek Flash；不设置密钥也可使用“只查原文”。

配置项见 [.env.example](.env.example)，程序读取环境变量，不自动加载 `.env`。首次导入需要联网下载公开资料；后续启动直接运行 `.\start.ps1`。

## 开发

```powershell
.\verify.ps1
```

验证需要 Node.js，测试不调用真实模型。管理员可通过 `create_admin.py` 在本机创建。

## 资料与文档

默认资料包含四套 Agent 课程和 12 个实战案例，来源与许可见 [来源清单](sources-cases.json)。教材快照、账号数据和运行输出保存在本地。

当前为本机开发版；扩展语料和新问答链路仍在验证。引用位置校验不代表答案内容已通过正确性验收。

[产品说明](PRODUCT.md) · [评测说明](evals/README.md) · [开发记录](docs/qa-repair-2026-10-15.md)
