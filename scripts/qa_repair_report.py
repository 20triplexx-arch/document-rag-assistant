"""Deliver failed gates and exact positions without claiming answer accuracy."""
from pathlib import Path
import csv
import hashlib
import json
import sqlite3
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/qa-repair-20261015-v5'


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    offline=read(OUT/'offline-final.json');bench=read(OUT/'retrieval-benchmark-final.json');audit=read(OUT/'object-index-audit.json')
    before=read(OUT/'before-contract.json');gold_path=ROOT/'evals/qa-repair-frozen-v1.json';gold=read(gold_path)
    manifest=read(ROOT/'data/qa-overhaul-20261015-v2/corpus.json');sources={d['source']['source_id']:d['source'] for d in manifest['documents']}
    exposed={q['id']:q for path in [ROOT/'evals/qa-depth-v1.json',ROOT/'evals/qa-overhaul-regression-v1.2.json'] for q in read(path)['questions']}
    rows=[];failures=[]
    for group,questions in offline['results'].items():
        for q in questions:
            covered=set(q['covered_points']);expected=q['expected_points']
            rows.append({'group':group,'id':q['id'],'question':q['question'],'covered':len(covered),'expected':expected,
                'complete':len(covered)==expected,'seconds':q['elapsed_seconds']})
            for point in q.get('points',exposed.get(q['id'],{}).get('points',[])):
                if point['id'] in covered:continue
                positions=[]
                for span in point['supports']:
                    source=sources.get(span['source_id']);same=[e for e in q['evidence'] if e['source_id']==span['source_id']]
                    kind=span.get('kind','prose');ranged=[e for e in same if e['start_char']<=span['start_char'] and e['end_char']>=span['end_char']]
                    reason='wrong_evidence_channel' if ranged and all(e.get('content_type','prose')!=kind for e in ranged) else 'position_or_mask_not_covered' if same else 'source_not_selected'
                    loc=span.get('source_locator');position=(f"Notebook单元{loc['cell_index']}行{loc['start_line']}–{loc['end_line']}" if loc else f"L{span['start_line']}–L{span['end_line']}")
                    positions.append({**span,'path':source['path'] if source else None,'indexed_source_available':source is not None,
                        'position':position,'attribution':reason,'selected_same_source':[{'start_char':e['start_char'],'end_char':e['end_char'],'content_type':e.get('content_type')} for e in same]})
                failures.append({'group':group,'id':q['id'],'question':q['question'],'point_id':point['id'],'required_fact':point['answer'],
                    'positions':positions,'attribution_scope':'Strict original support-position coverage, not a semantic verdict on unannotated alternative passages.'})
    preserved={path:sha(ROOT/path)==expected for path,expected in before['preserved_ledger_sha256'].items()}
    ledger=ROOT/'output/qa-depth-20261015-v1/ledger.sqlite3'
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        spent=db.execute('SELECT sum(coalesce(settled_micros,reserved_micros)) FROM flash_spend').fetchone()[0]
        phases=[]
        for name,purpose,calls,cap,protected in db.execute('SELECT name,purpose,max_calls,limit_micros,protected FROM experiment_phases'):
            n,cost=db.execute('SELECT count(*),coalesce(sum(coalesce(s.settled_micros,s.reserved_micros)),0) FROM phase_calls p JOIN flash_spend s ON p.call_key=s.call_key WHERE p.phase=?',(name,)).fetchone()
            phases.append(dict(name=name,purpose=purpose,max_calls=calls,limit_micros=cap,protected=bool(protected),actual_calls=n,used_upper_micros=cost))
        original=json.loads(db.execute("SELECT value FROM contracts WHERE name='flash-only-resume-20261015'").fetchone()[0])['limit_micros']
    assert spent==2710052 and original==500000 and all(p['actual_calls']==0 for p in phases) and all(preserved.values())
    assert all(sha(ROOT/p)==digest for p,digest in offline['code_contract'].items())
    assert all(sha(ROOT/p)==digest for p,digest in bench['code_contract'].items())
    with urllib.request.urlopen('http://127.0.0.1:8765/api/library',timeout=5) as response:library=json.load(response)
    active={k:library.get(k) for k in ['raw_files','chunks','corpus_version','answer_schema_version','models']}
    assert active['raw_files']==216 and active['answer_schema_version']==1
    with sqlite3.connect((ROOT/'output/users.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        accounts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['users','chats','exchanges']}
    samples=[{'id':q['id'],'question':q['question'],'status':'NOT_GENERATED_OFFLINE_GATE',
        'reason':'Offline prerequisites failed. No model call, no fabricated answer or review score.',
        'source_first_rubric':q['points']} for q in gold['questions'] if q['id'] in gold['representative_sample_ids']]
    assert len(samples)==12
    (OUT/'representative-samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'retrieval-failures.json').write_text(json.dumps(failures,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (OUT/'per-question-results.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'default_switched':False,'reason':'Offline quality prerequisites failed; repeated tuning stopped. No paid development or frozen generation.',
        'gates':{**offline['gates'],'serial_retrieval_p95':bench['warm_p95_gate'],'frozen_quality':None,'real_http_first_block':None},
        'offline':{'records':len(rows),'old':offline['old'],'new':offline['new'],
            'previous_questions_complete':sum(r['complete'] for r in offline['results']['previous_frozen']),
            'previous_points':sum(len(r['covered_points']) for r in offline['results']['previous_frozen']),
            'previous_expected':sum(r['expected_points'] for r in offline['results']['previous_frozen'])},
        'cost':{'new_calls':0,'new_upper_cny':0,'total_upper_cny':spent/1000000,'remaining_cny':(5000000-spent)/1000000,
            'original_contract_cny':original/1000000,'phases':phases},'active_library':active,'account_counts':accounts,
        'preserved_old_ledgers':preserved,'holdout_sha256':sha(gold_path),'holdout_used_for_tuning':False,
        'backend_tests':241,'frontend_tests':34,'new_holdout_generation':'not started','content_review':'not performed: no generated answers',
        'full_answer_25_percent':'insufficient evidence: no 20 quality-valid baseline pairs reviewed; no additional paid timing trials',
        'representative_samples_generated':0,'representative_samples_reserved':12,'object_index':{k:audit[k] for k in ['scoped_symbols','python_units','analysis_gap_units']}}
    (OUT/'delivery-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def link(path,label):return f'[{label}]({Path(path).resolve().as_posix()})'
    doc=f'''# 取证与回答组织修复：最终结果

本轮串行预热检索达到速度目标，离线质量门槛仍未通过，因此保留旧默认，没有启动开发生成或冻结 HTTP 验收。新增模型调用 **0 次**，新增费用 **0 元**；累计费用上界 **2.710052 元**，剩余 **2.289948 元**。这些结果不能解释成生成答案正确率。

## 已实现的候选改动

- 同一对象索引覆盖 Python 文件、Notebook 代码单元和 Markdown/MDX Python 围栏，保留文件、单元和围栏身份；识别点号方法及模块赋值。未执行收录代码。
- 精确函数匹配打开代码通道；配置、正文和代码分别取证。进度与分页拆成独立规则，版本比较逐维度召回。短来源保留完整父级背景，重叠证据有新增必要面时合并。
- 保存服务端对象锚点并在指代追问中复用；明确换题清空。区分对象歧义、已收录但未召回及文件未收录，历史回答不能当事实。
- 内部内容块绑定必要面，禁止同一编号重复输出；源码关系使用后端事实组，缺口由编号还原。公开 v2、旧记录及请求字段兼容，终校失败仍撤回预览。
- 预建筛选集合、符号关系与规范条款候选；E5 每题最多两个窗口，批量编码。八线程复用原文读取池，仍每题完整读取原文和索引一次，以完全相等的字节复用解析结果。
- 启动预热本地索引与 E5，冷启动单列。预算按事务同时限制开发八次/0.25元、冻结1.20元及累计5元，未知用量占预留；Pro/Max 与未确认免费保护的百炼生成保持关闭。

## 验证结果

| 项目 | 实测 | 门槛 | 结论 |
|---|---:|---:|---|
| 旧开发必要支持点 | {offline['old']['covered_support_points']}/49 | ≥45/49 | 未通过 |
| 新开发必要支持点 | {offline['new']['covered']}/72 | ≥70/72 | 未通过 |
| 上轮40题修订标注 | {result['offline']['previous_questions_complete']}/40完整，{result['offline']['previous_points']}/44点 | 全部可召回 | 未通过 |
| 串行预热检索20题×3次 P95 | {bench['warm']['p95_ms']:.1f}ms | ≤500ms | 通过 |
| 串行预热检索中位数 | {bench['warm']['median_ms']:.1f}ms | 独立报告 | — |
| 新查询 P95 / 重复查询 P95 | {bench['new_query']['p95_ms']:.1f} / {bench['repeated_query']['p95_ms']:.1f}ms | 独立报告 | — |
| 并发2检索 P95 | {bench['concurrency_2']['p95_ms']:.1f}ms | 独立报告 | 仍有瓶颈 |
| 冷启动 | {bench['cold_start_seconds']:.2f}s | 排除于预热耗时 | 明确计入启动 |
| 新链路真实 HTTP 首块 / 冻结40题质量 | 未运行 | ≤2.5秒 / 38题等完整门槛 | 离线未过，不花验证费用 |
| 完整回答提速25% | 证据不足 | 20道质量有效配对 | 未声明达标 |

后端241项、前端34项测试通过；原始2164文件、84686个分块的位置和旧301文件字节保全检查通过。完整离线回归保留152条记录（原112条加上轮40题）。新40题在排序修改前冻结，共67个必要点、6道Notebook题；出处逐字核对通过，尚未进入生成验收，仍可作为未使用的冻结题。A18只在新回归标注v1.2增加了实际配置行，原冻结标注与失败输出保留。

## 尚未解决的瓶颈

1. 混合题仍会选到同名函数或概览，挤掉所问 API 的配置与规则正文。最新失败包括 `interrupt_on`、wrap-style hook、调用次数限制、Command/Send、subagent 返回行为及跨框架 ToolRuntime 比较。
2. 必要面匹配仍有过宽或不足的情况。标题及关键词命中没有证明整个维度得到支持；Memory 的 namespace/key、ReAct/先规划边界及工具消息配对等原标注仍有缺口。不能用降低标注要求或宣称资料未收录解决。
3. Python 静态分析尝试了 {audit['python_units']} 个独立单元，建立 {audit['scoped_symbols']} 个带范围的符号；其中 {audit['analysis_gap_units']} 个不完整/无法解析的教学片段保留为分析缺口。原文仍可检索，这些单元没有被冒充为完整 AST 关系。
4. 并发2下 P95 仍约1秒。序列读取、E5及校验缓存已改善串行耗时，但并发资源争用与长尾仍需要独立处理。

最近两轮未超过最好离线结果，已停止同类调参。最后只完成明确的范围识别错误和结构兼容修复，再做最终检查。没有使用新冻结题进行调参，没有把未生成答案计成通过或零事实错误。

## 交付与保全

- {link(OUT/'per-question-results.csv','152条逐题汇总')}；{link(OUT/'retrieval-failures.json','全部失败要点、原文位置与归因')}。
- {link(OUT/'offline-final.json','最终离线原始结果与代码哈希')}；{link(OUT/'retrieval-benchmark-final.json','80条检索测速记录（60串行、20并发）')}。
- {link(OUT/'object-index-audit.json','逐文件对象分析及987个分析缺口')}；{link(OUT/'verify-final.log','完整测试与来源校验日志')}。
- {link(gold_path,'新冻结40题与预定12个样本编号')}；{link(OUT/'representative-samples.json','12个样本清单')}。这12题因离线门槛失败而未生成，清单明确标记原因；没有伪造成功或失败输出。此前真实输出继续保留在旧轮目录。
- {link(OUT/'delivery-report.json','费用、阶段上限、旧账本哈希、默认库与账号数量核对')}。

当前页面继续使用216文件旧默认、公开回答v1和DeepSeek Flash；新2164文件快照与候选v5链路均保留。账号/讨论数量为 {accounts['users']}/{accounts['chats']}/{accounts['exchanges']}，本轮未写生产账号库。两个旧预算账本哈希不变，0.5元原合同未改写，5元累计授权未重置。没有扩库、运行第三方案例、使用付费裁判、切换默认或部署公网。
'''
    (ROOT/'docs/qa-repair-2026-10-15.md').write_text(doc,encoding='utf-8')
    review='''# 取证修复复核

本轮只有离线取证覆盖与代码测试，没有新生成答案。结构/出处、内容支持、聚焦度、严重事实错误和首块速度不能据此判为通过。

逐题原文位置与失败原因见 [失败清单](../output/qa-repair-20261015-v5/retrieval-failures.json)，完整结果见 [交付报告](../docs/qa-repair-2026-10-15.md)。归因脚本只区分来源未选、范围未覆盖和通道不符；未标注替代段落没有被自动判为语义错误，也没有擅自计为通过。

下一轮应先明确 API/函数/配置对象间的范围关系，再为不完整 Python 示例建立保留位置的词法符号入口，AST只对可解析部分给关系。应把路由信号与必要事实覆盖彻底分开，优先解决上述实际失败，而非继续堆叠权重、扩大输出或重复花费冻结验收预算。本轮没有执行这一下一轮方案。
'''
    (ROOT/'reviews/qa-repair-2026-10-15.md').write_text(review,encoding='utf-8')
    print(json.dumps({'default_switched':False,'new_model_calls':0,'new_cost_cny':0,'old':offline['old']['covered_support_points'],'new':offline['new']['covered'],'p95_ms':bench['warm']['p95_ms'],'failure_points':len(failures)},ensure_ascii=False))


if __name__=='__main__':main()
