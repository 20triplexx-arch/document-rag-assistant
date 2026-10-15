"""Source-first AI-assisted annotations. Run before retrieval tuning, then freeze."""
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.core import verified_corpus,validate_text
from study_rag.qa_budget import QABudget

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"data/qa-20261014-v1"
M,C,S,raws=verified_corpus(DATA,DATA/"index.sqlite3")
T={s.source_id:validate_text(raw) for s,raw in raws}
MEM="qa-9042714eebfb8da64b51"; SHORT="qa-d9f81f001fabc5f9fa2f"; LONG="qa-bd2e9e285f5a6982fc85"
TOOLS="qa-05e43477ec0dfab5456d"; CALC="qa-fbc28a28db62cb94f8b1"; PERSIST="qa-aa3e61c3d14e41bdc6c2"
RAG="qa-588a71b992e7e61bbaeb"; HYBRID="qa-585eb13ebebd2013e3d8"; DIAG="llm-case-9d7b5d6cd1b06a7a"
REACT="hello-605cfb4730042c4c"; DEEP="qa-ec2757eeda3c3c49184d"; TEAM="qa-8df2ad124ccee273ac98"
CONTEXT="qa-c152efb113ef320812a3"; MULTI="qa-d9910fffbd3cbf2f488a"; SUB="qa-a90e0e1e586f36bcedee"; HAND="qa-5ad9c8977a6b0a2615c4"
ARCH="qa-c1a7878e44b380fb7970"; OLD="qa-0fe31ec465e42fae624c"; MT="qa-fe4b921a1300b3742de4"; MR="qa-a9a89eaaaafff7b92d60"; MP="qa-cd67b197ee197847de89"
OBS="qa-7fd3f30d4222b05941f0"; HF="huggingface-agents-5f63bb7146d2b015"; BROWSER="qa-684555ca0a7f7cd05b8a"; CRAG="qa-99be7d88483f4708828d"

def s(sid,anchor,*,end=None,lines=1,kind="prose"):
    text=T[sid]; pos=text.index(anchor)
    start=text.rfind("\n",0,pos)+1 if kind=="code" else pos
    finish=text.index(end,pos)+len(end) if end else pos
    if end:
        finish=text.find("\n",finish)
        if finish<0:finish=len(text)
    else:
        finish=start
        for _ in range(lines):
            idx=text.find("\n",finish)
            finish=len(text) if idx<0 else idx+1
    while finish>start and text[finish-1]=="\n":finish-=1
    if kind=="prose":
        import re
        url=re.search(r"https?://",text[start:finish])
        if url:
            url_pos=start+url.start();bracket=text.rfind("[",start,url_pos)
            finish=bracket if bracket>=start else url_pos
            while finish>start and text[finish-1] in " ([":finish-=1
    return {"source_id":sid,"start_char":start,"end_char":finish,"start_line":text.count("\n",0,start)+1,
        "end_line":text.count("\n",0,finish-1)+1,"quote":text[start:finish],"kind":kind,
        "rationale":"AI 辅助逐字复核固定原文；该位置支持此必要要点，未使用检索排名倒推。"}

