# 八个真实试答样本

2026-10-14；1 个开发复测、7 个充分支持上下文对照。全部为真实 Flash 输出。它们不代表日常检索的验收成绩；工具样本仍有冗长问题。原文引文核对通过，语义复核来源为 AI，无人工审批。

## 工具调用时，模型、宿主程序和工具各做什么？请解释从参数生成到模型收到执行结果的完整过程。

工具调用是一个有界循环：模型决定何时调用工具、提供什么参数；宿主程序（agent loop）重复“询问模型 → 执行工具 → 返回结果”，直到得到答案或碰到上限；工具本身是输入输出明确的、可调用的函数，真正执行动作并返回结果。完整来回是 model → tool call → execute → tool result → model。

工具定义时，类型提示是必需的，它决定工具的输入 schema；函数的 docstring 默认成为工具描述，帮助模型判断何时使用该工具。模型基于对话上下文选择工具并生成调用参数，宿主程序拿到这个调用后执行对应工具。

工具执行后，返回值通常被包装成 ToolMessage，模型看到这段文本后决定下一步。每个 AIMessage 的工具调用必须在消息历史中有对应的 ToolMessage；如果工具返回的是 Command 且目标是当前图、没有在 Command.update 里放入匹配 tool_call_id 的 ToolMessage，ToolNode 会抛 ValueError。

默认情况下结果回到模型继续推理；设置 return_direct=True 可短路循环，工具输出直接作为最终回复返回给调用方，不再经模型处理。若模型在同一步并行调用多个工具，只有当该批次每个工具都是 return_direct=True 时才会直接结束；否则宿主程序把批次里所有 ToolMessage 带回模型，由模型统一推理。

工具返回值也可以是文本以外的形式：返回字符串提供纯文本供模型阅读；返回多模态内容时转成带多模态 content 的 ToolMessage，模型必须支持所返回的模态。MCP 服务端还允许以 InputRequiredResult 响应 tools/call，表示完成调用前需要额外输入，客户端重试时带上 inputResponses 和可选的 requestState，且重试的 JSON-RPC id 必须与初始请求不同。

模型 | 基于对话上下文决定是否调用工具、调用哪个工具、提供什么参数；收到 ToolMessage 后决定下一步

宿主程序（agent loop） | 重复“询问模型 → 执行工具 → 返回结果”，维护消息历史（确保每个 tool call 有对应 ToolMessage），根据 return_direct 决定是否短路

工具 | 输入输出明确的 callable 函数，按模型生成的参数执行并返回结果；返回值被包装成 ToolMessage（或 Command）

引用原文：
- [E1 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L1-L31)

```text
Under the hood, tools are callable functions with well-defined inputs and outputs that get passed to a [chat model](/oss/langchain/models). The model decides when to invoke a tool based on the conversation context, and what input arguments to provide.
```

