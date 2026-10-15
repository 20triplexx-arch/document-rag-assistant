"""Local task understanding. Full question is retained; no classifier model call."""
import re
from .core import query_terms,tokenize,CorpusError
from .limits import MAX_QUESTION_CHARS

PLANNER_VERSION="topics-facets-versions-v2"
TOPIC_PATTERNS={
    "tools":r"工具|函数调用|function.?call|\btools?\b|参数|tool.?call",
    "memory":r"记忆|记住|上周.*聊|偏好|持久会话|\bmemory\b|namespace|checkpointer|跨会话|sqlite",
    "rag":r"\brag\b|检索|retriev|bm25|向量|embedding|rerank|产品手册|文档问答",
    "planning":r"规划|计划|拆解|\bplanning\b|\breact\b|plan.and|todo|deep.?agents?",
    "context":r"上下文|\bcontext\b|历史|消息|\btrim\b|\bsummar|\bdelete\b",
    "mcp":r"\bmcp\b|model context protocol|协议版本",
    "multi_agent":r"多.?agent|多智能体|多.?智能体|子.?agent|subagents?|handoffs?|总控|团队|多.?代理",
    "observability":r"可观测|观测|诊断|故障|调试|排错|\btrac|\bruns?\b|evaluation|评估|评测|langsmith",
}
ALIASES={
    "tools":"tools tool function calling",
    "memory":"memory short-term long-term persistence thread namespace store",
    "rag":"rag retrieval retriever knowledge documents",
    "planning":"planning plan react tasks todo",
    "context":"context messages history",
    "mcp":"mcp protocol host client server",
    "multi_agent":"multi-agent subagents handoffs supervisor coordination",
    "observability":"observability tracing trace run evaluation diagnostics",
}
LEXICON=[
    (r"记住|偏好|用户事实","semantic memory user preferences"),(r"短期|短时","short-term thread checkpointer"),
    (r"长期|长时|上周|跨会话","long-term namespace store"),(r"命名空间","namespace"),(r"会话|讨论","session thread"),
    (r"工具调用|参数生成","tool calling arguments"),(r"参数","arguments parameters input"),(r"校验|schema","schema validation"),(r"错误|异常|除零","error exception ZeroDivisionError"),
    (r"计算器","calculator math"),(r"持久会话|SQLite","DatabaseSessionService sqlite sessions"),
    (r"函数工具|function tools","function tools"),(r"混合检索|hybrid","hybrid_search rerank_chunks embedding BM25"),
    (r"重排","rerank reranker"),(r"两步|2.step","2-step"),(r"机制|过程|流程","mechanism workflow"),
    (r"控制权|转接","handoffs control state"),(r"子任务|子.?agent","subagents task isolated"),
    (r"研究|调研","research"),(r"旅行|行程","travel itinerary planning"),(r"总结|摘要","summarization summary"),
    (r"裁剪|修剪","trim messages"),(r"删除","delete remove"),(r"长历史|所有历史|对话.*长","long conversation history"),
    (r"资源","resources"),(r"提示模板","prompts"),(r"能力","capabilities"),(r"版本","version"),
    (r"有状态","stateful session initialization"),(r"无状态","stateless request"),(r"客户端","client"),(r"服务端|服务器","server"),(r"主机|宿主","host"),
    (r"输入|输出","input output"),(r"准确|正确|答错|错误答案","correctness grounding evaluation"),
    (r"延迟|耗时","latency"),(r"费用|成本","cost tokens"),(r"故障诊断","failure diagnostics patterns"),
    (r"记忆泄漏|串号","memory leak multi-tenant interference"),(r"原文|证据","grounding retrieved documents evidence"),
    (r"索引","index"),(r"切分|切块","chunk segmentation"),(r"路由","routing"),(r"权限|确认","permissions authorization consent confirmation"),
    (r"模型","model models"),(r"宿主","host"),(r"执行结果|收到.*结果","ToolMessage result response"),(r"循环","loop"),
    (r"谁|控制","control controlled"),(r"作用|各做什么|分别负责","components responsibilities"),
    (r"传递|共享|广播","share member interactions return"),(r"状态","state"),(r"生命周期","life-cycle lifecycle"),
    (r"代价|成本|取舍","performance tradeoffs cost"),(r"完整历史|最终输出|返回方式","outputs final output"),
    (r"每次|所有|一次","call invocation"),(r"机制|负责","overview concepts"),
]
STOP={"什么","怎么","如何","有什","么区","区别","教材","两本","这两","请问","解释","案例","举例","示例","请说","请给","为什么","哪些","分别","the","a","and","or","to","in","of","is","are","what","how","why"}

