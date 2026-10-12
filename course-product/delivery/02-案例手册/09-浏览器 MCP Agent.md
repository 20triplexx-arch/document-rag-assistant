# 案例09 浏览器 MCP Agent

浏览器 MCP 的服务连接与页面结果

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合观察 Host 如何经 MCP 获得 Playwright 工具。上游使用 Streamlit 与 mcp-agent，额外依赖 Node.js、浏览器工具服务和模型配置。

## 架构

> 流程：网页输入 → MCPApp → browser Agent → playwright服务 → 模型调用工具 → 页面操作与答复

## 关键代码与机制

main.py 的 setup_agent 创建 MCPApp 的异步上下文，构造 server_names=["playwright"] 的 Agent，初始化后 attach_llm，再 list_tools。run_mcp_agent 负责检查模型配置并生成文本。

独立配置 mcp_agent.config.yaml 将 playwright 指向 npx，参数是 @playwright/mcp@latest。仓库固定提交并没有固定这个外部服务版本，因此长期复现时需要额外记录实际安装版本。配置中的模型默认来自旧快照，实际可用性需核对。

该应用手动进入异步上下文并将对象存在 session_state。学习时要检查页面重载、异常与退出时资源能否释放。工具连接成功和页面任务完成是两项不同信号；不能只看 initialized 为真。

## 环境依赖

Streamlit、mcp-agent>=0.0.14、Node.js/npm、Playwright MCP 和模型服务。实际浏览器组件可能需要下载。配置文件与源码共同决定服务名称、模型和连接方式。

<!-- pagebreak -->

# 实验卡09 浏览器 MCP Agent

## 复现步骤

先检查 Node.js 与 npm，安装 requirements，按同目录 mcp_agent.config.yaml 和 secrets 示例配置模型，然后执行：
```bash
node --version
npm --version
python -m pip install -r requirements.txt
streamlit run main.py
```
用公开文档页的只读任务做第一项实验。首次启动外部服务会下载组件，应自行检查来源与版本。

## 结果与故障核对

核对工具列表与服务名一致；观察页面是否实际到达目标；点击后重新读取状态；记录可见成功信号。页面提示不等于用户授权，不执行无关上传或写入。

## 扩展练习

设计“从公开文档找安装命令”的验收项，至少写出一个页面异常和处理方式。

## 参考答案

验收为找到对应版本的命令与原页面链接。弹窗遮挡时先观察并处理正常弹窗；访问受限时说明限制，不绕过登录或访问控制。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/browser_mcp_agent/README.md)

- [main.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/browser_mcp_agent/main.py) | Git blob：8d83dbf1065ddd983107bfda9082d8e2b3aa57b3

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
