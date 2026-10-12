# 案例02 持久会话与记忆（SQLite）

持久会话如何从数据库回到模型

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合观察框架的会话管理、持久化和重启恢复。这个案例的“记得”依赖稳定的 app_name、user_id、session_id 以及数据库文件，不是模型自动访问磁盘。对应主线第09到12课。

## 架构

> 流程：Streamlit 输入 → chat(user_id,message) → 查询或创建会话 → Runner → 数据库事件 → 显示答复

## 关键代码与机制

agent.py 创建 DatabaseSessionService，db_url 指向 sqlite:///sessions.db。Runner 绑定 agent 与该服务。chat 函数根据 user_id 构造 session_id，先 get_session，再按需 create_session，最后运行 Agent 并收集最终响应。

app.py 用 Streamlit 的 session_state 保存当前页面显示的 messages，并调用 chat("demo_user", prompt)。页面消息列表与 SQLite 中的会话不是同一存储层：重新加载页面可能丢失显示列表，但数据库会话仍可能存在。清空页面按钮主要清理页面 state，不能直接推断数据库历史已删除。

固定的 demo_user 适合单人演示，不是多用户认证。源码还把用户 ID 与会话 ID 关联起来，学习时要检查恢复是否使用同一组标识。不要把“新建任意ID”当成“恢复旧会话”。

## 环境依赖

google-adk>=1.9.0、Streamlit、python-dotenv 和 Google 模型服务；SQLite 在本机写文件。源码中的模型是 gemini-3-flash-preview，实际可用性需自行核对。

<!-- pagebreak -->

# 实验卡02 持久会话与记忆（SQLite）

## 复现步骤

在案例目录安装 requirements.txt，按上游环境模板配置密钥，然后启动网页：
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```
输入一个虚构偏好，停止应用，再在同目录重启并继续同一 demo_user。观察原会话是否被取回；不要删除 sessions.db 后再期待恢复。

## 结果与故障核对

分别记录页面历史和服务端会话是否恢复。更换工作目录可能创建另一个同名数据库。没有登录功能时，不应把固定 demo_user 的演示部署给多个真实用户。

## 扩展练习

解释“清空页面但下次模型仍提到旧信息”的可能原因，并提出一项验证方法。

## 参考答案

页面列表已清空，SQLite 会话可能仍在。检查服务端 session_id 与数据库事件，确认清空动作是否同时删除或重置持久会话。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/5_memory_agent/5_2_persistent_conversation_agent/README.md)

- [agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/5_memory_agent/5_2_persistent_conversation_agent/agent.py) | Git blob：cfc93c3021cf537a3ecac480274102d430118003
- [app.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/5_memory_agent/5_2_persistent_conversation_agent/app.py) | Git blob：6eb5e83afd8101551e8d455b7a53d50b0e49ded3

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
