# 案例08 RAG 故障诊断

故障分析助手提供建议，不代替工程定位

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合学习把故障描述映射到可复用模式。案例是一个框架依赖较少的终端程序，通过模型输出诊断、证据需求和处理建议。

## 架构

> 流程：选择或输入故障 → 故障模式提示 → 模型请求 → 诊断建议 → 人工验证

## 关键代码与机制

rag_failure_diagnostics_clinic.py 包含12类模式：证据漂移、切分边界、嵌入不匹配、索引陈旧、查询路由、长链漂移、工具误用、记忆问题、评测盲区、启动顺序、配置差异和相互干扰。

build_system_prompt 组织模式说明，choose_bug_description 提供示例或接受自定义输入，make_client_and_model 从环境变量读取配置。run_once 调用模型并展示输出。程序没有读取你的实际向量索引或自动修复代码，因此输出是诊断假设。

故障描述越具体，越容易形成可验证建议。写清问题、预期、实际候选、文档版本和最近修改；如果只输入“RAG不准”，模型只能给宽泛的可能性。先定位证据缺失还是生成偏离，再选择改动。

## 环境依赖

requirements.txt 提供模型客户端依赖。源码默认配置读取 OPENAI_API_KEY、OPENAI_BASE_URL 和 OPENAI_MODEL。兼容端点可以调整，但并非所有服务参数都等价；课程没有验证替换端点。

<!-- pagebreak -->

# 实验卡08 RAG 故障诊断

## 复现步骤

安装该目录依赖，按源码配置变量，然后运行：
```bash
python -m pip install -r requirements.txt
python rag_failure_diagnostics_clinic.py
```
先选上游内置虚构故障，再输入自己的脱敏样本。这个命令会请求模型，不属于本包默认离线练习。

## 结果与故障核对

输出应把确认事实与假设区分。每条建议配一个能取得的证据，例如检查索引版本或打印候选。没有证据支持时不能把某一模式写成确定根因。

## 扩展练习

输入“更新政策后还回答旧截止日”，给出两个可能原因和各自检查方法。

## 参考答案

索引未更新：比较源文件哈希与索引版本；生成忽略新资料：检查实际传入上下文是否已是新截止日。先按数据流确认哪个阶段最早偏离。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/rag_failure_diagnostics_clinic/README.md)

- [rag_failure_diagnostics_clinic.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/rag_tutorials/rag_failure_diagnostics_clinic/rag_failure_diagnostics_clinic.py) | Git blob：9e315f8523cfa5b44a0a141801556d8a662b5197

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