def expand_terms(text,*,topics=True):
    terms,_=query_terms(text)
    extra=[]
    for pattern,words in LEXICON:
        if re.search(pattern,text,re.I):extra.append(words)
    if topics:
        for topic,pattern in TOPIC_PATTERNS.items():
            if re.search(pattern,text,re.I):extra.append(ALIASES[topic])
    terms.update(tokenize(" ".join(extra)))
    return {t for t in terms if len(t)>1 and t not in STOP}

def question_plan(question):
    if not question.strip() or len(question)>MAX_QUESTION_CHARS:raise CorpusError("问题长度无效。")
    topics=[t for t,p in TOPIC_PATTERNS.items() if re.search(p,question,re.I)]
    versions=list(dict.fromkeys(re.findall(r"\b20\d{2}-\d{2}-\d{2}\b",question)))
    code=bool(re.search(r"代码|源码|python|静态阅读|函数.*(?:排错|除零)|(?:具体|实际)实现|implementation|debug|traceback",question,re.I))
    kind="debug" if re.search(r"排错|故障|答错|异常|debug|traceback",question,re.I) else "comparison" if re.search(r"区别|差别|比较|取舍|vs\.?|versus|同一件|怎样选",question,re.I) else "implementation" if code else "operation" if re.search(r"怎样|怎么|如何|步骤|should|how to",question,re.I) else "mechanism" if re.search(r"机制|过程|为什么|边界|负责|顺序",question,re.I) else "definition"
    facets=[part.strip() for part in re.split(r"[？?；;\n]+|(?:[。！!]\s*)",question) if part.strip()]
    # Windows retain the tail of long queries; E5 adds tokenizer-bound windows as well.
    windows=[question[i:i+900] for i in range(0,len(question),780)]
    if not facets:facets=[question]
    from .provenance import named_symbols
    return {"version":PLANNER_VERSION,"question":question,"topics":topics,"kind":kind,"named_symbols":named_symbols(question),
        "subquestions":facets,"query_windows":windows,"needs_code":code,
        "applicable_versions":versions or (["2026-07-28"] if "mcp" in topics else []),
        "explicit_versions":bool(versions),"version_comparison":len(versions)>1,
        "necessary_facets":necessary_facets(question),"audience":"有基本编程能力的 Agent 初学者"}