- [E2 · 03-tool-use-and-hello-agent](https://github.com/WenyuChiou/awesome-agentic-ai-zh/blob/50fc26d5decc1f3ee8a9e67b9f2c807e179e01d6/stages/03-tool-use-and-hello-agent.zh-Hans.md#L47-L50)

```text
程序重复“询问模型 → 执行工具 → 返回结果”，直到得到答案或碰到上限。
```

- [E2 · 03-tool-use-and-hello-agent](https://github.com/WenyuChiou/awesome-agentic-ai-zh/blob/50fc26d5decc1f3ee8a9e67b9f2c807e179e01d6/stages/03-tool-use-and-hello-agent.zh-Hans.md#L47-L50)

```text
完整来回是 `model → tool call → execute → tool result → model`
```

- [E8 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L34-L87)

```text
Type hints are **required** as they define the tool's input schema. The docstring should be informative and concise to help the model understand the tool's purpose.
```

- [E1 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L1-L31)

```text
The model decides when to invoke a tool based on the conversation context, and what input arguments to provide.
```

- [E5 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L680-L703)

```text
The return value is converted to a `ToolMessage`.
```

- [E5 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L680-L703)

```text
The model sees that text and decides what to do next.
```

- [E3 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L850-L859)

```text
Omitting it causes `ToolNode` to raise a `ValueError`, because every `AIMessage` tool call must have a corresponding `ToolMessage` in the message history.
```

- [E4 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L812-L849)

```text
Set return direct on a tool to short-circuit the agent loop: the agent returns the tool's output to the caller immediately, without sending it back through the model for further processing.
```

- [E4 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L812-L849)

```text
After all tools finish, the agent routes to `END` only if **every** tool in that batch has `return_direct=True`.
```

- [E4 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L812-L849)

```text
It routes back to the model with every `ToolMessage` from the batch, so the model can reason over all results.
```

- [E7 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L728-L777)

```text
The return value is converted to a `ToolMessage` with multimodal `content`.
```

- [E7 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L728-L777)

```text
The model must support the modalities you return.
```

- [E6 · MCP 2026-07-28 · server/tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/server/tools.mdx#L174-L235)

```text
Servers **MAY** respond to `tools/call` with an [`InputRequiredResult`](/specification/2026-07-28/basic/patterns/mrtr#inputrequiredresult) to indicate that additional input is needed before the tool call can be completed.
```

- [E6 · MCP 2026-07-28 · server/tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/server/tools.mdx#L174-L235)

```text
Note that the JSON-RPC `id` **MUST** be different between the initial request and the retry.
```

- [E3 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L850-L859)

```text
every `AIMessage` tool call must have a corresponding `ToolMessage` in the message history
```

- [E1 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L1-L31)

```text
Under the hood, tools are callable functions with well-defined inputs and outputs that get passed to a [chat model](/oss/langchain/models).
```

- [E4 · 工具调用](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/tools.mdx#L812-L849)

```text
The tool executes normally and its output is wrapped in a `ToolMessage`.
```


## 短期记忆为什么跟 thread 走，长期记忆为什么用 namespace？同一用户换一段讨论时，两者分别保留什么？

短期记忆的边界是 thread：它按消息历史跟踪正在进行的对话，属于 agent state 的一部分，由 checkpointer 持久化到数据库，因此该 thread 可随时恢复；状态在图被调用或一步完成时更新，每步开始时读取。长期记忆的边界是自定义 namespace：它存跨会话的用户级或应用级数据，跨对话 thread 共享，可在任意时刻、任意 thread 取用，不局限在单个 thread ID 内。

换一段讨论时，短期记忆仍是同一 thread 内的消息历史——只要新讨论还在同一 thread，它延续这段会话；若开了新 thread，旧 thread 的历史留在旧 thread 的检查点里，不会自动带入。长期记忆则与 thread 无关：新讨论只要落在同一 namespace（如相同用户 ID），就能取到之前写入的该用户数据；namespace 类似文件夹，常包含用户或组织 ID 等标签来组织信息，key 则像文件名区分具体条目。

引用原文：
- [E1 · 记忆概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/concepts/memory.mdx#L12-L12)

```text
Short-term memory, or thread-scoped memory, tracks the ongoing conversation by maintaining message history within a session.
```

- [E2 · 记忆概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/concepts/memory.mdx#L13-L13)

```text
Long-term memory stores user-specific or application-level data across sessions and is shared _across_ conversational threads.
```

- [E1 · 记忆概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/concepts/memory.mdx#L12-L12)

```text
State is persisted to a database using a checkpointer so the thread can be resumed at any time.
```

- [E2 · 记忆概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/concepts/memory.mdx#L13-L13)

```text
It can be recalled _at any time_ and _in any thread_. Memories are scoped to any custom namespace, not just within a single thread ID.
```

- [E3 · 长期记忆](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/long-term-memory.mdx#L91-L91)

```text
Each memory is organized under a custom `namespace` (similar to a folder) and a distinct `key` (like a file name).
```


## 2-step RAG 与 Agentic RAG 在谁决定检索、执行顺序和延迟可预测性上有什么差别？

2-step RAG 中检索固定在生成之前、由流程预先决定；Agentic RAG 中由 LLM 驱动的 agent 在推理过程中自行决定何时检索、如何检索。因此 2-step RAG 的最大 LLM 调用次数已知且有上限，延迟更可预测；Agentic RAG 的延迟是可变的。

检索决策：2-step RAG 在生成前先做检索，步骤由流程预先确定。

Agentic RAG 不是在回答前先取文档，而是 agent 逐步推理，在交互期间决定何时、如何检索。

延迟可预测性：2-step RAG 最大 LLM 调用次数已知且有上限，所以更可预测；这一判断假设 LLM 推理时间是主导因素，真实延迟仍可能受检索步骤、API 响应、网络或数据库查询影响。

Agentic RAG 的延迟表现为可变，因为检索的时机和次数由推理过程动态决定。

引用原文：
- [E1 · 正文依赖 · retrieval](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/deepagents/retrieval.mdx#L136-L136)

```text
| **2-Step RAG**          | Retrieval always happens before generation. Simple and predictable         | ✅ High    | ❌ Low       | ⚡ Fast         | FAQs, documentation bots                           |
```

- [E2 · 正文依赖 · retrieval](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/deepagents/retrieval.mdx#L137-L137)

```text
| **Agentic RAG**         | An LLM-powered agent decides *when* and *how* to retrieve during reasoning | ❌ Low     | ✅ High      | ⏳ Variable     | Research assistants with access to multiple tools  |
```

- [E1 · 正文依赖 · retrieval](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/deepagents/retrieval.mdx#L136-L136)

```text
Retrieval always happens before generation.
```

- [E3 · 正文依赖 · retrieval](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/deepagents/retrieval.mdx#L186-L186)

```text
Instead of retrieving documents before answering, an agent (powered by an LLM) reasons step-by-step and decides **when** and **how** to retrieve information during the interaction.
```

- [E4 · 正文依赖 · retrieval](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/deepagents/retrieval.mdx#L141-L141)

```text
**Latency**: Latency is generally more **predictable** in **2-Step RAG**, as the maximum number of LLM calls is known and capped. This predictability assumes that LLM inference time is the dominant factor.
```


## ReAct 和先规划后执行有什么区别？任务步骤会因工具结果改变时，各自怎么处理？

ReAct 与先规划后执行的核心区别在于控制流：ReAct 把推理和工具调用交织成一个动态循环，每一步的行动结果都会反馈回来修正下一步的思考；先规划后执行则先把复杂任务分解成清晰的步骤序列，再逐一执行，结构性和稳定性更强。

步骤会因工具结果变化时，ReAct 依赖“思考-行动-观察”循环不断接收环境反馈，行动结果反过来修正后续思考，因此适应性和动态纠错能力更强，适合探索性、需要外部工具输入的任务。

先规划后执行假设逻辑路径基本确定：任务被一次分解为步骤后按序执行，优势是高结构性和稳定性，适合内部推理密集、路径确定的场景；证据未说明执行中工具结果偏离计划时如何回退或重规划。

引用原文：
- [E1 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L144-L144)

```text
它认识到思考与行动是相辅相成的。思考指导行动，而行动的结果又反过来修正思考
```

- [E2 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L1233-L1233)

```text
它将复杂的任务分解为清晰的步骤，然后逐一执行。其核心优势在于结构性和稳定性
```

- [E3 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L1232-L1232)

```text
通过“思考-行动-观察”的动态循环
```

- [E3 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L1232-L1232)

```text
其核心优势在于环境适应性和动态纠错能力，使其成为处理探索性、需要外部工具输入的任务的首选
```

- [E1 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L144-L144)

```text
行动的结果又反过来修正思考
```

- [E2 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L1233-L1233)

```text
特别适合处理逻辑路径确定、内部推理密集的任务
```

- [E2 · 第四章 智能体经典范式构建](https://github.com/datawhalechina/hello-agents/blob/6acdf9527f9c229b173f26d66bee2f6831d6c93a/docs/chapter4/%E7%AC%AC%E5%9B%9B%E7%AB%A0%20%E6%99%BA%E8%83%BD%E4%BD%93%E7%BB%8F%E5%85%B8%E8%8C%83%E5%BC%8F%E6%9E%84%E5%BB%BA.md#L1233-L1233)

```text
其核心优势在于结构性和稳定性
```


## 上下文工程到底在每次模型调用前控制哪些信息？请区分模型上下文、工具上下文和生命周期上下文。

上下文工程是在每次模型调用前提供正确格式的恰当信息和工具，让 LLM 能完成任务。它分为三个层面：模型上下文决定模型调用本身看到什么，是临时的；工具上下文决定工具能读写什么状态、存储和运行时上下文，是持久的；生命周期上下文决定模型调用和工具调用之间发生什么，比如摘要、护栏和日志，同样是持久的。

模型上下文 | 模型调用包含的指令、消息历史、工具、响应格式 | 临时

工具上下文 | 工具能访问和产生的内容，包括对 state、store、runtime context 的读写 | 持久

生命周期上下文 | 模型调用与工具调用之间发生的事，如摘要、护栏、日志等 | 持久

引用原文：
- [E1 · 上下文工程](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/context-engineering.mdx#L19-L19)

```text
**Context engineering** is providing the right information and tools in the right format so the LLM can accomplish a task.
```

- [E2 · 上下文工程](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/context-engineering.mdx#L48-L48)

```text
**[Model Context](#model-context)** | What goes into model calls (instructions, message history, tools, response format) | Transient |
```

- [E3 · 上下文工程](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/context-engineering.mdx#L49-L49)

```text
**[Tool Context](#tool-context)** | What tools can access and produce (reads/writes to state, store, runtime context) | Persistent |
```

- [E4 · 上下文工程](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/context-engineering.mdx#L50-L50)

```text
**[Life-cycle Context](#life-cycle-context)** | What happens between model and tool calls (summarization, guardrails, logging, etc.) | Persistent |
```


## MCP 的 host、client、server 分别负责什么？当前默认规范怎样处理协议版本与能力？

MCP 2026-07-28 是三项分工：host 是容器与协调者，client 由 host 创建并一对一连接某个 server，server 提供专门的上下文与能力。协议本身无状态，每次请求自带协议版本与能力。

host：创建并管理多个 client 实例，控制连接权限与生命周期，执行安全策略与同意要求，处理用户授权，协调 AI/LLM 集成与 sampling，并聚合多个 client 的上下文。

client：每个 client 对应恰好一个 server；在每次请求上附带协议版本和能力，双向路由协议消息，管理订阅与通知，并维持 server 之间的安全边界。

server：通过 MCP 原语暴露 resources、tools、prompts，独立承担聚焦职责，可在回复中通过 InputRequiredResult 请求 client 输入（sampling、elicitation、roots），遵守安全约束，既可以是本地进程也可以是远程服务。

能力协商：client 在每次请求的 _meta.io.modelcontextprotocol/clientCapabilities 中声明自身能力；server 在 server/discover 的响应中说明能力，client 可在任何其他请求之前先调用它以提前发现能力。

引用原文：
- [E1 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L52-L59)

```text
The host process acts as the container and coordinator:

- Creates and manages multiple client instances
```

- [E2 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L63-L69)

```text
Each client is created by the host and communicates with exactly one server:
```

- [E3 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L76-L82)

```text
Servers provide specialized context and capabilities:
```

- [E4 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L8-L9)

```text
MCP is a stateless protocol: every request is
self-contained and carries its own protocol version and capabilities.
```

- [E1 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L52-L59)

```text
- Creates and manages multiple client instances
- Controls client connection permissions and lifecycle
- Enforces security policies and consent requirements
- Handles user authorization decisions
- Coordinates AI/LLM integration and sampling
- Manages context aggregation across clients
```

- [E2 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L63-L69)

```text
- Communicates with exactly one server
- Attaches protocol version and capabilities to every request
- Routes protocol messages bidirectionally
- Manages subscriptions and notifications
- Maintains security boundaries between servers
```

- [E3 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L76-L82)

```text
- Expose resources, tools and prompts via MCP primitives
- Operate independently with focused responsibilities
- Request client input (sampling, elicitation, roots) via `InputRequiredResult` within a reply
- Must respect security constraints
- Can be local processes or remote services
```

- [E5 · MCP 2026-07-28 · architecture/index](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/5ea996028df322ce97d1c906731cf8c05a6e268e/docs/specification/2026-07-28/architecture/index.mdx#L119-L123)

```text
Clients include their
capabilities in `_meta.io.modelcontextprotocol/clientCapabilities` on every request.
Servers advertise their capabilities in response to
[`server/discover`](/specification/2026-07-28/server/discover), which clients may call before
any other request for up-front capability discovery.
```


## subagents 与 handoffs 在控制权和状态传递上有什么区别？分别适合哪种任务？

两者最核心的区别在于：subagents 由主 Agent 保留控制权，把子 Agent 当作工具调用，输入和结果都由主 Agent 安排；handoffs 则把控制权转交给另一个 Agent 或另一套配置，靠一个跨轮次持久的状态变量来触发切换。

控制权：subagents 中主 Agent 决定调用哪个子 Agent、传什么输入、如何合并结果，控制始终集中在主 Agent；handoffs 中状态变量决定路由，行为随之切换到不同 Agent 或不同配置。

状态传递：subagents 默认无状态，子 Agent 不记得过往交互，全部对话记忆由主 Agent 维护，因此每次调用都在干净的上下文窗口中工作；handoffs 的状态变量跨轮次持久，下一轮行为由它读取决定。

适合 subagents 的场景：多个彼此独立的领域（如日历、邮件、CRM、数据库）、子 Agent 不需要直接与用户对话、或希望集中控制工作流。

适合 handoffs 的场景：需要强制执行先后顺序（满足前置条件后才解锁能力）、Agent 需要在不同状态下直接与用户对话、或构建多阶段对话流程，例如先收集保修 ID 再处理退款。

补充边界：如果只是少数几个工具，应使用单个 Agent，而不是 subagents 模式。

引用原文：
- [E1 · 子 Agent](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/subagents.mdx#L5-L5)

```text
a central main agent (often referred to as a supervisor) coordinates subagents by calling them as tools. The main agent decides which subagent to invoke, what input to provide, and how to combine results.
```

- [E2 · 控制权转接](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/handoffs.mdx#L5-L5)

```text
tools update a state variable (e.g., `current_step` or `active_agent`) that persists across turns, and the system reads this variable to adjust behavior
```

- [E1 · 子 Agent](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/subagents.mdx#L5-L5)

```text
The main agent decides which subagent to invoke, what input to provide, and how to combine results.
```

- [E2 · 控制权转接](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/handoffs.mdx#L5-L5)

```text
the system reads this variable to adjust behavior—either applying different configuration (system prompt, tools) or routing to a different [agent](/oss/langchain/agents)
```

- [E1 · 子 Agent](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/subagents.mdx#L5-L5)

```text
By default, subagents are stateless—they don't remember past interactions, with all conversation memory maintained by the main agent.
```

- [E2 · 控制权转接](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/handoffs.mdx#L5-L5)

```text
a state variable (e.g., `current_step` or `active_agent`) that persists across turns
```

- [E3 · 子 Agent](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/subagents.mdx#L42-L42)

```text
Use the subagents pattern when you have multiple distinct domains (e.g., calendar, email, CRM, database), subagents don't need to converse directly with users, or you want centralized workflow control.
```

- [E4 · 控制权转接](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/handoffs.mdx#L41-L41)

```text
Use the handoffs pattern when you need to enforce sequential constraints (unlock capabilities only after preconditions are met), the agent needs to converse directly with the user across different states, or you're building multi-stage conversational flows.
```

- [E3 · 子 Agent](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/oss/langchain/multi-agent/subagents.mdx#L42-L42)

```text
For simpler cases with just a few [tools](/oss/langchain/tools), use a [single agent](/oss/langchain/agents).
```


## LangSmith 里的 trace、run 和 thread 分别是什么？一次 Agent 请求调用两次工具时，应怎样理解这些记录的关系？

Run 是 Agent 执行的最小工作单元，比如调用 LLM、格式化提示或检索文档；Trace 是单次操作中所有 run 的集合，用唯一 trace ID 绑定；Thread 是代表单次多轮会话的一系列 trace。

一次用户请求触发 Agent 调用模型、运行工具、再调用模型，这些步骤各自的 run 都属于同一个 trace，因为它们共享同一 trace ID；这次请求本身就是一个 turn，因此它作为独立 trace 被记录，若后续还有多轮对话，再通过传入 thread_id 元数据把这些 trace 归入同一 thread。

引用原文：
- [E1 · LangSmith 可观测性概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/langsmith/observability-concepts.mdx#L34-L34)

```text
A _run_ represents a single unit of work executed by an agent, such as calling an LLM, formatting a prompt, or retrieving documents.
```

- [E2 · LangSmith 可观测性概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/langsmith/observability-concepts.mdx#L38-L38)

```text
A _trace_ is a collection of runs for a single operation.
```

- [E3 · LangSmith 可观测性概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/langsmith/observability-concepts.mdx#L44-L44)

```text
A _thread_ is a sequence of traces representing a single multi-turn session.
```

- [E2 · LangSmith 可观测性概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/langsmith/observability-concepts.mdx#L38-L38)

```text
if a user request triggers an agent that calls a model, runs a tool, and then calls the model again, all of those runs belong to the same trace. Runs are bound to a trace by a unique trace ID.
```

- [E3 · LangSmith 可观测性概念](https://github.com/langchain-ai/docs/blob/a28c75411093fdc0e57b03c1d6486ba78f005f51/src/langsmith/observability-concepts.mdx#L44-L44)

```text
Each turn is recorded as its own trace. To group traces into a thread, pass a `thread_id` metadata key with a unique value.
```