def p(answer,*supports):return {"answer":answer,"supports":list(supports)}
G={
"TOOL-D1":[p("模型选择工具并生成输入参数，而不是亲自执行函数",s(TOOLS,"Under the hood")),p("宿主执行工具并返回结果，模型调用与工具执行形成循环",s(CONTEXT,"**Model call**"),s(CONTEXT,"**Tool execution**")),p("工具请求与结果须对应，工具消息携带匹配的 tool_call_id",s(HAND,"**Why include a `ToolMessage`?**"))],
"TOOL-D2":[p("纠正前提：实际函数为 calculate_basic_math，不是 divide；收到表达式字符串",s(CALC,"def calculate_basic_math",kind="code")),p("函数捕获 ZeroDivisionError 并返回 error/status，不是抛出裸异常",s(CALC,"except ZeroDivisionError:",lines=6,kind="code")),p("白名单过滤与通用异常捕获位于函数体；不能据此断言框架没有参数校验",s(CALC,'allowed_chars =',lines=2,kind="code"),s(CALC,"except Exception as e:",lines=6,kind="code"))],
"TOOL-D3":[p("工具的类型标注定义输入 schema，用于模型生成参数",s(TOOLS,"Type hints are **required**")),p("runtime 由 ToolNode 自动注入，不进入发给模型的 schema",s(TOOLS,"At call time, @[`ToolNode`] injects")),p("运行时 context 提供不可变身份配置，state/store 提供当前或跨会话数据",s(TOOLS,"**Context** | Immutable configuration"),s(TOOLS,"**State** | Short-term memory"),s(TOOLS,"**Store** | Long-term memory"))],
"TOOL-A1":[p("模型控制工具选择不等于获得执行权限",s(MT,"Tools in MCP are designed",lines=3)),p("应用应让人可以拒绝调用，并提供暴露工具与调用提示、确认",s(MT,"be a human in the loop",lines=1),s(MT,"Present confirmation prompts",lines=2)),p("host 负责权限、安全策略与用户授权决策",s(ARCH,"Enforces security policies",lines=2))],
"MEM-D1":[p("短期记忆属于 thread，状态由 checkpointer 持久化并按步骤读取/更新",s(MEM,"* [Short-term memory]")),p("长期记忆跨 thread/session，用自定义 namespace 存储用户或应用数据",s(MEM,"* [Long-term memory]")),p("namespace/key 是组织记忆的地址，常包含 user/org ID",s(LONG,"Each memory is organized"))],
"MEM-D2":[p("初始化 DatabaseSessionService 指向 sqlite:///sessions.db，Runner 使用同一服务",s(PERSIST,"session_service = DatabaseSessionService(",lines=3,kind="code"),s(PERSIST,"runner = Runner(",lines=5,kind="code")),p("session_id 从 user_id 派生，get_session 使用 app_name、user_id、session_id",s(PERSIST,'session_id = f',lines=9,kind="code")),p("未找到会话时 create_session 创建初始状态，run_async 使用该会话",s(PERSIST,"if not session:",lines=9,kind="code"))],
"MEM-D3":[p("长期记忆保存交互产生的用户事实，RAG 在查询时取相关外部知识；二者目标不同但可共同用于上下文",s(MEM,"For AI agents, semantic memory is often used"),s(RAG,"Retrieval addresses these problems")),p("记忆可在响应路径或后台写入，写入时机有延迟/新鲜度取舍",s(MEM,"Creating memories during runtime offers"),s(MEM,"Creating memories as a separate background task offers")),p("长期记忆支持按 namespace/key 保存和搜索，查询过程可以使用检索",s(LONG,"LangGraph stores long-term memories"),s(MEM,"Working with document collections also shifts"))],
"MEM-A1":[p("namespace 采用用户或组织标识，key 标识具体记忆",s(LONG,"Each memory is organized")),p("只按当前用户 namespace 读写；示例 namespace 包含 user_id/application_context",s(MEM,'namespace = (user_id, application_context)',lines=1,kind="code"),s(MEM,"store.search(",lines=3,kind="code")),p("用户标识由运行时 context 注入，不交给模型随意生成",s(TOOLS,"At call time, @[`ToolNode`] injects"),s(TOOLS,"**Context** | Immutable configuration"))],
"RAG-D1":[p("2-step 总是先检索后生成，Agentic 由模型决定何时/如何检索",s(RAG,"| **2-Step RAG**"),s(RAG,"| **Agentic RAG**")),p("Agentic 在推理循环中选择检索工具，适合多个知识工具",s(RAG,"**Agentic Retrieval-Augmented Generation")),p("2-step 模型调用有已知上限，延迟较可预测，但检索/网络延迟仍可能变化",s(RAG,"**Latency**:"))],
"RAG-D2":[p("实际 perform_search 调用 hybrid_search(num_results=10)，读取对应 chunks 再 rerank",s(HYBRID,"chunk_ids, scores = hybrid_search",lines=5,kind="code")),p("配置包含 embedding 模型与 Cohere reranker，不应编造 BM25 权重或底层实现",s(HYBRID,"embedder_normalize=True",lines=4,kind="code")),p("生成分支的 rag(search=hybrid_search) 是另一次调用；不能说一定复用先前 reranked_chunks",s(HYBRID,"response_stream = rag(",lines=6,kind="code"))],
"RAG-D3":[p("先看原文是否被索引/切分正确，再看检索结果语义相关性",s(DIAG,"| P02"),s(DIAG,"| P03"),s(DIAG,"| P04")),p("证据存在但答案与它矛盾是 grounding drift，与没检索到事实不同",s(DIAG,"| P01")),p("案例是模式库加模型诊断建议，不是已经测量的检查/指标",s(DIAG,"The script asks an LLM",lines=2),s(DIAG,"1. The script builds",lines=9))],
"RAG-A1":[p("逐个文档让模型给 yes/no，yes 入 filtered_docs；否定设置 web search",s(CRAG,'if score.get("score") == "yes":',lines=7,kind="code")),p("run_web_search=Yes 走 transform_query，否则 generate；改写后接 web search",s(CRAG,'if search == "Yes":',lines=9,kind="code")),p("打分异常保留该文档而非可靠判为相关；示例路径不代表生产质量保证",s(CRAG,"Error grading document",lines=5,kind="code"))],
"PLAN-D1":[p("ReAct 以思考/行动/观察循环，用工具结果修正后续思考",s(REACT,"ReAct的巧妙之处")),p("先规划后执行先拆分计划，适合逻辑路径较确定任务；经典实现不自动重规划",s(REACT,"2. Plan-and-Solve:我们实现")),p("变动工具结果适合动态观察与纠错，静态计划需额外设计重规划而非宣称已有",s(REACT,"1. ReAct:我们构建"))],
"PLAN-D2":[p("计划是可选的 write_todos/状态跟踪；v0.7 起不默认启用",s(DEEP,"Task planning is an opt-in"),s(DEEP,"Starting in v0.7")),p("文件系统/摘要/卸载为长任务管理上下文，后端可配置",s(DEEP,"The harness provides a configurable virtual filesystem"),s(DEEP,"**Compression**:")),p("task 工具创建隔离子任务并返回报告；todo 状态只是 agent state，不能证明外部结果",s(DEEP,"Tasks support status tracking"),s(DEEP,"The harness includes a built-in `task` tool"))],
"PLAN-D3":[p("Team coordinate 模式指定成员；总控通过专业 Agent 做航班、住宿、餐饮、预算与行程",s(TEAM,'mode="coordinate"',lines=11,kind="code")),p("团队开启 share_member_interactions/show_members_responses，说明交互共享配置而非运行保证",s(TEAM,"share_member_interactions=True",lines=2,kind="code")),p("Itinerary Specialist 负责每日行程与时间/交通安排，但其他成员实现未全部导入",s("qa-181f6bc64f7c785ae1ca","Create perfectly balanced day-by-day",lines=6,kind="code"))],
"PLAN-A1":[p("任务计划可选，保存状态跟踪；不能当成完成证明",s(DEEP,"Tasks support status tracking")),p("中间大结果通过文件/摘要卸载，跨窗口继续任务",s(DEEP,"**Compression**:"),s(DEEP,"Together, these mechanisms support")),p("隔离子任务返回报告，总控汇总；同步/异步需要按结果依赖选择",s(DEEP,"Two subagent types are available:",lines=1))],
"CTX-D1":[p("上下文工程给模型合适的信息、工具与格式",s(CONTEXT,"**Context engineering** is providing")),p("model context 控制指令、历史、工具与输出格式",s(CONTEXT,"**[Model Context]")),p("tool context 控制读写 state/store/runtime，lifecycle 控制摘要/guardrails/logging等步骤间行为",s(CONTEXT,"**[Tool Context]"),s(CONTEXT,"**[Life-cycle Context]"))],
"CTX-D2":[p("长历史可能超窗口，旧/无关内容分散注意并增加延迟和成本",s(MEM,"Conversation history is the most common")),p("trim 控制模型输入，delete 永久修改 graph state",s(SHORT,"Remove first or last N messages"),s(SHORT,"Delete messages from LangGraph state permanently")),p("摘要用压缩内容替换旧历史；修剪/删除可能丢信息",s(SHORT,"Summarize earlier messages in the history"),s(SHORT,"The problem with trimming or removing messages"))],
"CTX-D3":[p("输入上下文按子任务选，query-only 与全历史具有隔离/延续工作的取舍",s(SUB,"`some_logic` controls how much context")),p("输出需要明确回传结果，默认总控只看到 final output，可代码补充 state keys",s(SUB,"**Prompt the sub-agent**"),s(SUB,"**Format in code**")),p("广播原始历史会引入无关内容、混乱与 token 开销，可改为摘要",s(HAND,"**Why not pass all subagent messages?**"))],
"CTX-A1":[p("当前任务决定模型消息与上下文选择，旧/跑题内容应过滤",s(CONTEXT,"Control what goes into each model call"),s(MEM,"Conversation history is the most common")),p("可保存状态但调整单次模型可见消息；历史回答不等于当前问题证据",s(CONTEXT,"What the LLM sees for a single call")),p("RAG 提供查询时外部知识，不把本项目行为说成官方文档已验证",s(RAG,"Retrieval addresses these problems"))],
"MCP-D1":[p("host 管理 clients、安全授权与上下文；client 对单个 server；server 暴露资源工具提示",s(ARCH,"The host process acts",lines=8),s(ARCH,"Each client is created",lines=7),s(ARCH,"Servers provide specialized",lines=7)),p("默认 2026-07-28 stateless，每请求携带自己的版本与能力",s(ARCH,"host can run multiple client instances",lines=2)),p("客户端能力在 request _meta，服务器可由 server/discover 发现",s(ARCH,"servers declare their supported features",lines=5))],
"MCP-D2":[p("2025-11-25 是 stateful session，以初始化声明会话能力",s(OLD,"isolating concerns. Built on JSON-RPC",lines=2),s(OLD,"servers explicitly declare their supported features",lines=2)),p("2026-07-28 是 stateless，各请求携带协议版本/客户端能力",s(ARCH,"host can run multiple client instances",lines=2)),p("新规范 server/discover 返回支持版本/能力；不得混用旧 initialize 会话握手",s(ARCH,"servers declare their supported features",lines=5))],
"MCP-D3":[p("tools 模型控制，调用外部系统执行计算/动作",s(MT,"Tools in MCP are designed",lines=3)),p("resources 由应用选择上下文，提供文件/数据库等数据",s(MR,"Resources in MCP are designed",lines=2),s(MR,"resources to clients. Resources allow",lines=2)),p("prompts 用户选择结构化消息模板，可以带定制参数",s(MP,"Prompts are designed",lines=3),s(MP,"templates to clients. Prompts allow",lines=3))],
"MCP-A1":[p("案例通过 MCPApp 与 browser Agent 指定 playwright server，初始化后 attach_llm",s(BROWSER,'st.session_state.mcp_app = MCPApp',kind="code"),s(BROWSER,'server_names=["playwright"]',lines=6,kind="code")),p("可见代码 list_tools 后调用工具，使用包装器不证明协议版本兼容性",s(BROWSER,"tools = await st.session_state.browser_agent.list_tools()",lines=2,kind="code"))],
"MULTI-D1":[p("subagents 总控把子 Agent 当工具调用，返回结果后总控继续决策",s(SUB,"In the **subagents** architecture")),p("handoffs 通过持久状态变量改变配置/路由，可在不同 Agent 或单 Agent 内转接",s(HAND,"In the **handoffs** architecture")),p("子任务/中心控制适合 subagents，直接用户交互与多阶段状态流适合 handoffs",s(SUB,"Use the subagents pattern"),s(HAND,"Use the handoffs pattern"))],
"MULTI-D2":[p("默认子 Agent 无状态隔离，总控保存会话；可以显式给子 Agent 传历史",s(SUB,"In the **subagents** architecture"),s(SUB,"You can also pass the main")),p("默认总控只见最终输出，遗漏结果是具体失败模式",s(SUB,"**Prompt the sub-agent**")),p("可用代码返回额外 state 与最终 ToolMessage，而非自动广播完整历史",s(SUB,"**Format in code**"))],
"MULTI-D3":[p("复杂任务也可能由一个具备合适工具和提示的 Agent 完成",s(MULTI,"Multi-agent systems coordinate specialized")),p("工具过多误选、专门知识/大量上下文或顺序约束时拆分有价值",s(MULTI,"Multi-agent patterns are particularly valuable")),p("多次模型调用和 token 消耗增加延迟/成本；隔离上下文有取舍",s(MULTI,"**Model calls**:"),s(MULTI,"**Tokens processed**:"))],
"MULTI-A1":[p("无直接用户交互的研究子任务由总控协调适合 subagents",s(SUB,"Use the subagents pattern")),p("专家直接跟用户交互、逐步收集信息与状态变化适合 handoffs",s(HAND,"Use the handoffs pattern")),p("前者输入/输出可过滤，后者转接要保留匹配工具请求/响应并控制历史",s(SUB,"`some_logic` controls how much context"),s(HAND,"When handing off between agents",lines=5))],
"OBS-D1":[p("run 是单次工作单元，模型/工具/检索都可以成为 run",s(OBS,"A _run_ represents",end="If you are familiar")),p("trace 是一次操作的一组 runs，模型-工具-模型属于同一trace",s(OBS,"A _trace_ is a collection")),p("thread 将多轮 trace 连接，每轮各自记录 trace",s(OBS,"A _thread_ is a sequence"))],
"OBS-D2":[p("tracing 记录真实步骤的输入输出、工具和模型行为，帮助定位过程",s(OBS,"In LangSmith, every unit of work")),p("离线评估用数据/测试判断表现，补充运行观测",s(HF,"可观测性为我们提供了指标"),s(HF,"AI 智能体的评估有两类")),p("请求成功只是错误率维度，正确性要按成功标准单独检查",s(HF,"**请求错误：**"),s(HF,"**准确性：**"))],
"OBS-D3":[p("诊断检索段被切断/缺失/旧索引，与证据在场但生成矛盾区分",s(DIAG,"| P01"),s(DIAG,"| P02"),s(DIAG,"| P04")),p("上下文丢失是 P08，链式约束漂移 P06，不是单一相似度指标",s(DIAG,"| P08"),s(DIAG,"| P06")),p("实际脚本分类模式并建议结构修复；没有已经跑通的分阶段测量结果",s(DIAG,"1. The script builds",lines=9))],
"OBS-A1":[p("把每次模型、工具、检索调用作为 run 放进同一trace，按序看中间信息",s(OBS,"In LangSmith, every unit of work"),s(OBS,"A _trace_ is a collection")),p("先核对索引/检索/路由/切块，再核对答案是否与检索原文矛盾",s(DIAG,"| P01"),s(DIAG,"| P02"),s(DIAG,"| P04"),s(DIAG,"| P05")),p("不能以 HTTP 或总耗时代替准确性评估，观察工具错误、反馈与目标事实",s(HF,"**准确性：**"),s(HF,"**请求错误：**"))]
}
MISSING={
"TOOL-D2":"登记源码中没有 divide 函数；框架的完整参数校验链和安全执行保证未纳入这些源码。",
"RAG-D2":"该实现调用第三方 hybrid_search，没有展开底层 BM25 实现、融合权重或 reranker 与最终生成上下文的实测对应关系。",
"RAG-D3":"案例提供模式诊断，不提供已经执行的检索/生成逐阶段指标或生产测量结果。",
"PLAN-D3":"部分成员只在 team.py 导入，未收录其全部实现；SDK内部消息共享过程和实际效果未运行验证。",
"MEM-A1":"命名空间组织不能单独证明鉴权/数据访问安全；需要服务端可信身份、访问检查与多用户运行测试。",
"MCP-A1":"登记实现未固定 MCP 协议/SDK版本，缺少配置锁定、协议请求元数据与运行握手/兼容性证据。",
"OBS-D3":"诊断脚本不是实际 pipeline 分阶段指标采集器，也没有已经运行通过的诊断证据。"
}
ALL_SUPPORTS={"TOOL-D1-P2","TOOL-D2-P3","TOOL-D3-P3","MEM-D2-P1","MEM-D3-P1","MEM-D3-P2","MEM-D3-P3",
    "RAG-D1-P1","RAG-D3-P1","PLAN-D2-P1","PLAN-D2-P3","CTX-D1-P3","CTX-D2-P2","CTX-D2-P3","CTX-D3-P2",
    "MCP-D1-P1","MCP-D2-P1","MCP-D3-P2","MCP-D3-P3","MULTI-D1-P3","MULTI-D2-P1","MULTI-A1-P3",
    "OBS-D2-P2","OBS-D2-P3","OBS-D3-P1","OBS-D3-P2","OBS-A1-P2","OBS-A1-P3","MCP-A1-P1"}

