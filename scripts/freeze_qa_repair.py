"""Source-first holdout, frozen before v5 ranking changes; no model calls."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import source_view, locator

DEST = ROOT / 'evals/qa-repair-frozen-v1.json'


def main():
    data = ROOT / 'data/qa-overhaul-20261015-v2'
    manifest, _, _, contents = verified_corpus(data, data/'index.sqlite3')
    files = {s.path: (s, raw, *source_view(s.path, raw)) for s, raw in contents}
    tools = 'src/oss/langchain/tools.mdx'
    memory = 'src/oss/concepts/memory.mdx'
    rag = 'src/oss/deepagents/retrieval.mdx'
    deep = 'src/oss/deepagents/overview.mdx'
    sub = 'src/oss/langchain/multi-agent/subagents.mdx'
    obs = 'src/langsmith/observability-concepts.mdx'
    sample = 'src/langsmith/sample-traces.mdx'
    plan = 'code/chapter4/Plan_and_solve.py'
    nb = '04-tool-use/code_samples/04-python-agent-framework.ipynb'
    hitl = '06-building-trustworthy-agents/code_samples/06-human-in-the-loop.ipynb'
    conf = 'rag_tutorials/hybrid_search_rag/requirements.txt'
    log = 'docs/specification/2026-07-28/server/utilities/logging.mdx'
    oldlog = log.replace('2026-07-28', '2025-11-25')

    def lines(path, a, b, cell=None, kind='prose'):
        s, raw, text, cells = files[path]
        base = next(c['start'] for c in cells if c['cell_index'] == cell) if cell else 0
        body = text[base:next(c['end'] for c in cells if c['cell_index'] == cell)] if cell else text
        rows = body.splitlines(keepends=True)
        assert 0 < a <= b <= len(rows), (path, a, b, len(rows))
        start = base + sum(map(len, rows[:a-1])); end = base + sum(map(len, rows[:b]))
        while text[start:end] and text[start].isspace(): start += 1
        while text[start:end] and text[end-1].isspace(): end -= 1
        loc = locator(s, raw, start, end)
        return {'source_id': s.source_id, 'path': path, 'start_char': start, 'end_char': end,
                'start_line': text.count('\n', 0, start)+1, 'end_line': text.count('\n', 0, end-1)+1,
                'quote': text[start:end], 'kind': kind, 'source_locator': loc,
                'line_url': s.source_url if loc else s.source_url+f'#L{a}-L{b}',
                'rationale': 'Code assistant checked pinned source; no retrieval or generated answer; model-assisted annotation.'}

    def snippet(path, start, end, cell=None):
        _, _, text, cells = files[path]
        base = next(c['start'] for c in cells if c['cell_index'] == cell) if cell else 0
        a = text.index(start, base); b = text.index(end, a)+len(end)
        return lines(path, text.count('\n', base, a)+1, text.count('\n', base, b-1)+1, cell, 'code')

    questions = []
    def add(topic, question, *facts, prelude=None, missing=''):
        questions.append({'id': f'REPAIR-A{len(questions)+1:02}', 'topic': topic, 'question': question,
            'book': None, 'prelude': prelude, 'answerability': 'answerable' if facts else 'insufficient',
            'missing_information': missing, 'points': [{'id':f'P{i+1}', 'answer':answer,
                'supports':supports, 'coverage':'all'} for i,(answer,supports) in enumerate(facts)],
            'cannot_infer':['文档和示例不能证明实际执行结果；依赖声明不能证明本机安装版本；不能推广到未引用框架或版本。'],
            'review_origin':'Source-first model-assisted labels; not human accuracy.'})

    add('tools','LangChain 的 runtime 参数由谁提供，模型工具 schema 会包含它吗？',
        ('ToolNode在调用时注入。',[lines(tools,254,254)]),('runtime不进入发给模型的schema。',[lines(tools,254,254)]))
    add('tools','微软 04-tool-use Notebook 的 check_availability 遇到未列出的城市怎样返回？',
        ('通过字典get默认返回Unknown destination；不能说明真实库存。',[snippet(nb,'return availability.get','return availability.get(destination, "Unknown destination")',7)]))
    add('tools','微软 04-tool-use Notebook 中 TravelPlan.recommendations 的类型是什么，structured_agent 在哪里指定输出类型？',
        ('recommendations为list[BookingRecommendation]。',[snippet(nb,'class TravelPlan','recommendations: list[BookingRecommendation]',11)]),
        ('run的options.response_format指定TravelPlan。',[snippet(nb,'response = await structured_agent.run','options={"response_format": TravelPlan},',11)]))
    add('tools','LangChain 工具同批并行调用，一部分 return_direct=True、一部分不是，会立即结束吗？',
        ('不会，混合批次返回模型，并带全部ToolMessage。',[lines(tools,845,845)]),
        ('只有该步每个工具都return_direct=True才短路。',[lines(tools,832,832)]))
    add('memory','LangGraph 短期记忆只有聊天消息吗？不同 thread 的状态怎样区分？',
        ('还可含上传文件、检索文档和生成物。',[lines(memory,21,21)]),('以thread作用域的checkpoints隔离。',[lines(memory,21,21)]))
    add('memory','semantic memory 与 semantic search 是同一概念吗？',
        ('前者是存储事实与知识的记忆类型。',[lines(memory,55,55)]),('后者是按意义检索信息的方法。',[lines(memory,55,55)]))
    add('memory','LangGraph 文档分别用什么对应 semantic、episodic 和 procedural memory？',
        ('semantic对应facts。',[lines(memory,46,46)]),('episodic对应experiences。',[lines(memory,47,47)]),('procedural对应instructions。',[lines(memory,48,48)]))
    add('memory','episodic memory 在智能体中常用哪种提示方式实现？',
        ('常用few-shot输入输出示例提示。',[lines(memory,87,87)]))
    add('rag','2-Step RAG 的检索与生成次序固定吗，文档为何说延迟更可预测？',
        ('总是先检索后生成。',[lines(rag,146,146)]),('模型调用数已知且有上限，预测性以推理时间占主导为前提。',[lines(rag,141,141)]))
    add('rag','Agentic RAG 是必须每次先检索吗？决定何时怎样检索的是谁？',
        ('由LLM驱动的智能体在推理中决定何时和如何检索，不是固定前置步骤。',[lines(rag,186,186)]))
    add('rag','Hybrid Search RAG 依赖清单的 pydantic 与 openai 是否都精确锁版本？',
        ('pydantic==2.10.1精确锁定。',[lines(conf,2,2,kind='code')]),('openai>=1.0.0仅下限。',[lines(conf,5,5,kind='code')]))
    add('rag','课件把 2-Step RAG 标成 Fast，是否足以保证所有部署的检索耗时固定？',
        ('不够，实际延迟受API响应、网络和数据库检索变化影响。',[lines(rag,141,141)]))
    add('planning','Hello-Agents Executor.execute 每步的历史怎样累积，最后返回所有步骤还是最后一步的回答？',
        ('按步骤追加step和response_text到history。',[lines(plan,93,96,kind='code')]),('final_answer每步覆盖，末尾返回最后一步回答。',[lines(plan,95,99,kind='code')]))
    add('planning','微软 human-in-the-loop Notebook 的 run_with_revision 默认最多提案几次，获批后还会继续循环吗？',
        ('默认max_revisions=2，range(max_revisions+1)最多3次。',[snippet(hitl,'def run_with_revision','for attempt in range(max_revisions + 1):',8)]),
        ('decision为approve时立即返回。',[snippet(hitl,'if decision["decision"] == "approve":','return decision',8)]))
    add('planning','run_with_revision 怎样把拒绝原因交给下一次提案？',
        ('循环末把decision.reason赋给prior_reason，下一次传propose_action的prior_rejection。',[snippet(hitl,'prior_reason: str | None','prior_reason = decision["reason"]',8)]))
    add('planning','PlanAndSolveAgent 构造时 Planner 与 Executor 使用同一个 llm_client 吗？',
        ('两者均显式接收self.llm_client；不能据此证明依赖内部复用连接。',[lines(plan,103,106,kind='code')]))
    add('context','LangChain 中 thread_id 与 context 分别控制会话还是单次运行数据？持久化还需要什么？',
        ('thread_id限定会话消息和checkpoints，context传每次运行数据。',[lines(tools,304,304)]),('持久化需要checkpointer。',[lines(tools,304,304)]))
    add('context','Deep Agents 的 read_file 对大文件提供哪两个范围参数？是否只支持纯文本？',
        ('支持offset/limit。',[lines(deep,127,127)]),('可返回非文本文件的多模态内容块。',[lines(deep,127,127)]))
    add('context','Deep Agents execute 工具是否所有后端都有？',
        ('仅sandbox backends可用；不能从有虚拟文件系统推出可执行shell。',[lines(deep,133,133)]))
    add('context','Deep Agents delete 的 Python 版本要求是什么，后端不支持删除时会怎样？',
        ('需要deepagents>=0.7。',[lines(deep,135,135)]),('不支持删除的后端会向模型隐藏该工具。',[lines(deep,135,135)]))
    add('mcp','MCP 2026-07-28 请求没有 _meta 的 logLevel 时，服务端还能发送该请求日志通知吗？',
        ('没有io.modelcontextprotocol/logLevel时MUST NOT发送notifications/message。',[lines(log,62,64)]))
    add('mcp','MCP 2026-07-28 请求日志可以推送到 subscriptions/listen 吗？允许在哪个流上发？',
        ('不得发送到subscriptions/listen或其他流。',[lines(log,66,72)]),('只能在设置日志等级的请求的响应流、最终响应前发送。',[lines(log,66,72)]))
    add('mcp','MCP 2026-07-28 不认识 logLevel 的值时，规范规定哪种强度的拒绝及哪个错误码？',
        ('SHOULD拒绝，非MUST。',[lines(log,100,104)]),('-32602 Invalid params。',[lines(log,100,104)]))
    add('mcp','MCP logging 的 debug 和 emergency 两个等级分别表示什么？',
        ('debug为详细调试信息。',[lines(log,49,49)]),('emergency为系统不可用。',[lines(log,56,56)]))
    add('multi_agent','LangChain subagents 默认有各自持续会话记忆吗？记忆默认由谁维护？',
        ('默认子智能体stateless、不记得过去交互。',[lines(sub,5,5)]),('会话记忆由main agent维护；可按需要传历史。',[lines(sub,5,7)]))
    add('multi_agent','LangChain subagents 一轮能并行调用多个吗，路由经过谁？',
        ('主智能体一轮可调用多个子智能体。',[lines(sub,34,34)]),('所有路由经main agent。',[lines(sub,31,31)]))
    add('multi_agent','只有几个简单工具时，LangChain 文档建议直接用 subagents 吗？',
        ('简单少量工具建议single agent；subagents适合多个独立领域或集中工作流控制。',[lines(sub,42,42)]))
    add('multi_agent','子智能体需要向用户澄清时，文档允许什么机制？这会让它成为主编排者吗？',
        ('可用interrupt暂停收集输入。',[lines(sub,45,45)]),('main agent仍为orchestrator。',[lines(sub,45,45)]))
    add('observability','LangSmith 的 thread 与 trajectory 对嵌套结构的保留有什么区别？',
        ('thread分组traces并保留嵌套。',[lines(obs,18,18)]),('trajectory展平成有序消息列表。',[lines(obs,18,18)]))
    add('observability','LangSmith 一次用户回合对应一条 trace 吗，怎样把多回合 traces 关联？',
        ('每一回合独立trace。',[lines(obs,44,44)]),('通过metadata.thread_id唯一值分组。',[lines(obs,44,44)]))
    add('observability','LANGSMITH_TRACING_SAMPLING_RATE 的 0 与 1 各代表什么？',
        ('0不记录trace，1全记录；范围0到1的浮点数。',[lines(sample,20,20)]))
    add('observability','LangSmith sampling 能否保证某个敏感请求绝不被追踪？应用什么控制？',
        ('sampling是概率控制，不是确定性保证。',[lines(sample,58,58)]),('敏感数据绝不记录应用conditional tracing业务逻辑。',[lines(sample,62,66)]))
    add('cross','现在换到 LangSmith：一个 run 是否等于完整多回合 thread？',
        ('run是单个工作单元。',[lines(obs,34,34)]),('thread为多回合traces序列。',[lines(obs,44,44)]) ,prelude='请介绍 LangChain 的短期记忆。')
    add('cross','这里没传已知城市时，函数返回什么？',
        ('原Notebook check_availability默认返回Unknown destination。',[snippet(nb,'return availability.get','return availability.get(destination, "Unknown destination")',7)]),prelude='微软 04-tool-use Notebook 的 check_availability 是什么？')
    add('cross','对照 MCP 2025-11-25 和 2026-07-28，请求日志等级的设置方式一样吗？',
        ('2025客户端MAY发logging/setLevel。',[lines(oldlog,49,49)]),('2026在每个请求_meta加io.modelcontextprotocol/logLevel。',[lines(log,62,64)]))
    add('cross','LangChain 文档的 runtime.state 与 runtime.store 都会在会话结束消失，对吗？',
        ('state为会话期间短期状态。',[lines(tools,250,250)]),('store跨会话持久保存。',[lines(tools,323,323)]))
    add('cross','Hybrid Search RAG requirements.txt 列了 streamlit，能告诉我本机现在装的精确版本吗？',
        ('清单仅streamlit无版本约束，不能得出现装版本。',[lines(conf,11,11,kind='code')]))
    add('cross','MCP 的 trace 日志级别与 LangSmith trace 采样率能直接当同一参数吗？',
        ('MCP指定syslog严重性等级。',[lines(log,44,45)]),('LangSmith采样率控制记录百分比。',[lines(sample,6,6)]))
    add('cross','按课件告诉我今晚本机 Azure 端点是否在线、实际剩余调用额度是多少？',missing='缺少实时端点健康、账户额度与账单；静态课件无法提供。')
    add('cross','微软 tool-use Notebook 的环境变量检查成功，能证明真实 Foundry 已连接成功吗？',
        ('检查仅确认两个环境变量非空，缺失raise ValueError。',[snippet(nb,'endpoint = os.getenv','    )',4)]),
        ('随后构造FoundryChatClient传endpoint/model/credential，不等于执行网络健康测试。',[snippet(nb,'client = FoundryChatClient','    credential=DefaultAzureCredential()',5)]))
    assert len(questions) == 40
    assert len({q['topic'] for q in questions[:32]}) == 8
    assert sum(any(s['source_locator'] for p in q['points'] for s in p['supports']) for q in questions) >= 4
    result = {'version':'qa-repair-frozen-v1', 'frozen_on':'2026-10-15',
        'corpus_version':manifest['corpus_version'], 'origin':'Source-first, before v5 ranking edits; model-assisted review, not human benchmark.',
        'representative_sample_ids':[f'REPAIR-A{i:02}' for i in [1,2,3,6,11,13,14,21,25,29,35,40]],
        'questions':questions}
    encoded = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    if DEST.exists() and DEST.read_text(encoding='utf-8') != encoded: raise ValueError('Frozen data changed')
    if not DEST.exists(): DEST.write_text(encoded, encoding='utf-8')
    print(json.dumps({'questions':40,'points':sum(len(q['points']) for q in questions),'sha256':hashlib.sha256(DEST.read_bytes()).hexdigest(),'model_calls':0}))


if __name__ == '__main__': main()