def necessary_facets(question):
    """Task-specific coverage concepts, never question IDs / gold spans / rankings."""
    rules=[
      (r'(?s)(?=.*(?:记忆|偏好|memory))(?=.*(?:后台|background))', 'memory_background',r'in the background',None),
      (r'(?s)(?=.*(?:记忆|偏好|memory))(?=.*(?:热路径|hot.path|取舍))', 'memory_hot_path',r'in the hot path',None),
      (r'(?s)(?=.*(?:MCP|协议))(?=.*(?:发现|discover|能力.*入口))', 'mcp_discovery',r'capability negotiation',r'server/discover'),
      (r'(?s)(?=.*(?:总控|supervisor))(?=.*(?:历史|输出|报告))', 'supervisor_outputs',r'subagent outputs',None),
      (r"模型.*宿主|完整过程.*工具|工具.*完整过程", "model_choice",r"正文|agent loop|工作流程",r"model.*(?:decid|select)|模型.*(?:选择|决定)"),
      (r"模型.*宿主|完整过程.*工具|工具.*完整过程", "execution",r"agent loop|工作流程|工具调用|tool execution",r"(?s)model call.*tool execution|模型.*(?:执行|运行).*工具"),
      (r"收到.*执行结果|结果.*模型|模型.*结果", "tool_result",r".*",r"(?s)ToolMessage.*(?:matching|匹配).*tool_call_id"),
      (r"参数.*schema|schema.*参数|参数.*上下文", "argument_schema",r"definition|schema|参数",None),
      (r"runtime|注入|运行时|schema.*上下文|上下文.*schema|哪些.*模型生成", "runtime_injection",r"access state",None),
      (r"runtime|运行时|参数.*上下文|上下文.*参数", "runtime_components",r"access context",r"State.*Context|State|Store"),
      (r"短期.*长期|thread.*namespace", "short_memory",r"short.term memory|正文",r"short.term|短期"),
      (r"短期.*长期|thread.*namespace", "long_memory",r"long.term memory|正文",r"long.term|长期"),
      (r"存什么|何时写入|何时读出来", "semantic_memory",r"semantic memory",None),
      (r"存什么|何时写入|何时读出来", "memory_write_hot",r"in the hot path",None),
      (r"存什么|何时写入|何时读出来", "memory_write_background",r"in the background",None),
      (r"存什么|何时读出来", "memory_search",r"collection",r"search"),
      (r"产品手册|2.step|agentic.*差别", "external_retrieval",r"正文|rag architectures|2.step rag|agentic rag",r"Retrieval|RAG|检索"),
      (r"trim|delete|summar|对话.*长", "memory_limit",r"manage short.term memory|管理.*记忆",None),
      (r"trim|delete|summar|对话.*长", "trim_delete",r"common patterns|trim messages|delete messages",None),
      (r"trim|delete|summar|对话.*长", "summarize",r"summarize messages|summarization",None),
      (r"上下文工程.*控制|模型上下文.*工具上下文", "context_control",r"what you can control|overview$",None),
      (r"上下文工程.*控制|上下文工程到底", "context_definition",r"why do agents fail",None),
      (r"选择输入|完整历史|输出上下文|返回方式|总控上下文", "subagent_inputs",r"subagent inputs|正文",None),
      (r"选择输入|完整历史|输出上下文|返回方式|总控上下文", "subagent_outputs",r"subagent outputs",None),
      (r"选择输入|输出上下文|广播", "history_filter",r"context engineering",r"not pass all|full subagent|上下文.*(?:筛|过滤)"),
      (r"subagents.*handoffs|handoffs.*subagents|怎样选.*subagents|控制权", "subagents",r"正文|when to use",r"subagents"),
      (r"subagents.*handoffs|handoffs.*subagents|怎样选.*subagents|控制权", "handoffs",r"正文|when to use",r"handoffs"),
      (r"subagents.*handoffs|handoffs.*subagents|怎样选.*subagents|控制权", "subagent_boundary",r"when to use",r"subagents"),
      (r"多.*一定|值得拆分|复杂度.*上下文", "multi_need",r"正文|why use",r"multi.agent"),
      (r"多.*一定|值得拆分|复杂度.*上下文", "multi_cost",r"performance comparison$|成本|性能",None),
      (r"多.*一定|值得拆分|复杂度.*上下文", "multi_conditions",r"why.*multi.agent",None),
      (r"host.*client.*server", "host",r"core components / host$",None),
      (r"host.*client.*server", "client",r"core components / clients$",None),
      (r"host.*client.*server", "server",r"core components / servers$",None),
      (r"MCP.*版本|版本.*能力|版本和能力|规范.*能力", "capabilities",r"capability negotiation",None),
      (r"tools.*resources.*prompts", "tools_primitive",r"user interaction model",r"tools"),
      (r"tools.*resources.*prompts", "resources_primitive",r"user interaction model",r"resources"),
      (r"tools.*resources.*prompts", "prompts_primitive",r"user interaction model",r"prompts"),
      (r"trace.*run|run.*thread|记录.*关系", "runs",r"runs$",None),
      (r"trace.*run|run.*thread|记录.*关系", "traces",r"traces$",None),
      (r"trace.*run|run.*thread|记录.*关系", "threads",r"threads$",None),
      (r"tracing.*evaluation|线上.*离线", "trace_structure",r"how langsmith structures",r"runs.*trace|trace.*runs"),
      (r"tracing.*evaluation|线上.*离线", "eval_workflow",r"评估.*智能体$",None),
      (r"tracing.*evaluation|HTTP|正确", "quality_metrics",r"key metrics|关键指标",None),
      (r"初始化.*会话|SQLite.*初始化", "session_storage",r"\[code\].*module statement",r"db_url"),
      (r"初始化.*会话|SQLite.*初始化", "session_runner",r"\[code\].*module statement",r"Runner\("),
      (r"信息如何传递|怎样.*传递", "communication",r"\[code\]",r"share_member_interactions|messages|return|yield"),
      (r"ReAct.*先规划|ReAct.*Plan.and", "react_mechanism",r"react.*工作流程|react$|本章小结",None),
      (r"ReAct.*先规划|ReAct.*Plan.and", "plan_mechanism",r"plan.and.solve.*工作原理|本章小结",None),
      (r"ReAct.*先规划|ReAct.*Plan.and", "paradigm_boundary",r"本章小结",None),
    ]
    return [{"id":name,"section_pattern":section,"body_pattern":body} for trigger,name,section,body in rules if re.search(trigger,question,re.I)]

