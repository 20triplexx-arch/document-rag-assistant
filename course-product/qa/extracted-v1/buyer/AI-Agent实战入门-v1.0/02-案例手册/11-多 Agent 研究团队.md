# 案例11 多 Agent 研究团队

研究团队：找、读、整合的职责

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合阅读多 Agent 在信息研究任务中的分工。上游有模型服务版本与 Ollama 版本，都结合 HackerNews、网页搜索和文章读取工具。

## 架构

> 流程：研究问题 → HackerNews研究员 + 网页搜索员 + 文章阅读员 → Team协调 → 汇总与来源

## 关键代码与机制

research_agent.py 构造三个成员：hn_researcher 使用 HackerNewsTools，web_searcher 使用 DuckDuckGoTools，article_reader 使用 Newspaper4kTools；Team 接收成员并生成结果。固定源码实际使用 gpt-4o-mini，README的简写描述不应覆盖源码。

research_agent_llama3.py 改用 Ollama(id="llama3.2")，但网页检索和文章读取仍需要网络，因此“本地模型”不等于整个任务离线。两个文件可帮助你把模型服务与外部工具分开分析。

团队角色的提示表达了希望发生的分工，不保证每次严格按相同顺序执行。结果要保留来源、日期和支持的事实；文章读取失败时不能让整合角色自行补造文章内容。

## 环境依赖

Streamlit、agno>=2.2.10、HackerNews/搜索/文章读取相关包。模型服务版本需要账户配置；Ollama版本需要本地模型。网络可访问性影响各工具行为。

<!-- pagebreak -->

# 实验卡11 多 Agent 研究团队

## 复现步骤

在目录安装 requirements 后，选择一种模型路径：
```bash
python -m pip install -r requirements.txt
streamlit run research_agent.py
```
或先运行 Ollama并拉取模型，再执行：
```bash
ollama pull llama3.2
streamlit run research_agent_llama3.py
```
用公开且范围清楚的研究题测试，核对来源和日期。

## 结果与故障核对

比较单个搜索Agent与团队的来源覆盖、重复项、耗时和结果支持。不能只凭内容更长推断质量更高。案例未在本次制作中测得准确率或收益。

## 扩展练习

定义一张成员交付表，要求找资料者、读文章者、整合者分别交付哪些字段。

## 参考答案

找资料者交付URL、标题和时间；阅读者交付原文依据与提取事实；整合者只使用确认事实，并列出冲突与未读取来源。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/multi_agent_researcher/README.md)

- [research_agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/multi_agent_researcher/research_agent.py) | Git blob：a0ae20c2e4a000686af3e1ba267cf1dbe7abfe54
- [research_agent_llama3.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/advanced_ai_agents/multi_agent_apps/multi_agent_researcher/research_agent_llama3.py) | Git blob：8bfe1f530472eda8a1cc7ba746dbef2e8bf7c49b

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
