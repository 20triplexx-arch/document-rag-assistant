"""Assemble reproducible public QA results and explicit AI review findings. Zero calls."""
from pathlib import Path
from collections import Counter
import hashlib,json,re,sqlite3,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.answer_schema import answer_text,answer_units
from study_rag.qa_budget import QABudget
from study_rag.qa_evaluation import qa_summary
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"output/qa-v3"
NOTES={
"candidate-TOOL-D2":"首句仍称 divide 内部处理，紧接着才说没有 divide，前提纠正前后矛盾；源码引用存在不代表解释正确。",
"candidate-TOOL-D3":"第二段把工具描述列入模型生成部分，混淆开发者定义 schema/描述与模型生成实参；存在关键对象混淆。",
"candidate-CTX-D1":"三种上下文及瞬态/持久边界有依据；展开较长，重复模型/工具/生命周期区分，可精简。",
"candidate-CTX-D2":"主要机制与信息损失取舍有依据；长段解释后又重复三条摘要，篇幅需精简。",
"candidate-MCP-D1":"采用 2026-07-28，每请求元数据有依据；额外错误码细节超过初学者所问范围。",
"candidate-MULTI-D2":"输入隔离与最终输出机制有依据；最后追加 handoff 规则，应限定其具体模式，避免泛化到所有返回。",
"candidate-OBS-D1":"run/trace/thread 对象已正确区分，例子有依据；末段 LangChain 工具说明与本题关系弱。",
"candidate-OBS-D3":"正确指出案例不是指标采集器；表格三阶段映射部分为综合解释，未清晰标注推演，仍不能当作案例自带分阶段实现。",
"candidate-PLAN-D1":"ReAct 与静态计划的核心区别、适用条件和未提供动态重规划的缺口有依据。",
"candidate-PLAN-D2":"三种能力、todo 非完成证明有依据；实际完成校验细节缺失说明合理；可以进一步减少重复。",
"retest-TOOL-D1":"工具完整循环和结果对应有依据；并行 return_direct、多模态及 MCP 输入请求是未问的扩展，表格再次重复正文，篇幅与聚焦尚未达标。",
"retest-MEM-D2":"已改用实际 Python 源码，纠正 README 的 initialize 示意；初始化、查找和创建有依据，代码摘录不是独立脚本，未执行。",
"retest-RAG-D1":"控制权、执行顺序、延迟预测及检索延迟限制有依据；开头与列表略重复。",
"retest-MCP-D2":"版本区分改善，但把旧逻辑会话表述成连接边界，现有证据不能支持；细节明显过多。最终提示补了限制，未追加开发复测。",
"acceptance-TOOL-A1":"输出有效但没有检索到工具规范的人在环/确认段落，未给出所需具体确认边界；泛化为先协商能力还可能混淆 2026 无状态模型，未通过质量验收。",
"acceptance-CTX-A1":"把用户假设的学习情境解释成实验中的 DISCUSSION_CONTEXT 为空，泄露无关实现细节；主要展开 MCP 规范而非上下文选择，关键子问题未被充分解决。",
"acceptance-RAG-A1":"识别 yes/no、异常保留文档、改写/搜索路径，能解释主流程；但空检索后“不设 run_web_search”的表述不精确（grade_documents 默认返回 No），仍需修正说明。",
"acceptance-MULTI-A1":"模式选择和上下文边界有依据；直接套通用多领域示例，研究报告流程的具体输入/输出安排不足，handoff 消息建议不应泛化为绝对限制。",
"baseline-MEM-D1":"错误断言短期记忆重启后不会保留，并把长期记忆概括为保留全部历史，与 thread/checkpointer 和 namespace 的来源对象混淆。",
"baseline-RAG-D1":"把复杂 Agent 的数十/上百次串行调用泛化为 Agentic RAG 的定义性延迟条件，且未完整比较。",
"baseline-OBS-D1":"用其他框架的 run 定义代替 LangSmith，最终虽指出资料缺口，但前面的对象混用已经影响教学。",
"baseline-MCP-D2":"把应用实例的外部状态持久化/水平扩展推成 MCP 协议机制，缺少两版规范正文。",
"baseline-TOOL-D1":"工具调用工作单与宿主执行的核心链有依据；依赖代码式段落，原始概念过滤仍有局限。",
"baseline-TOOL-D2":"没有源码时拒绝推测 divide 的实现，缺口说明合理；不能因此断言整个仓库没有函数。",
"baseline-MEM-D2":"本轮没有源码证据，选择不足回答，未伪称运行。",
"baseline-MULTI-D1":"只有 subagent 依据时给出部分答案，handoff 缺口明确；未解决完整比较。",
"baseline-MULTI-D2":"说明隔离与回传结果；追加上下文中毒建议与当前问题关系弱。",
"baseline-CTX-D2":"指出窗口限制和摘要，trim/delete 未检索到；重复且有拼写错误 simmarize。",
"baseline-PLAN-D2":"资料只列 harness 能力但仍作机制推演；最终缺口说明不能替代前面推演的明确标注。",
"baseline-OBS-D2":"观测与评测区分基本清楚；追加收据/schema 示例超过用户所问。",
"baseline-MCP-D1":"角色概念基本有依据，但未找到当前规范版本/能力处理正文。"
}
ORACLE_NOTES={
"MEM-D1":"thread/checkpointer 与 namespace 的跨讨论差异有依据；回答直接且具体。",
"RAG-D1":"主流程、模型决策与延迟条件有依据；列表与开头略重复。",
"PLAN-D1":"反应式循环与静态计划区别有依据，工具结果变化与未提供重规划的缺口明确。",
"CTX-D1":"三种上下文与瞬态/持久范围由表格正文支持；适合基础解释。",
"MCP-D1":"明确 2026-07-28 和三个组件，能力按每请求处理，未混入旧初始化流程。",
"MULTI-D1":"控制权、持久状态变量和选择条件有依据；仍有定义与列表重复。",
"OBS-D1":"LangSmith run/trace/thread 关系有依据，示意没有声称已实际运行。"
}