FACET_RULES=[
 (r"定义|什么是|是什么|各做什么|负责|有.*区别|差别|同一件",r"正文|overview|concept|core components|patterns|工作原理|工作流程|基础知识|核心|特点"),
 (r"参数|schema|注入",r"definition|schema|access context|access state|context|input|参数"),
 (r"生成.*执行结果|模型.*宿主|完整过程",r"agent loop|tool execution|core components|工作流程|工具调用|how.*works"),
 (r"短期|长期|thread|namespace|存什么|读出来|写入",r"short.term memory|long.term memory|memory storage|writing memories|semantic memory|正文"),
 (r"trim|delete|summar|长.*历史|对话.*长",r"manage short.term memory|common patterns|trim messages|delete messages|summarize messages"),
 (r"子.*输入|选择输入|完整历史|输出上下文|返回方式|总控上下文",r"subagent inputs|subagent outputs|context engineering|正文"),
 (r"subagents.*handoffs|怎样选.*subagents|控制权",r"正文|when to use|key characteristics|context engineering|patterns"),
 (r"多.*一定|值得拆分|复杂度|成本.*协调",r"正文|why use|performance comparison|key characteristics"),
 (r"host|client|server|主机|客户端|服务端",r"core components|architecture|正文"),
 (r"版本|能力|stateless|stateful|状态.*请求",r"capability negotiation|statelessness|正文|clients|_meta"),
 (r"resources|prompts|tools.*三个|谁控制",r"user interaction model|正文"),
 (r"trace.*run|run.*thread|记录.*关系",r"runs$|traces$|threads$|structures|正文"),
 (r"tracing|evaluation|评估|正确|HTTP",r"评估|准确性|请求错误|observability|failure patterns|traces|正文"),
]
def relevant_sections(question):
    return [pattern for trigger,pattern in FACET_RULES if re.search(trigger,question,re.I)]

def followups_for(question):
    plan=question_plan(question);topic=question[:100]
    if plan["needs_code"]:
        return [{"label":"检查失败分支","question":f"围绕「{topic}」，失败时怎样处理？请区分源码已经实现的分支和仍需验证的条件。"},
                {"label":"解释输入输出","question":f"围绕「{topic}」，请按实际源码解释输入、输出和关键状态如何变化。"}]
    if plan["kind"]=="comparison":
        return [{"label":"按场景选方案","question":f"围绕「{topic}」，请给出一个具体使用场景并说明有依据的选择条件。"},
                {"label":"看实现片段","question":f"围绕「{topic}」，能否用已收录的 Python 代码说明关键差异？没有代码依据时指出缺口。"}]
    return [{"label":"看具体例子","question":f"围绕「{topic}」，请用资料中的具体例子解释机制，说明适用条件。"},
            {"label":"找常见失败","question":f"围绕「{topic}」，容易在哪一步失败？请给出有依据的检查办法。"}]
