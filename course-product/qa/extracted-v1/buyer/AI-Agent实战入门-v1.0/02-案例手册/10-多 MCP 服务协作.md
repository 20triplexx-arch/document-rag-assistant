# 案例10 多 MCP 服务协作

多 MCP 服务协作的权限与状态

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合阅读 Agno 对多个 MCP 服务的组织方式。案例包含仓库、搜索、日历和邮箱服务，但接通服务不代表所有写操作都已被授权。

## 架构

> 流程：环境配置 → 多MCP服务上下文 → 单个Agent使用多工具 → 会话数据库 → 交互终端

## 关键代码与机制

multi_mcp_agent.py 验证三类变量，再随机生成 user_id 与 session_id。它通过 MultiMCPTools 连接四条 npx 服务命令，为单个 Agent 提供工具集合；README 使用“Multi-Agent”描述，实际主文件展示的是一个 Agent 加多个服务。

SqliteDb 指向 tmp/multi_mcp_agent.db。每次启动会话ID随机产生，旧数据库存在不等于自动恢复同一会话。acli_app 接受本次 user_id 和 session_id。按持久化章节的方法检查这些标识如何复用。

env={**os.environ,...} 会把整个进程环境交给子服务；独立实现可改为只传服务必要变量。服务命令也没有统一固定版本，运行时权限与包版本要另外核对。源码里的能力描述不能代替授权和成功结果。

## 环境依赖

Agno、mcp、python-dotenv、模型客户端、Node.js与各外部服务。GitHub与搜索凭据、日历/邮箱授权各有独立要求，不能将一项密钥当作全部服务都可访问。

<!-- pagebreak -->

# 实验卡10 多 MCP 服务协作

## 复现步骤

安装依赖并检查Node工具；按同目录环境模板配置，只在隔离学习账户里尝试：
```bash
python -m pip install -r requirements.txt
node --version
python multi_mcp_agent.py
```
第一次只做读取与生成草稿任务，先观察哪些子服务真正启动。未完成必要授权时，不声称对应服务可用。

## 结果与故障核对

检查服务启动失败的行为、继承变量范围、会话恢复和输出凭据风险。测试只读请求是否触发写工具；跨服务写入需要可核对结果ID与去重策略。

## 扩展练习

把“读取仓库问题并安排复查”拆成读取、草稿和写入三步，并列出必要权限。

## 参考答案

读取阶段只需要仓库只读；草稿阶段在本机生成标题与日期；写入阶段才需要日历创建权限，必须校验时间与授权并保存事件ID。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/multi_mcp_agent/README.md)

- [multi_mcp_agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/mcp_ai_agents/multi_mcp_agent/multi_mcp_agent.py) | Git blob：dc3689541645dd2bf768dc84937c0768edfe17e6

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