def main():
    records=[];phases={};baseline_by_q={}
    for phase in ("baseline","candidate","oracle","retest","acceptance"):
        rows=[]
        for path in sorted(OUT.glob(phase+"-*.json")):
            if path.name.endswith("failure-audit.json"):continue
            obj=json.loads(path.read_text(encoding="utf-8"))
            if "scenario" not in obj:continue
            q=obj["scenario"];r=obj["result"];key=phase+"-"+q["id"]
            valid=r["status"]=="CITED_DRAFT";text=answer_text(r["answer"]) if r.get("answer") else ""
            note=NOTES.get(key,ORACLE_NOTES.get(q["id"],"仅已核对输出与来源；该条尚无额外语义判定。") if phase=="oracle" else "")
            if not valid:note=f"输出被 {r.get('failure_stage','service')} 检查拦截，未展示；不存在可交付答案，其余语义/篇幅项目未判定。"
            findings={"phase":phase,"id":q["id"],"question":q["question"],"status":r["status"],"output_valid":valid,
                "failure_stage":r.get("failure_stage"),"validation_issues":r.get("validation_issues",[]),"visible_characters":len(text),
                "answer_units":len(answer_units(r["answer"])) if r.get("answer") else 0,"review_origin":"AI source review; not human approval",
                "review_note":note,"quote_check_is_correctness":False,"record_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                "path":str(path.relative_to(ROOT)),"code_contract":obj.get("code_contract"),"prompt_version":r.get("prompt_version")}
            score=obj.get("retrieval_score")
            findings["retrieval_support"]=None if score is None else {"covered":len(score["covered_points"]),"expected":score["expected_points"]}
            rows.append(findings);records.append(findings)
            if phase=="baseline":baseline_by_q[q["id"]]=findings
        phases[phase]={"questions":len(rows),"valid_outputs":sum(r["output_valid"] for r in rows),"failure_stages":dict(Counter(r["failure_stage"] for r in rows if not r["output_valid"]))}
    budget=QABudget(OUT/"budget.sqlite3").summary()
    with sqlite3.connect(OUT/"budget.sqlite3") as db:
        usage=[json.loads(r[0] or "{}") for r in db.execute("SELECT usage FROM calls")]
    budget["reported_prompt_tokens"]=sum(u.get("prompt_tokens") or 0 for u in usage);budget["reported_output_tokens"]=sum(u.get("output_tokens") or 0 for u in usage)
    bm=json.loads((OUT/"retrieval-bm25.json").read_text(encoding="utf-8"));hy=json.loads((OUT/"retrieval-hybrid.json").read_text(encoding="utf-8"))
    # Repair reporting semantics only; retain the original ranks, spans and run files.
    # Partial questions can cover all known support without being fully answerable.
    for report in (bm,hy):
        rows=[{**r,"complete_known_support":len(r["covered_points"])==r["expected_points"],
            "complete":len(r["covered_points"])==r["expected_points"] if r["answerability"]=="answerable" else None}
            for r in report["new"]["results"]]
        report["new"]["summary"]=qa_summary(rows)
    acceptance_retrieval=qa_summary([json.loads(path.read_text(encoding="utf-8"))["retrieval_score"]
        for path in sorted(OUT.glob("acceptance-*.json"))])
    summary={"date":"2026-10-14","status":"NOT_ACCEPTED_KEEP_OLD_DEFAULT","review_origin":"AI-assisted, not human accuracy or approval",
        "source_files":301,"reading_entries":240,"implementation_files":17,"dependency_files":44,"chunks":7780,
        "corpus_version":bm["new"]["corpus_version"],"dataset_sha256":bm["new"]["dataset_sha256"],"budget":budget,"phases":phases,
        "retrieval":{"bm25":{"old":bm["old"],"new":bm["new"]["summary"],"gates":bm["gates"]},
            "hybrid":{"old":hy["old"],"new":hy["new"]["summary"],"gates":hy["gates"]}},
        "acceptance_retrieval":acceptance_retrieval,
        "selected_candidate":"bm25","rollout":False,"answer_acceptance_pass":False,
        "experiment_limits":["旧/新端到端使用不同语料及提示，不能把差异归因于单独检索因素。",
            "同语料 BM25/E5 RRF 对照仅为离线检索消融。",
            "8 次充分支持上下文生成使用 v1.1 提示，24 次候选使用 v1 提示；提示同时变化，不是干净的检索因果对照。",
            "4 次复测使用 v1.2，最终 8 题冻结为 v1.3。最终提示的开发题覆盖未全部重跑。",
            "新标注来自 AI 原文复核，无人工审批；新题未额外标注干扰段落，未判定不能自动算错。",
            "同主题的综合验收题仍复用基础概念，样本很小，不能据此给出人类正确率。",
            "汇总修正部分可答题的完整题统计：完整覆盖已知支持不等于完整可回答；原始排名、位置及历史运行文件保留。",
            "部分初版实现只保存代码哈希，输入、证据及原始输出可复核，不能用最终代码复现所有历史阶段。"],
        "records":records}
    (OUT/"review-report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (ROOT/"evals/qa-baseline-summary-2026-10-14.json").write_text(json.dumps({k:v for k,v in summary.items() if k!="records"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 八主题逐题复核 · 2026-10-14","","复核者：本轮 AI 助手依据固定原文检查。不是人工审批或人类正确率。输出格式/引文通过不等于内容验收。","",
        "最终 8 题仅 4 题产生有效输出，其余被拦截；有效输出还存在偏题、具体内容不足等问题。保留旧默认，不增加模型调用。","",
        "冻结验收检索仅覆盖 10/23 个已标注必要要点，完整可答 1/6；不能以开发题 70/72 宣称已能解决新场景。未判定证据不自动算错。","",
        "| 阶段 | 题号 | 输出 | 本次检索已标注支持 | 复核发现 |","| --- | --- | --- | --- | --- |"]
    for r in records:
        support=r["retrieval_support"]
        hits=f"{support['covered']}/{support['expected']}" if support else "未统计"
        lines.append(f"| {r['phase']} | {r['id']} | {'有效结构/出处' if r['output_valid'] else '已拦截：'+str(r['failure_stage'])} | {hits} | {r['review_note']} |")
    lines += ["","实验边界："]+["- "+s for s in summary["experiment_limits"]]
    (ROOT/"reviews/qa-question-review-2026-10-14.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    choices=[next(OUT.glob("retest-TOOL-D1-*.json"))]+[OUT/f"oracle-{qid}.json" for qid in ("MEM-D1","RAG-D1","PLAN-D1","CTX-D1","MCP-D1","MULTI-D1","OBS-D1")]
    samples=[];lines=["# 八个真实试答样本","","2026-10-14；1 个开发复测、7 个充分支持上下文对照。全部为真实 Flash 输出。它们不代表日常检索的验收成绩；工具样本仍有冗长问题。原文引文核对通过，语义复核来源为 AI，无人工审批。",""]
    for path in choices:
        obj=json.loads(path.read_text(encoding="utf-8"));r=obj["result"];samples.append({"phase":obj.get("phase","retest"),"result":r})
        lines += ["## "+obj["scenario"]["question"],"",answer_text(r["answer"]),"","引用原文："]
        ev={e["evidence_id"]:e for e in r["evidence"]};seen=set()
        for unit in answer_units(r["answer"]):
            for ref in unit["references"]:
                if (ref["evidence_id"],ref["quote"]) in seen:continue
                seen.add((ref["evidence_id"],ref["quote"]));e=ev[ref["evidence_id"]]
                quote=ref["quote"]
                fence="`"*max(3,1+max((len(m.group()) for m in re.finditer(r"`+",quote)),default=0))
                lines += [f"- [{ref['evidence_id']} · {e.get('chapter',e['section'])}]({e['line_url']})", "",fence+"text",quote,fence,""]
        lines += [""]
    (ROOT/"reviews/qa-eight-samples-2026-10-14.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT/"representative-samples.json").write_text(json.dumps({"probes":samples},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":summary["status"],"budget":budget,"phases":phases},ensure_ascii=False))
if __name__=="__main__":main()
