"""Persist Codex's source-by-source review; no judge service or model calls.

Decisions were made after reading the frozen answers and pinned source passages.
They are model-assisted judgments, not human accuracy or a semantic proof.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from study_rag.core import verified_corpus
from study_rag.source_views import source_view,locator
from study_rag.answer_schema import validate_v2,quote_locations
from study_rag.provenance import validate_provenance
from study_rag.static_facts import validate_boundaries

OUT=ROOT/'output/qa-overhaul-20261015-v2'
# covered point IDs, citation support, focus, serious factual error, explanation
DECISIONS={
 1:('1',True,True,False,'正确限定到 LangGraph 执行上下文，一段回答。'),
 2:('1',True,False,False,'审批装饰器和字符串返回有源码支持；第二块再次陈述第一块的审批实参。'),
 3:('1',True,False,False,'缺密钥提前返回有支持；自由改写与事实块重复，另补搜索参数，误把无需的运行验证写为缺口。'),
 4:('1',True,True,False,'先给判断，再列实际错误字典和函数内分支的边界；未推广为统一框架校验。'),
 5:('',False,False,True,'把指令反思问题答成 Hello-Agents 的代码反思；遗漏当前指令、近期对话或反馈，且把修改对象错写为代码。'),
 6:('1',True,True,False,'明确写入 store 的指令而非训练权重。额外给出两语言版本，可再缩短。'),
 7:('',True,True,False,'本轮取证未召回 embed 示例，故拒答；原库支持位置存在，属于召回失败，不能算必要内容覆盖。'),
 8:('1',True,True,False,'namespace/key 类比及非 thread 限定均有支持。'),
 9:('1',True,True,False,'三个声明约束正确，区分声明和实际安装；导入补充较长但仍解释安装证明边界。'),
10:('',True,False,False,'具名函数问题没有触发代码通道，未回答 num_results=10，还要求不必要的依赖内部源码。'),
11:('',False,False,False,'要求依赖清单却主要回答 README 和导入路径；漏掉 agno>=2.2.10、qdrant-client、ollama 的声明。'),
12:('',False,False,False,'将有限上下文改成对话状态遗忘，引用把记忆与 RAG 并列讨论的段落；重复解释生成前检索，缺静态训练知识的准确边界。'),
13:('',False,False,True,'称 Hello-Agents 资料没有 Planner.plan；原文有该方法，且实际 ast.literal_eval/非列表返回空列表均未回答。'),
14:('1',True,False,False,'空计划提前 return 的控制流正确，但完整结论、静态事实、最后改述重复同一控制流。'),
15:('1',True,False,False,'默认 medium 正确；额外逐个列出已知关键词分支，末尾又重复默认分支。'),
16:('1',True,False,False,'v0.7 opt-in 和 TodoListMiddleware 正确；四段反复说明 opt-in 和 write_todos。'),
17:('1',True,True,False,'静态 prompt 部分及供应商限定回答正确，末段补充 Bedrock 需支持缓存；首段宜直接保留 Claude/Nova 限定。'),
18:('',True,False,False,'按 .name 匹配回答正确，但缺实际 interrupt_on 配置且重复 send_email 定义。冻结标注对 True 配置值的支持位置也不完整，单独保留标注缺口。'),
19:('1',True,True,False,'零次、一次、多次 handler 和短路/正常/重试的对应正确。'),
20:('',True,True,False,'未召回 Model call limit/Tool call limit，明确拒答；未覆盖必要名称。'),
21:('1',True,True,False,'token 类型及唯一性正确；漏召回完成后 MUST stop，所以 P2 未完整覆盖。'),
22:('',False,True,True,'把响应字段写成 cursor，实际下一页字段是 nextCursor；会误导 API 使用。'),
23:('',True,False,False,'HTTP 关闭流与 stdio 通知的方向正确，但遗漏 stdio requestId 与服务端 MUST 视为取消；开头与分段重复。'),
24:('',False,False,False,'未取到可重置计时但 SHOULD 有最大超时的条款，却先作确定否定，并扩写无关 token 规则。'),
25:('',False,False,False,'生成把 missing_information 放进 blocks[6]，终校失败、预览撤回；没有可验收的最终回答。'),
26:('1',True,False,False,'Command/Send 对应正确；前两段重复同一对应，又补未问的完整路由状态细节。'),
27:('1',True,True,False,'两种方式和 middleware 改变配置均有直接支持；解释偏长，仍围绕实现选择。'),
28:('1',True,False,False,'继续读取结果及工具描述选工具可由引用支持，但扩写完整工具循环、排错 Trace 并追加无需的源码缺口。'),
29:('1',True,True,False,'环境变量及 0/1/0.75 含义正确。'),
30:('1',True,False,False,'不同 Client 与 tracing_context 正确；追加题目未问的条件追踪对比。'),
31:('1',True,True,False,'三种手动埋点及 Python context manager 限定正确，一段回答。'),
32:('1',True,True,False,'固定版本 180 天、加入 dataset 及源 trace 删除后保留均正确。'),
33:('',False,True,True,'换话题后召回 PR/skills，错误声称课件没有 Reflection；原文支持指令反思。'),
34:('',False,False,False,'追问未锚定上一轮 Notebook 的 book_flight，换成另一份 location/date 示例和 MCP 假设流程；结论相似不能替代对象取证。'),
35:('1,2',True,False,False,'双方身份、执行上下文、token 类型完整；完整结论后又分别复述，另补非必要协议说明。'),
36:('1',True,False,False,'旧版规则正确，新版拿到 schema/changelog 而非分页规则；新版必要面缺失，重复说明缺口。'),
37:('1',True,False,False,'low/medium 自动批准及其余转 gate_action 的纠正正确；六段重复和扩写 run_with_revision，缺口超出当前问题。'),
38:('',True,True,False,'正确拒绝给出课件无法提供的账户/计费实时数字，说明 $0 教学路径不等于账单；两项具体缺口齐全。'),
39:('1',True,False,False,'脚本化重试与非真人重评的区别正确；再次复述后输出 print/input/datetime 等无关 AST 事实。'),
40:('1,2',True,False,False,'框架与机制区分有支持；末段重复开头否定，缺口再次复述不能推广。'),
}


def main():
    data=ROOT/'data/qa-overhaul-20261015-v2'
    manifest,_,sources,contents=verified_corpus(data,data/'index.sqlite3')
    raws={s.source_id:raw for s,raw in contents};texts={s.source_id:source_view(s.path,raw)[0] for s,raw in contents}
    rows=[]
    for i,decision in DECISIONS.items():
        path=OUT/'acceptance-final'/f'OVERHAUL-A{i:02d}-0.json'
        record=json.loads(path.read_text(encoding='utf-8'));q=record['scenario'];result=record['result']
        evidence=result['evidence'];source_positions=True;errors=[];locations=[]
        for e in evidence:
            sid=e['source_id'];a,b=e['start_char'],e['end_char'];source=sources[sid]
            if texts[sid][a:b]!=e['text'] or e['source_url']!=source.source_url:source_positions=False
            where=locator(source,raws[sid],a,b)
            if where!=e.get('source_locator'):source_positions=False
            if where and ('#L' in e['line_url'] or e['line_url']!=source.source_url):source_positions=False
        structured=False
        if result.get('answer'):
            try:
                answer=validate_v2(json.dumps(result['answer']),evidence).model_dump()
                validate_provenance(answer,evidence);validate_boundaries(answer,evidence,{})
                locations=quote_locations(answer,evidence);structured=True
            except (ValueError,TypeError) as error:errors.append(type(error).__name__)
        covered,support,focus,serious,reason=decision
        covered=['P'+s for s in covered.split(',') if s]
        content=(len(covered)==len(q['points'])) and (bool(q['points']) or i==38)
        points=[{'id':p['id'],'covered':p['id'] in covered,'expected':p['answer'],
                 'support_positions':[{'source_id':s['source_id'],'start_char':s['start_char'],'end_char':s['end_char'],
                    'start_line':s['start_line'],'end_line':s['end_line'],'source_locator':s.get('source_locator')} for s in p['supports']]}
                for p in q['points']]
        passed=structured and source_positions and content and support and focus and not serious
        rows.append({'id':q['id'],'question':q['question'],'topic':q['topic'],'status':result['status'],
            'structure_pass':structured,'evidence_positions_pass':source_positions,'structure_and_source_pass':structured and source_positions,
            'content_pass':content,'citation_support_pass':support,'focus_pass':focus,'serious_factual_error':serious,
            'pass':passed,'points':points,'reason':reason,'actual_quote_locations':locations,'offline_check_errors':errors,
            'answer_file':str(path.relative_to(ROOT)),'answer_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'review_origin':'Codex source comparison; model-assisted review, not human accuracy or independent judge'})
    topics={}
    for topic in sorted({r['topic'] for r in rows}):
        group=[r for r in rows if r['topic']==topic];total=sum(len(r['points']) for r in group);hits=sum(sum(p['covered'] for p in r['points']) for r in group)
        topics[topic]={'points':total,'covered':hits,'coverage':hits/total if total else None,'passed':sum(r['pass'] for r in group),'questions':len(group)}
    total=sum(len(r['points']) for r in rows);hits=sum(sum(p['covered'] for p in r['points']) for r in rows)
    report={'origin':'Model-assisted source review by Codex; no paid judge, not human accuracy',
        'dataset_sha256':hashlib.sha256((ROOT/'evals/qa-overhaul-v1.1.json').read_bytes()).hexdigest(),
        'corpus_version':manifest['corpus_version'],'questions':40,'structure_and_source':sum(r['structure_and_source_pass'] for r in rows),
        'content_and_focus_pass':sum(r['pass'] for r in rows),'points':total,'covered_points':hits,'point_coverage':hits/total,
        'serious_errors':sum(r['serious_factual_error'] for r in rows),'by_topic':topics,
        'annotation_gaps':[{'id':'OVERHAUL-A18','reason':'Frozen supports establish .name and send_email key, but do not include an actual interrupt_on=True configuration passage. Original gold preserved; example requirement conservatively treated as unmet.'}],
        'rows':rows,'model_calls':0,'network_requests':0,'public_support_verified':False}
    dest=OUT/'acceptance-source-review.json'
    encoded=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if dest.exists() and dest.read_text(encoding='utf-8')!=encoded:raise ValueError('Existing source review changed')
    if not dest.exists():dest.write_text(encoded,encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'rows','by_topic'}},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
