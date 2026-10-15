"""New source-first scenarios frozen before v4 retrieval tuning; no model/ranking."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import source_view,locator

DATA=ROOT/'data/qa-overhaul-20261015-v2';DEST=ROOT/'evals/qa-overhaul-v1.1.json'


def main():
    manifest,_,_,contents=verified_corpus(DATA,DATA/'index.sqlite3')
    files={s.path:(s,raw,*source_view(s.path,raw)) for s,raw in contents}
    tools='src/oss/langchain/tools.mdx';mem='src/oss/concepts/memory.mdx'
    rag='src/oss/deepagents/retrieval.mdx';deep='src/oss/deepagents/overview.mdx'
    mid='src/oss/langchain/middleware/overview.mdx';custom='src/oss/langchain/middleware/custom.mdx'
    built='src/oss/langchain/middleware/built-in.mdx';sub='src/oss/langchain/multi-agent/subagents.mdx'
    router='src/oss/langchain/multi-agent/router.mdx';handoff='src/oss/langchain/multi-agent/handoffs.mdx'
    obs='src/langsmith/observability-concepts.mdx';sampling='src/langsmith/sample-traces.mdx'
    tracing='src/langsmith/trace-without-env-vars.mdx'
    planner='code/chapter4/Plan_and_solve.py'
    nb='04-tool-use/code_samples/04-python-agent-framework.ipynb'
    hello='code/chapter1/FirstAgentTest.ipynb'
    hitl='06-building-trustworthy-agents/code_samples/06-human-in-the-loop.ipynb'
    multi='08-multi-agent/code_samples/08-python-agent-framework.ipynb'
    calc='ai_agent_framework_crash_course/google_adk_crash_course/4_tool_using_agent/4_2_function_tools/calculator_agent/tools.py'
    hybrid='rag_tutorials/hybrid_search_rag/main.py'
    conf='rag_tutorials/hybrid_search_rag/requirements.txt';localconf='rag_tutorials/local_rag_agent/requirements.txt'
    progress='docs/specification/2026-07-28/basic/patterns/progress.mdx'
    page='docs/specification/2026-07-28/server/utilities/pagination.mdx'
    cancel='docs/specification/2026-07-28/basic/patterns/cancellation.mdx'
    logging='docs/specification/2026-07-28/server/utilities/logging.mdx'
    annotations=[]
    def quote(path,needle,end=None,kind='prose',cell=None):
        source,raw,text,cells=files[path]
        minimum=next(c['start'] for c in cells if c['cell_index']==cell) if cell else 0
        start=text.index(needle,minimum)
        if end is None:
            start=text.rfind('\n\n',minimum,start)+2 if '\n\n' in text[minimum:start] else minimum
            finish=text.find('\n\n',start)
            if finish<0:finish=len(text)
        else:finish=text.index(end,start)+len(end)
        while start<finish and text[start].isspace():start+=1
        while finish>start and text[finish-1].isspace():finish-=1
        if end is None and kind=='prose':
            import re
            while start<finish and re.fullmatch(r'\s*(?:::.*|<[^>]+>)\s*',text[start:text.find('\n',start) if '\n' in text[start:finish] else finish]):
                start=text.index('\n',start)+1
            while start<finish:
                line_start=text.rfind('\n',start,finish)+1
                if not re.fullmatch(r'\s*(?:::.*|<[^>]+>)\s*',text[line_start:finish]):break
                finish=line_start-1
        loc=locator(source,raw,start,finish)
        return {'source_id':source.source_id,'start_char':start,'end_char':finish,
                'start_line':text.count('\n',0,start)+1,'end_line':text.count('\n',0,finish-1)+1,
                'quote':text[start:finish],'kind':kind,'source_locator':loc,
                'line_url':source.source_url if loc else source.source_url+f"#L{text.count(chr(10),0,start)+1}-L{text.count(chr(10),0,finish-1)+1}",
                'rationale':'Source-first code-assistant annotation; no retrieval ranking or generated answer used; not human approval'}
    def add(topic,question,points,prelude=None,missing='',cannot=None):
        annotations.append({'id':f'OVERHAUL-A{len(annotations)+1:02}','topic':topic,'question':question,'book':None,'prelude':prelude,
            'answerability':'insufficient' if not points else 'partial' if missing else 'answerable',
            'missing_information':missing,'cannot_infer':cannot or ['不能把文档、配置或静态代码描述称为实际运行验证，也不能推广成其他框架的保证。'],
            'points':[{'id':f'P{i+1}','answer':answer,'supports':supports,'coverage':'all'} for i,(answer,supports) in enumerate(points)],
            'review_origin':'source-first model-assisted annotation; not human benchmark'})
    add('tools','LangChain 工具用 runtime.stream_writer 发进度时，能直接脱离 LangGraph 执行上下文调用吗？只说明前提。',[
        ('文档要求在LangGraph执行上下文中调用该工具。',[quote(tools,'If you use `runtime.stream_writer`')])])
    add('tools','微软 04-tool-use Notebook 的 book_flight 示例怎样声明审批要求？函数体能证明已调用真实订票服务吗？',[
        ('装饰器设approval_mode=always_require。函数体只拼接确认字符串，未见真实订票API调用，不能当成订票实测。',[quote(nb,'@tool(approval_mode="always_require")','    )',kind='code',cell=13)])])
    add('tools','Hello-Agents 的 FirstAgentTest.ipynb 中，get_attraction 没有 TAVILY_API_KEY 时会创建客户端并继续搜索吗？按源码回答。',[
        ('先检查环境变量，缺失即返回配置错误，不进入后面的客户端创建和search调用。',[quote(hello,'api_key = os.environ.get("TAVILY_API_KEY")','tavily = TavilyClient(api_key=api_key)',kind='code',cell=2)])])
    add('tools','calculate_percentage 的 total 为零时，示例代码是主动返回错误还是继续除法？这能代表框架的统一参数校验吗？',[
        ('函数内先返回error/status，不执行后续除法；不能推成框架统一校验。',[quote(calc,'if total == 0:','percentage = (value / total) * 100',kind='code')])])
    add('memory','用 Reflection 改进智能体指令时，文档建议把什么输入交给智能体？它修改的是哪类内容？',[
        ('输入当前指令和近期对话或用户反馈，产出改进后的指令。',[quote(mem,'One effective approach to refining')])])
    add('memory','记忆文档的 update_instructions 伪代码把新规则保存到哪里？能据此说模型权重被在线训练了吗？',[
        ('示意保存prompt到store，通常改提示而非权重，不能称在线训练。',[quote(mem,'In practice, it is fairly uncommon'),quote(mem,'The below pseudo-code shows')])])
    add('memory','记忆文档里 InMemoryStore 示例的 embed 返回常量列表，能把它当成已经实现的真实语义嵌入吗？',[
        ('注释要求替换成真实embedding，当前返回常量列表只是示例。',[quote(mem,'def embed(texts: list[str])','return [[1.0, 2.0] * len(texts)]',kind='code')])])
    add('memory','LangGraph store 的 namespace 与 key 分别类似什么？文档是否只允许按 thread ID 组织长期记忆？',[
        ('namespace类似文件夹、key类似文件名，可用用户或组织ID等自定义组织，不限thread ID。',[quote(mem,'Each memory is organized'),quote(mem,'It can be recalled _at any time_')])])
    add('rag','Hybrid Search RAG 的 requirements.txt 对 raglite、rerankers 和 sqlalchemy 分别写了什么版本约束？这些能证明当前安装版本吗？',[
        ('raglite==0.2.1，rerankers==0.6.0，sqlalchemy>=2.0.0；是依赖声明，不能证明本机实际安装。',[quote(conf,'raglite==0.2.1','rerankers==0.6.0',kind='code')])])
    add('rag','perform_search 给 hybrid_search 写的 num_results 是多少？能直接保证最终返回列表一定有这么多条吗？',[
        ('调用处显式num_results=10；有空结果分支与重排，不能保证最终十条。',[quote(hybrid,'chunk_ids, scores = hybrid_search','return rerank_chunks(query, chunks, config=st.session_state.my_config)',kind='code')])])
    add('rag','Local RAG 案例依赖清单列出了哪些 Agent、检索和本地推理组件？agno 是锁定单一版本吗？',[
        ('列有agno、qdrant-client、ollama，agno>=2.2.10为下限而非精确锁定。',[quote(localconf,'agno>=2.2.10','pypdf',kind='code')])])
    add('rag','资料中 Retrieval 主要针对大模型的哪两项限制？外部知识是在什么时间引入的？',[
        ('有限上下文与静态训练知识；查询时检索相关外部知识。',[quote(rag,'* **Finite context**','at a point in time.'),quote(rag,'Retrieval addresses these problems')])])
    add('planning','Hello-Agents 的 Planner.plan 如何解析模型给出的计划？没有合法 Python 列表时会返回什么？',[
        ('提取python代码围栏后用ast.literal_eval解析，只接受list；解析异常或非列表返回空列表。',[quote(planner,'plan_str = response_text.split','return []',kind='code')])])
    add('planning','PlanAndSolveAgent.run 遇到空计划会继续调用 executor 吗？只描述这份代码的控制流。',[
        ('先判断not plan并return，非空才显式调用executor.execute。',[quote(planner,'plan = self.planner.plan(question)','final_answer = self.executor.execute(question, plan)',kind='code')])])
    add('planning','微软 human-in-the-loop Notebook 的 classify_risk 对不含任何已知关键词的动作，默认给 low 还是 medium？',[
        ('未知动作默认medium，源码注释明确不按low处理。',[quote(hitl,"# Explicit fail-safe default: unrecognized actions route to batched review.",'return "medium"',kind='code',cell=6)])])
    add('planning','Deep Agents 在 v0.7 前后的 task planning 默认启用策略有什么变化？新版本怎样提供 write_todos？',[
        ('v0.7起opt-in，早期默认包含；显式传TodoListMiddleware提供write_todos。',[quote(deep,'Starting in v0.7 task planning'),quote(deep,'Pass @[`TodoListMiddleware`]')])])
    add('context','Deep Agents 的默认 prompt caching 对哪些供应商启用，缓存哪些内容？能推广为所有模型的默认行为吗？',[
        ('Anthropic及Bedrock Claude/Nova默认缓存静态system instructions、memory、skills，不是所有供应商通用默认。',[quote(deep,'For Anthropic and Amazon Bedrock'),quote(deep,'Prompt caching is enabled by default')])])
    add('context','HumanInTheLoopMiddleware 的 interrupt_on 键按工具变量名还是工具的 .name 匹配？文档 send_email 示例怎么写？',[
        ('按工具.name匹配；@tool函数默认名send_email，配置interrupt_on={send_email: True}。',[quote(mid,'`HumanInTheLoopMiddleware` matches'),quote(mid,'`@tool`-decorated functions take their name')])])
    add('context','LangChain 的 wrap-style hook 是否必须恰好调用一次 handler？可以用来做什么控制？',[
        ('可零次短路、一次正常流、多次重试；由中间件控制。',[quote(custom,'Intercept execution and control'),quote(custom,'You decide if the handler is called zero times')])])
    add('context','模型调用次数和工具执行次数要分别限制时，LangChain 内置 middleware 对应哪两项？',[
        ('Model call limit限制模型调用，Tool call limit限制工具调用次数。',[quote(built,'| [Model call limit]','| [Tool call limit](#tool-call-limit) | Control tool execution by limiting call counts. |')])])
    add('mcp','MCP 2026-07-28 的 progressToken 可以是什么类型？progress 值能倒退或在完成后继续发送吗？',[
        ('token是string或integer，活动请求内唯一。',[quote(progress,'- Progress tokens **MUST**','across all active requests.')]),
        ('progress每次须增加，完成后须停止。',[quote(progress,'- The `progress` value **MUST**','unknown.'),quote(progress,'- Progress notifications **MUST** stop after completion')])])
    add('mcp','MCP 2026-07-28 分页能假设每页固定条数、把 cursor 当页码加一吗？下一页依据哪个字段？',[
        ('cursor是不透明token，页大小服务端决定，不能固定假设；继续分页用返回的nextCursor。',[quote(page,'Pagination in MCP uses','\n  size'),quote(page,'- An optional `nextCursor` field')])])
    add('mcp','MCP 2026-07-28 取消 Streamable HTTP 请求与取消 stdio 请求，客户端分别怎么做？',[
        ('HTTP关闭该SSE响应流，服务端须视为取消；stdio发送引用requestId的notifications/cancelled。',[quote(cancel,'- **Streamable HTTP**: Closing','notification referencing the request ID.')])])
    add('mcp','进度通知持续到达时，MCP 2026-07-28 的请求超时能无限延长吗？',[
        ('可以选择因进度重置超时，但仍应有最大超时。',[quote(cancel,'Implementations **MAY** choose to reset','limit the impact of a misbehaving client or server.')])])
    add('multi_agent','微软 08-multi-agent Notebook 的 extended_workflow 怎样连接 planner、concierge、budget 三个 Agent？这是并行 fan-out 配置吗？',[
        ('源码从planner开始，planner→concierge→budget依次连边，不是同时分发三路的配置；未作运行验证。',[quote(multi,'extended_workflow = WorkflowBuilder','    .build()',kind='code',cell=11)])])
    add('multi_agent','LangChain router 只路由一个 Agent 与并行分发多个 Agent，文档分别用 Command 还是 Send？',[
        ('单Agent用Command，多个并行fan-out用Send。',[quote(router,'The router classifies the query')])])
    add('multi_agent','Handoffs 一定要建多个 Agent 子图吗？一个 Agent 能否通过 middleware 改变配置来实现？',[
        ('文档列出单agent+middleware及多个agent子图两种方式，非必须多个。',[quote(handoff,'There are two ways to implement handoffs')])])
    add('multi_agent','subagent 工具返回结果后，主 Agent 是立刻固定退出还是继续编排？什么信息帮助它决定调用哪个子工具？',[
        ('按子工具描述决定调用，收到结果后继续编排；没有固定立刻退出。',[quote(sub,'The main agent invokes the subagent tool')])])
    add('observability','LangSmith 全局采样率设为0、1和0.75分别表示什么？变量名是什么？',[
        ('LANGSMITH_TRACING_SAMPLING_RATE，0不采、1全采、0.75采75%；不代表模型成功率。',[quote(sampling,'By default, all traces are logged','75% of the traces.'),quote(sampling,'export LANGSMITH_TRACING_SAMPLING_RATE=0.75',kind='code')])])
    add('observability','两个 LangSmith Client 能否使用不同 tracing_sampling_rate，再按不同操作选择？',[
        ('文档示例支持不同Client采样率，并用tracing_context(client=...)作用于不同操作。',[quote(sampling,'You can also set sampling rates on specific'),quote(sampling,'client_1 = Client','client_2 = Client(tracing_sampling_rate=0.25)',kind='code')])])
    add('observability','不使用已有框架集成时，LangSmith 文档列出的三种手动埋点机制是什么？',[
        ('traceable装饰器、Python trace上下文管理器、RunTree低层显式构造。',[quote(obs,'_Manual instrumentation_','- `RunTree` API: low-level, explicit trace construction')])])
    add('observability','按这份固定版本文档，要把 LangSmith SaaS 的某些样本保留超过 trace 留存期，应怎样做？',[
        ('固定文档称trace默认180天；需长期保留的加dataset，dataset在源trace删除后仍保存。',[quote(obs,'LangSmith (SaaS) retains'),quote(obs,'To keep data beyond the retention period')])])
    add('memory','换个话题：Reflection 修改的是权重还是指令？只根据课件解释。',[
        ('此处Reflection用当前指令、对话或反馈改进指令，不是证明权重训练。',[quote(mem,'One effective approach to refining'),quote(mem,'In practice, it is fairly uncommon')])],prelude='MCP 的服务端日志通知是什么？')
    add('tools','这里的函数体能证明机票已经通过外部服务订好了吗？',[
        ('该book_flight示例只有返回确认字符串，未见外部订票调用，不能声称实际出票。',[quote(nb,'@tool(approval_mode="always_require")','    )',kind='code',cell=13)])],prelude='请解释微软 04-tool-use Notebook 中的 book_flight 示例。')
    add('context','比较 LangChain 的 runtime.stream_writer 与 MCP progressToken：一个是执行上下文入口还是协议字段，另一个有什么类型约束？',[
        ('stream_writer是LangChain工具的自定义更新入口，要求LangGraph执行上下文。',[quote(tools,'Use `runtime.stream_writer`'),quote(tools,'If you use `runtime.stream_writer`')]),
        ('progressToken是MCP请求的进度关联token，string或integer，不是同一个API。',[quote(progress,'- Progress tokens **MUST**','across all active requests.')])])
    oldpage=page.replace('2026-07-28','2025-11-25')
    add('mcp','对照 MCP 2025-11-25 与 2026-07-28，两版分页 cursor 是否都不透明，客户端是否能假设固定页大小？',[
        ('2025版使用不透明cursor，页大小由服务端决定，客户端不能固定假设。',[quote(oldpage,'Pagination in MCP uses','\n  size')]),
        ('2026版对应规则一致；不能自行把token当页码。',[quote(page,'Pagination in MCP uses','\n  size')])])
    add('planning','微软 Notebook 的 tiered_gate 把 medium 动作送给真人批准后才返回 approve，对吗？请纠正前提。',[
        ('示例对low及medium直接自动approve；high才调用gate_action，不可说medium先经真人。',[quote(hitl,'def tiered_gate(action:','return gate_action(action, tier, attempt=attempt)',kind='code',cell=6)])])
    add('observability','根据这些课件，给出本机今天的真实模型支出和阿里账户免费 tokens 剩余量。',[],
        missing='没有本机当天账单、调用用量及阿里账户实时免费额度记录，课件不能提供这些实测值。')
    add('planning','human-in-the-loop Notebook 的 DEMO_MODE 下，高风险重试获批是否说明真人重新评估后降低了风险？',[
        ('DEMO_MODE是脚本演示：首次拒绝，后续尝试批准；注释明确不是根据修改后的提案重新评估，也非真人审批证明。',[quote(hitl,'DEMO_MODE behavior:','proposal on its own merits.',kind='code',cell=4)])])
    add('tools','LangChain 示例的 ToolRuntime 和微软 Notebook 的 @tool(approval_mode=...) 可以直接视为所有框架统一的同一套工具参数契约吗？',[
        ('ToolRuntime示例属于LangChain。',[quote(tools,'from langchain.tools import tool, ToolRuntime','from langchain.tools import tool, ToolRuntime',kind='code')]),
        ('微软示例使用自己的tool审批装饰器；两份代码不提供跨框架统一参数或互换保证。',[quote(nb,'@tool(approval_mode="always_require")','    )',kind='code',cell=13)])])
    assert len(annotations)==40
    assert sum(any(s['source_locator'] for p in q['points'] for s in p['supports']) for q in annotations)>=4
    result={'version':'qa-overhaul-v1.1','frozen_on':'2026-10-15','corpus_version':manifest['corpus_version'],
            'raw_files':len(contents),'questions':annotations,'origin':'New source-first scenarios; model-assisted labels, not human accuracy. No ranking or generated answers used.'}
    from study_rag.qa_retrieval import body_mask
    from study_rag.rag import visible_prose
    from study_rag.answer_schema import normalize_with_positions
    for q in annotations:
        for p in q['points']:
            for span in p['supports']:
                source,raw,text,cells=next(v for v in files.values() if v[0].source_id==span['source_id'])
                if span['kind']=='prose':
                    mask=body_mask(text,source.path.endswith('.mdx'))
                    if normalize_with_positions(visible_prose(span['quote'],mask[span['start_char']:span['end_char']]))[0]!=normalize_with_positions(span['quote'])[0]:
                        raise ValueError('Gold contains masked syntax: '+q['id']+':'+source.path)
    encoded=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if DEST.exists() and DEST.read_text(encoding='utf-8')!=encoded:raise ValueError('Frozen questions changed')
    if not DEST.exists():DEST.write_text(encoded,encoding='utf-8')
    print(json.dumps({'questions':40,'points':sum(len(q['points']) for q in annotations),'sha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),'model_calls':0}))


if __name__=='__main__':main()
