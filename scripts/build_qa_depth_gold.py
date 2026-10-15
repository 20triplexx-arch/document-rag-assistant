"""Freeze source-first holdouts before tuning. Never uses retrieval or a model."""
from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from study_rag.core import verified_corpus, validate_text

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/qa-20261014-v1"
GOLD = ROOT / "evals/qa-depth-v1.json"


def freeze():
    manifest, _, _, contents = verified_corpus(DATA, DATA / "index.sqlite3")
    sources = {s.path: (s, validate_text(raw)) for s, raw in contents}
    tools = "src/oss/langchain/tools.mdx"
    mem = "src/oss/concepts/memory.mdx"
    rag = "src/oss/deepagents/retrieval.mdx"
    deep = "src/oss/deepagents/overview.mdx"
    ctx = "src/oss/langchain/context-engineering.mdx"
    sub = "src/oss/langchain/multi-agent/subagents.mdx"
    obs = "src/langsmith/observability-concepts.mdx"
    basic = "docs/specification/2026-07-28/basic/index.mdx"
    main = "rag_tutorials/hybrid_search_rag/main.py"
    calc = "ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/calculator_agent/tools.py"
    specs = [
        ("tools", "LangChain 工具用 Command 更新当前图时，为什么还要 ToolMessage？写入父图时要求是否相同？", [(tools,780,785,"当前图须提供匹配 tool call ID 的 ToolMessage，否则 ToolNode 报错。"),(tools,856,856,"写父图离开当前图，ToolMessage 要求解除。")]),
        ("tools", "给 LangChain Python 工具自定义 config 和 runtime 两个业务参数会有什么问题？应该怎样取得运行时信息？", [(tools,169,176,"config/runtime 是保留参数名，自定义使用会导致运行错误；运行时信息使用 ToolRuntime。")]),
        ("tools", "LangChain 工具返回字符串、对象和 Command，分别适合什么目的？不要展开其他返回形式。", [(tools,674,678,"字符串供人读，对象提供结构化结果，Command 用于写状态。")]),
        ("tools", "只静态阅读 calculate_basic_math：输入字符串 'a1b'、'1' 和空字符串会分别经过什么分支？这能证明运行安全性吗？", [(calc,18,37,"非法字符被删除；a1b 变成 1，1 保留，均求值并返回浮点结果；空串返回 error。只是静态推断，未运行且不能证明安全。")]),
        ("memory", "用户事实越来越多时，单个 profile 和文档 collection 各有什么维护与检索取舍？", [(mem,62,64,"profile 为统一 JSON，更新须结合旧版本，变大后易出错。"),(mem,70,76,"collection 容易新增窄范围事实，但删除更新、检索和完整关系上下文更复杂。")]),
        ("memory", "semantic memory 和 semantic search 是同一回事吗？请简短区分。", [(mem,52,55,"semantic memory 存储事实和知识；semantic search 按含义寻找内容，两者不是同一概念。")]),
        ("memory", "记住成功操作的 few-shot 示例，与记住智能体执行规则，分别属于哪类记忆？", [(mem,84,87,"情景记忆记录经历，常通过 few-shot 输入输出示例帮助完成任务。"),(mem,108,110,"程序记忆是执行规则，体现在模型权重、代码和提示；实践中更常修改提示。")]),
        ("memory", "偏好写入热路径或后台，各如何影响当次延迟和其他 thread 读到新事实的时间？", [(mem,183,185,"热路径立即可用，但记忆决策增加延迟及多任务负担。"),(mem,191,193,"后台分离主应用延迟；写入频率低可能使其他线程缺少新上下文。")]),
        ("rag", "企业已经有 CRM 知识库，做 RAG 是否必须重新建向量库？有哪些接入办法？", [(rag,19,21,"不必重建；可作为 Agentic RAG 工具，或直接查询后给两步 RAG 提供上下文。")]),
        ("rag", "两步 RAG 的延迟更可预测，是否意味着检索网络再慢也不影响回答时间？", [(rag,141,141,"可预测性假设推理主导，但检索 API、网络和数据库仍影响延迟。"),(rag,146,146,"两步 RAG 固定先检索再生成。")]),
        ("rag", "Agentic RAG 在什么时候检索、怎样检索这两件事上，谁作决策？需要什么基本接入能力？", [(rag,186,189,"智能体在交互推理中决定何时和如何检索；需能访问获取外部知识的工具。")]),
        ("rag", "官方 RAG 架构里的 Hybrid RAG，是否只表示 BM25 与向量分数合并？请解释它的校验环节。", [(rag,429,435,"该架构结合两步与智能体方式，含查询增强、检索验证和回答验证，并非仅关键词与向量融合。")]),
        ("planning", "Deep Agents 的 write_todos 是默认必有的吗？它记录的 completed 能直接当成报告已经验收吗？", [(deep,304,305,"任务规划是 opt-in。"),(deep,319,329,"需传 TodoListMiddleware；状态保存在 agent state，是计划跟踪，不证明报告产物正确。")]),
        ("planning", "Deep Agents 的虚拟文件系统是否必然写入本机磁盘？解释后端选择的边界。", [(deep,118,118,"可选内存状态、本机磁盘、LangGraph store、复合或自定义后端，虚拟文件系统不等于磁盘。")]),
        ("planning", "Deep Agents 文件权限规则多条命中时采用哪条？没有命中怎么办，sandbox execute 也受同一规则约束吗？", [(deep,217,228,"声明顺序首条命中生效，无命中默认允许；不适用于提供任意执行的 sandbox backend。")]),
        ("planning", "Deep Agents 的 skills 与 AGENTS.md memory 在加载时机和上下文占用上如何不同？", [(deep,262,264,"skills 启动读 frontmatter，任务需要时才读完整内容。"),(deep,270,274,"memory 通过 memory 参数传入 AGENTS.md，总是加载并保存到配置后端。")]),
        ("context", "只修改这次模型调用看到的 messages，是否必然删掉持久 state 里的历史？请区分两种上下文。", [(ctx,48,58,"model context 为当次调用的临时视图；可改发送消息而不改 state；持久上下文由工具写入或生命周期钩子改变。")]),
        ("context", "LangChain 的 runtime context、state、store 分别适合保存数据库连接、当前工具结果和跨会话偏好吗？", [(ctx,65,69,"runtime 为会话级静态配置含数据库连接；state 为会话级状态含工具结果；store 跨会话含偏好。")]),
        ("context", "life-cycle context 只负责日志吗？它在模型和工具步骤之间还能改变什么？", [(ctx,1977,1982,"生命周期上下文可摘要、护栏、日志，通过 middleware 更新持久上下文或跳转生命周期步骤。")]),
        ("context", "模型窗口放得下全部聊天记录时，为什么仍可能需要裁剪？", [("src/oss/langchain/short-term-memory.mdx",18,22,"即使窗口可容纳，过期或离题内容也会干扰，增加延迟和成本；可去除陈旧信息。")]),
        ("mcp", "按 MCP 2026-07-28，notification 应该带 id 并等接收方回包吗？", [(basic,159,172,"notification 单向，接收方不得回复，消息不得有 ID。")]),
        ("mcp", "MCP 2026-07-28 中，把同一 stdio 进程当成同一会话并从前一请求继承能力，符合规范吗？", [(basic,184,208,"无状态，每请求自带版本能力等 metadata；连接或进程不代表会话，不能隐含继承。")]),
        ("mcp", "MCP 2026-07-28 校验 JSON Schema 时，遇到远程 $ref 是否应该自动下载？未解析引用可以当成宽松 schema 放行吗？", [(basic,301,310,"不得默认联网解引用；可选模式默认禁用并限制访问；无法解析时应拒绝而非宽松放行。")]),
        ("mcp", "MCP 2026-07-28 的 tools/list 可以因权限不同而返回不同集合吗？可以因为连接不同或上一个请求不同而改变吗？", [("docs/specification/2026-07-28/server/tools.mdx",62,73,"可按请求授权变化，不得因连接或前序请求副作用变化；建议确定顺序。")]),
        ("multi_agent", "LangChain 的 supervisor 和 router 都只是一次分类分发吗？适用行为有何差别？", [(sub,31,37,"supervisor 保持对话并跨轮动态路由；router 通常单步分类且不保持持续会话状态。")]),
        ("multi_agent", "主智能体必须等子任务结果才继续时如何选同步或异步？这里的异步就是 Python async/await 吗？", [(sub,121,134,"依赖结果时适合同步等待；异步后台可继续主对话，这里的异步不等同 Python async/await。")]),
        ("multi_agent", "子智能体明明完成了工具调用，总控却没看到结果，应调整 inputs 还是 outputs？", [(sub,559,559,"inputs 决定子智能体获得哪些上下文。"),(sub,626,629,"outputs 决定总控获得的结果，通常只见最终输出；需提示返回结果或代码补充返回字段。")]),
        ("multi_agent", "Deep Agents 里 mode=isolated 与 mode=fork 有什么区别？能把这种配置直接当成所有 subagents 的通用保证吗？", [(deep,335,344,"Deep Agents 默认隔离新实例，fork 继承父完整历史，最终返回报告；这是该框架的配置，不能推广为所有子智能体。")]),
        ("observability", "一次用户操作先检索再调用模型，LangSmith 应记为一个 run 还是多个 run 和一个 trace？", [(obs,34,38,"每个工作单元独立 run，一次操作的多个 run 归为一个 trace。")]),
        ("observability", "排查多轮对话的嵌套调用与只读消息路径，LangSmith 的 thread 和 trajectory 分别适合什么？", [(obs,44,62,"thread 为多 trace 会话并保留嵌套与时序；trajectory 把会话投影为去重的顺序消息列表。")]),
        ("observability", "在 LangSmith 中要筛选 production 和应用版本，tags 与 metadata 分别是什么形式？", [(obs,98,104,"tags 是字符串标签；metadata 是键值对，可记录环境和版本；均可筛选。")]),
        ("observability", "LangSmith 的 feedback 是绑定 thread 的任意备注吗？它如何表达评分和归属？", [(obs,92,92,"feedback 用 tag 和 score 按标准评价单次 run，绑定唯一 run ID，可连续或离散。")]),
        ("memory", "换个话题：semantic memory 与 semantic search 的区别是什么？", [(mem,52,55,"记忆存事实知识；语义搜索按含义检索，旧 MCP 主题不能污染回答。")], {"prelude":"MCP 2026-07-28 的 host、client、server 分别负责什么？"}),
        ("memory", "它为什么在其他 thread 里可能还读不到刚写入的新偏好？只解释后台方案的时机问题。", [(mem,191,193,"后台写入有触发和频率选择，更新不及时会使其他 thread 缺少新上下文。")], {"prelude":"长期记忆的后台写入方案是什么？"}),
        ("rag", "长期记忆 store、RAG 检索和 MCP server 各解决什么问题？请只比较这三个对象的职责。", [(mem,199,199,"store 组织长期 JSON 记忆。"),(rag,38,40,"RAG 把运行时检索与生成结合。"),("docs/specification/2026-07-28/architecture/index.mdx",76,82,"MCP server 按协议暴露资源、工具和提示等能力。")]),
        ("mcp", "比较 MCP 2025-11-25 与 2026-07-28：省略 $schema 时默认 dialect 是否改变？不支持声明的 dialect 应如何处理？", [("docs/specification/2025-11-25/basic/index.mdx",180,182,"旧版默认2020-12，不支持声明 dialect 应返回错误。"),(basic,291,293,"新版同为2020-12，也要求按声明校验并处理不支持的 dialect。")]),
        ("rag", "Hybrid Search RAG 的 perform_search 是 raglite 导入的函数，所以 rag 一定用它做重排，对吗？请按 Python 源码纠正前提。", [(main,4,5,"导入列表不含 perform_search。"),(main,79,100,"perform_search 是本地定义，并调用 hybrid_search/retrieve_chunks/rerank_chunks。"),(main,186,200,"rag 获得 search=hybrid_search，未显式传 reranked_chunks；内部如何处理未收录。")]),
        ("observability", "现有资料能证明本机这个问答应用今天的实际正确率达到99.9%吗？请给实测结论。", [], {"answerability":"insufficient","missing_information":"本轮教材没有本机应用今天的独立实测数据、题集及正确性判定，不能给实际正确率。"}),
        ("rag", "Hybrid Search RAG 的 README 写一般问题直接走 Claude，实际 main.py 按语义分类问题还是按检索结果选择 fallback？", [("rag_tutorials/hybrid_search_rag/README.md",70,71,"README 按文档问题和一般问题描述。"),(main,186,200,"实现按 perform_search 结果为空或非空选择 fallback/rag，未见语义分类器。")]),
        ("memory", "Deep Agents 的 AGENTS.md memory 与 LangGraph store 中按 namespace/key 存的事实，是同一种默认加载机制吗？", [(deep,270,274,"Deep Agents 传入的 AGENTS.md 总是加载，后端可配置。"),(mem,199,199,"LangGraph store 按namespace/key组织JSON事实；该存储形式本身不证明自动加载所有文档。")]),
    ]
    questions = []
    for i, spec in enumerate(specs, 1):
        topic, question, annotations, *options = spec
        extra = options[0] if options else {}
        points = []
        for j, (path, first, last, expected) in enumerate(annotations, 1):
            source, text = sources[path]
            lines = text.splitlines(keepends=True)
            a = sum(map(len, lines[:first-1])); b = sum(map(len, lines[:last]))
            while b > a and text[b-1].isspace(): b -= 1
            span = {"source_id": source.source_id, "start_char": a, "end_char": b,
                    "start_line": first, "end_line": text.count("\n",0,b-1)+1,
                    "quote": text[a:b], "kind": "code" if path.endswith('.py') else "prose",
                    "line_url":f"{source.source_url}#L{first}-L{last}",
                    "rationale":"AI source-first annotation before tuning; not human approval"}
            points.append({"id":f"P{j}","answer":expected,"supports":[span],"coverage":"all"})
        questions.append({"id":f"DEPTH-A{i:02}","topic":topic,"question":question,"points":points,
                          "answerability":extra.get("answerability","answerable"),
                          "missing_information":extra.get("missing_information",""),
                          "prelude":extra.get("prelude"),"book":None,
                          "review_origin":"AI-assisted raw-source annotation; not human approval"})
    result = {"version":"qa-depth-v1","frozen_on":"2026-10-15","corpus_version":manifest['corpus_version'],
              "documents":len(contents),"questions":questions,
              "note":"New scenario wording and source-first labels, not an independent human benchmark. No retrieval ranking or model output used to label."}
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if GOLD.exists() and GOLD.read_text(encoding='utf-8')!=encoded: raise ValueError('Frozen holdouts changed')
    if not GOLD.exists(): GOLD.write_text(encoded,encoding='utf-8')
    print(json.dumps({"questions":len(questions),"points":sum(len(q['points']) for q in questions),"sha256":hashlib.sha256(GOLD.read_bytes()).hexdigest()}))


if __name__ == '__main__': freeze()
