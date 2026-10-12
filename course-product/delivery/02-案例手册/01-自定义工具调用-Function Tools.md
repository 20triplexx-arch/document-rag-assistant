# 案例01 自定义工具调用（Function Tools）

让计算回到确定性的程序

验证状态：已读取固定版本README与实现源码，17个原有实现入口已核对Git blob；未安装、未启动、未调用该上游案例的模型或服务。

## 用途与学习目标

适合学习把业务函数注册为 Agent 工具。上游计算器包含基本运算、温度换算、复利、百分比、统计和四舍五入工具。它说明模型如何选择函数，并不意味着所有参数都已被充分约束。建议先完成本包 tool_agent.py，再阅读这个框架版本。

## 架构

> 流程：用户问题 → Google ADK 的 LlmAgent → 注册的计算函数 → 结构化结果 → 模型答复

## 关键代码与机制

calculator_agent/agent.py 的 root_agent 使用 LlmAgent，tools 参数传入六个 Python 函数。模型名称为固定源码中的 gemini-3-flash-preview，不应把它当作当前一定可用的型号。

tools.py 的 calculate_basic_math 先过滤字符再调用 eval。字符过滤会改变原始表达，例如一个包含非法字符的输入可能被悄悄改成另一个表达；允许字符内仍能写出重复乘法或幂运算，不能据此认定资源消耗已受控。本课程练习改为 operation、a、b 三项参数和明确四种分支。

calculate_compound_interest 检查本金、年数和复利次数；calculate_statistics 拒绝空列表并计算统计量。学习时重点比较：不同函数对输入的约束是否一致，错误返回字段是否稳定，成功结果能否独立复算。

## 环境依赖

上游 requirements.txt 要求 google-adk>=1.5.0；模型调用使用 Google 服务，需要自行配置该项目的 Google 密钥。框架版本是范围约束，没有完整固定依赖闭包，不能保证未来安装行为相同。

<!-- pagebreak -->

# 实验卡01 自定义工具调用（Function Tools）

## 复现步骤

在该案例目录建立独立环境、安装 requirements.txt，按照上游实际存在的 .env.example 配置 Google 变量，然后执行 adk web，选择 calculator_agent。不要直接 python calculator_agent/agent.py 期待一个完整终端应用。
```bash
python -m pip install -r requirements.txt
adk web
```
先询问“18乘7”，再试除零。模型和工具执行属于可选的上游复现实验。

## 结果与故障核对

核对工具返回结果是否为126；除零是否返回错误；输出是否声称执行了未注册工具。还应测试缺参数、超长表达式与类型异常。源码中出现“safely”并不等于安全性已验收。

## 扩展练习

设计一个不使用 eval 的温度换算函数，明确单位与数值类型；写出0℃和100℃的结果。

## 参考答案

只接受数值 celsius，输出 celsius*9/5+32；0对应32，100对应212。字符串单位先在输入层解析，不能默默删字符再计算。

## 固定版本来源

[上游README](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/README.md)

- [agent.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/calculator_agent/agent.py) | Git blob：ce412ad747dfb722447fc5e3c9fb8d4f09ac9a9f
- [tools.py](https://github.com/Shubhamsaboo/awesome-llm-apps/blob/4bf51ab704fb2c5b3803cd5191b30d7dcdb51dc2/ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/calculator_agent/tools.py) | Git blob：390efb6cfa2cc8f288515e5e1eb25ea448fd1f21

来源许可：Apache-2.0。作者与版权归上游贡献者；本手册增加中文教学组织、流程解释、源码边界与练习。许可证原文见附录。
