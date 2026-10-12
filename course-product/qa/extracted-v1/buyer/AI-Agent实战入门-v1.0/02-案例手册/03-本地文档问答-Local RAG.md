# 案例03 本地文档问答（Local RAG）

本地文档、嵌入、向量库与本地模型

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合理解一个使用 Ollama、Qdrant 与 Agno 的文档问答应用。它与本包关键词练习不同：上游使用向量库与本地推理服务，首次安装和模型下载仍需要网络。

## 架构

> 流程：PDF资料 → Knowledge → OllamaEmbedder → Qdrant → 检索上下文 → Ollama模型 → AgentOS

## 关键代码与机制

local_rag_agent.py 构造 Qdrant，地址是 localhost:6333，集合名 thai-recipe-index。Knowledge 接收这个向量库，然后 add_content 下载一个公开食谱 PDF。脚本没有内置你自己的资料目录遍历，需要修改资料导入位置。

生成模型使用 Ollama(id="llama3.2")，最终通过 AgentOS 暴露应用。agent_os.serve 在脚本入口启动服务。这里的“本地”指模型和向量库可以在本机运行，不应忽略默认资料仍是远程 URL。

README 建议拉取 openhermes 用于嵌入，但源码实例 OllamaEmbedder() 没有显式填模型名。复现时应检查所安装 Agno 版本的默认嵌入型号并显式设定，而不是假定拉取任意模型就够用。生成模型与嵌入模型的职责不同。

## 环境依赖

requirements.txt 中有 agno>=2.2.10、qdrant-client、Ollama 相关依赖；还需安装运行 Ollama 和 Qdrant。硬件内存与磁盘需求取决于实际模型，课程未测量该上游案例的占用。

<!-- pagebreak -->

# 实验卡03 本地文档问答（Local RAG）

## 复现步骤

先启动本机 Qdrant，再拉取生成与实际使用的嵌入模型。Docker 示例仅把 Qdrant 暴露在回环地址：
```bash
docker run --name course-qdrant -p 127.0.0.1:6333:6333 qdrant/qdrant
ollama pull llama3.2
ollama pull openhermes
python -m pip install -r requirements.txt
python local_rag_agent.py
```
确认 Ollama 服务正在运行；上述嵌入模型名须与源码配置一致。应用访问地址以实际控制台输出为准。

## 结果与故障核对

检查首次导入是否重复执行、集合是否创建、资料是否真被读取。对有答案和无答案问题分别测试；不以网页启动代表检索正确。远程PDF不可访问时先替换为可访问教学资料。

## 扩展练习

把资料源换成一份自己的公开文本，说明生成模型和嵌入模型各负责什么。

## 参考答案

嵌入模型负责文档与问题表示，生成模型根据检索上下文生成文本。更换嵌入模型需重建兼容索引；只更换生成模型通常不要求重算文档向量，但仍须重新验证答案。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/local_rag_agent/README.md)

- [local_rag_agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/local_rag_agent/local_rag_agent.py) | Git blob：6d3473095f12262bd5c1f2e751e6b70b96de6035

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