def main():
    scenarios=json.loads((ROOT/"evals/qa-scenarios-v1.json").read_text(encoding="utf-8"))
    questions=[]
    for q in scenarios["questions"]:
        pts=[{"id":f"{q['id']}-P{i}",**point} for i,point in enumerate(G[q["id"]],1)]
        for point in pts:point["coverage"]="all" if point["id"] in ALL_SUPPORTS else "any"
        question={**q,"group":q["id"].lower(),"book":None,"points":pts,"distractors":[],
            "answerability":"partial" if q["id"] in MISSING else "answerable",
            "missing_information":MISSING.get(q["id"],""),"review_origin":"AI-assisted fixed-source review; no human approval",
            "review_scope":{"source_ids":sorted({span["source_id"] for point in pts for span in point["supports"]}),
                            "basis":MISSING.get(q["id"],"核对上述正文位置；不宣称源文以外的实现或质量结果。")}}
        questions.append(question)
    payload={"schema_version":3,"dataset_version":"agent-qa-v1.1","annotated_on":"2026-10-14",
        "annotation_method":"AI-assisted source-first reading and exact-span checks. No human approval. Frozen before retrieval tuning. v1.1 repairs masked-link annotations and distinguishes conjunctive supports from genuine alternatives; no question/answer point changed to improve retrieval.",
        "scenario_sha256":hashlib.sha256((ROOT/"evals/qa-scenarios-v1.json").read_bytes()).hexdigest(),
        "corpus_version":M["corpus_version"],"documents":len(S),"baseline_chunks":len(C),"questions":questions}
    dest=ROOT/"evals/agent-qa-v1.1.json"
    content=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
    if dest.exists() and dest.read_text(encoding="utf-8")!=content:raise ValueError("Gold already frozen; change dataset version")
    dest.write_text(content,encoding="utf-8")
    QABudget(ROOT/"output/qa-v3/budget.sqlite3").freeze("gold_sha256-v1.1",hashlib.sha256(dest.read_bytes()).hexdigest())
    # Topic matrix is source coverage, independent of retrieval ranks / model answers.
    matrix=[]
    selections={
      "tools":["TOOL-D1","TOOL-D1","TOOL-A1","TOOL-D2","TOOL-D2"],
      "memory":["MEM-D1","MEM-D1","MEM-A1","MEM-D2","MEM-D3"],
      "rag":["RAG-D1","RAG-D1","RAG-D2","RAG-D2","RAG-D3"],
      "planning":["PLAN-D1","PLAN-D2","PLAN-D2","PLAN-D3","PLAN-D1"],
      "context":["CTX-D1","CTX-D1","CTX-D2","CTX-D3","CTX-D2"],
      "mcp":["MCP-D1","MCP-D2","MCP-A1","MCP-A1","TOOL-A1"],
      "multi_agent":["MULTI-D1","MULTI-D1","MULTI-D3","MULTI-D2","CTX-D3"],
      "observability":["OBS-D1","OBS-D1","OBS-D2","OBS-D3","RAG-D3"]}
    for topic,ids in selections.items():
        for facet,qid in zip(("definition","mechanism","boundary","implementation","failure"),ids):
            q=next(q for q in questions if q["id"]==qid)
            matrix.append({"topic":topic,"facet":facet,"review_origin":"AI source review",
                "supports":[{**span,"line_url":f"{S[span['source_id']].source_url}#L{span['start_line']}-L{span['end_line']}"}
                            for point in q["points"] for span in point["supports"]],
                "uncovered":q["missing_information"] or "原文概念与静态示例不证明具体应用的运行质量；远程链接、图片及未登记框架内部实现不在本轮收录范围。"})
    (ROOT/"evals/qa-source-matrix-v1.json").write_text(json.dumps({"date":"2026-10-14","corpus_version":M["corpus_version"],"matrix":matrix},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"questions":len(questions),"points":sum(len(q["points"]) for q in questions),"corpus_version":M["corpus_version"],"gold_sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}))

if __name__=="__main__":main()
