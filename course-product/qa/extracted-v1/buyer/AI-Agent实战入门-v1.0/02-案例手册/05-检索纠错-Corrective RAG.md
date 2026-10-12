# 案例05 检索纠错（Corrective RAG）

检索失败时，改写的是查询而不是目标

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合阅读 LangGraph 状态图。上游实现把检索、相关性判别、查询改写、外部搜索和生成分成节点，比只加一句“请纠错”更容易观察分支。

## 架构

> 流程：retrieve → grade_documents → 足够则generate；不足则transform_query → web_search → generate

## 关键代码与机制

corrective_rag.py 定义状态并建立 StateGraph，retrieve 从向量检索器取文档，grade_documents 用模型判断片段相关性。decide_to_generate 根据状态选择生成或改写。transform_query 将问题改写，再进入 web_search。

固定图里的 web_search 直接连向 generate，而不是再次回到相关性评分节点。因此它不是无限循环纠错，也没有展示“搜索后再评分”的完整闭环。分析源码时应以真实图边为准，不能只照标题想象机制。

相关性输出需要解析 JSON 的 score 字段。格式异常、打分误判和外部搜索失败都会影响结果。源码使用 Qdrant、嵌入服务、Anthropic 和 Tavily；缺少搜索配置时应检查返回分支是否仍然沿用弱证据。

## 环境依赖

LangChain、LangGraph、Qdrant、Streamlit 与多类API。requirements 固定部分版本，例如 LangChain 0.3.12；安装现代版本可能改变接口。数据源支持情况由 loader 分支决定，不应把所有文件都当可读。

<!-- pagebreak -->

# 实验卡05 检索纠错（Corrective RAG）

## 复现步骤

先启动 Qdrant，安装案例 requirements，然后启动：
```bash
python -m pip install -r requirements.txt
streamlit run corrective_rag.py
```
配置生成、嵌入、Qdrant及搜索服务，选择公开资料。先测试一题能够直接检索回答，再测试一题需要改写，并记录每个节点输出。

## 结果与故障核对

核对 original question 是否被保留；搜索来源是否可靠；改写是否丢失约束；没有证据时是否仍生成确定答案。重点测试搜索不可用和评分JSON异常。

## 扩展练习

把一次外部搜索后的资料重新评分，画出新增分支与停止规则，不需要真正调用API。

## 参考答案

可在 web_search 后增加 grade_external，相关则生成，不相关则返回证据不足。设置最多一次改写和一次搜索，避免循环；记录原问题与每次查询。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/corrective_rag/README.md)

- [corrective_rag.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/corrective_rag/corrective_rag.py) | Git blob：853a74a5a21bf2731668e11effb2abeef764f1c3

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
