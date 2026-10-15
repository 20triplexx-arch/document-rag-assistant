"""Summarize actual public trials, with separate source/meaning/speed decisions."""
from pathlib import Path
import json
import statistics
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.answer_schema import answer_text
from study_rag.qa_evaluation import load_qa_dataset, QA_DATASET, QAPoint, span_matches

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"output/qa-speed-20261015-v1"
NOTES={
    "SPEED-A1":("fail","非法字符和除零主路径有源码，但把字面表达式 1 混入空表达式失败路径；结尾又从函数内部过滤推导校验责任主要在函数，超出框架证据，且存在重复和无必要缺口说明。"),
    "SPEED-A2":("revise","thread/namespace 主体有依据；引用只说明可后台更新，并未覆盖具体延迟取舍，回答却补充不阻塞与延迟；把读取时机限定在新 thread 初始化也过窄。"),
    "SPEED-A3":("fail","关键调用没有显式传递重排结果这一点正确；但把本地定义的 perform_search 说成从 raglite 导入，并断言内部重新检索与不复用，随后又承认缺少该库实现，前后不一致。"),
    "SPEED-A4":("revise","能区分 todo 状态与实际报告；多段重复这一结论，并加入持久化/能力泛述，未把虚拟文件系统后端条件说清楚，聚焦度未达标。"),
    "SPEED-A5":("pass","身份由 runtime 注入而非模型填写、模型输入与工具上下文的区分、trim 与 delete 的影响均能定位本轮资料；摘要部分偏长，可继续精简。"),
    "SPEED-A6":("fail","span_id 写成 5 而非本轮有效编号，严格拦截且撤回预览；检索也未覆盖 server/discover 必要入口，原始正文再次混淆会话与连接状态。未自动改编号。"),
    "SPEED-A7":("revise","选择 handoffs/subagents 的方向正确；把 Deep Agents 特有的 isolated/fork 配置当作未限定框架的通用 subagents 行为，且重复结论。"),
    "SPEED-A8":("pass","两轮 trace、三个 run、同一 thread 与独立正确性评估均有本轮依据；说明仍偏长，有可删的重复与额外工具举例。"),
}


def main():
    records={phase:[json.loads(p.read_text(encoding="utf-8")) for p in sorted(OUT.glob(phase+"-*.json"))] for phase in ("baseline","dev","acceptance")}
    loaded=load_qa_dataset(QA_DATASET,ROOT/"data/qa-20261014-v1")
    texts,masks=loaded[5],loaded[6]
    rows=[]
    for record in records["acceptance"]:
        scenario,result=record["scenario"],record["result"]
        points=[QAPoint.model_validate(p) for p in scenario["points"]]
        covered=[]
        for point in points:
            hits=[any(span_matches(span,item,texts,masks) for item in result["evidence"]) for span in point.supports]
            if (all(hits) if point.coverage=="all" else any(hits)):covered.append(point.id)
        verdict,note=NOTES[scenario["id"]]
        rows.append({"id":scenario["id"],"status":result["status"],"retrieval_covered":covered,"expected_points":len(points),
                     "review":verdict,"note":note,"first_block_seconds":record["client_first_block_seconds"],
                     "total_seconds":record["client_total_seconds"]})
    with sqlite3.connect((OUT/"budget.sqlite3").resolve().as_uri()+"?mode=ro",uri=True) as db:
        count,tokens=db.execute("SELECT count(*),sum(reserved) FROM calls").fetchone()
        states=db.execute("SELECT state,count(*) FROM calls GROUP BY state").fetchall()
        usages=[json.loads(row[0]) for row in db.execute("SELECT usage FROM calls WHERE usage IS NOT NULL")]
    valid=[r for r in records["acceptance"] if r["result"].get("answer")]
    baseline={r["scenario"]["id"]:r for r in records["baseline"]}
    pairs=[{"id":r["scenario"]["id"],"before_seconds":baseline[r["scenario"]["id"]]["client_total_seconds"],
            "after_seconds":r["client_total_seconds"],"before_status":baseline[r["scenario"]["id"]]["result"]["status"],"after_status":r["result"]["status"]}
           for r in records["dev"] if r["scenario"]["id"] in baseline]
    shared=json.loads((OUT/"shared-performance.json").read_text(encoding="utf-8"))
    retrieval=json.loads((OUT/"retrieval.json").read_text(encoding="utf-8"))
    summary={"date":"2026-10-15","rollout":False,"status":"KEEP_OLD_DEFAULT_SHARED_SPEED_APPLIED",
        "budget":{"calls_reserved":count,"tokens_reserved":tokens,"limit_calls":20,"limit_tokens":1_000_000,"states":dict(states),
                  "reported_prompt_tokens":sum(u.get("prompt_tokens",0) or 0 for u in usages),"reported_output_tokens":sum(u.get("output_tokens",0) or 0 for u in usages)},
        "acceptance":{"questions":len(rows),"structurally_valid":len(valid),"strict_content_pass":sum(r["review"]=="pass" for r in rows),
                      "valid_first_block_median_seconds":statistics.median(r["client_first_block_seconds"] for r in valid),
                      "valid_total_median_seconds":statistics.median(r["client_total_seconds"] for r in valid),"rows":rows},
        "shared_performance":shared,"candidate_retrieval_benchmark":retrieval["benchmark"],"retrieval_gates":retrieval["gates"],"pairs":pairs,
        "limitations":["AI source review, not human accuracy or approval.","First baseline lost to sandbox network; reservation retained without retry; three HTTP baseline records remain.",
                        "Paired development runs used v2; final acceptance used v2.1 on different scenarios. No final paired 25% speed acceptance claim.",
                        "Only one paired development question produced a valid answer on both sides; failed requests are never counted as successful-answer speed gains.",
                        "Frozen new scenarios reuse previously annotated concepts and source spans; not an independent human benchmark.",
                        "After acceptance only legacy v1 retrieval precomputation was extended; source positions checked unchanged. No additional generation calls.",
                        "Baseline source snapshot retained; development/acceptance initially retained hashes, inputs and raw outputs, not every intermediate source revision."]}
    (OUT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    public_summary={**summary,"shared_performance":{key:{field:value for field,value in data.items() if field not in {"samples","evidence"}} if isinstance(data,dict) else data for key,data in shared.items()},
                    "candidate_retrieval_benchmark":{key:value for key,value in retrieval["benchmark"].items() if key!="samples"}}
    (ROOT/"evals/qa-speed-summary-2026-10-15.json").write_text(json.dumps(public_summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    lines=["# 问答质量与速度逐题复核", "", "2026-10-15；AI 原文复核，不是人工正确率或批准。候选未通过，保留旧默认。", "",
           "| 题号 | 结构/出处 | 内容复核 | 首段/总耗时（秒） |", "| --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['id']} | {row['status']} | {row['review']} | {row['first_block_seconds']:.2f} / {row['total_seconds']:.2f} |")
    for record,row in zip(records["acceptance"],rows):
        lines += ["", "## "+row["id"], "", record["scenario"]["question"], "", row["note"], "",
                  f"检索标注支持覆盖：{len(row['retrieval_covered'])}/{row['expected_points']}；该数不是内容正确率。", ""]
        if record["result"].get("answer"):
            lines += [answer_text(record["result"]["answer"]), ""]
        else:lines += ["回答未展示；原始输出保存在本机独立预算账本，仅用于失败复核。", ""]
        for item in record["result"]["evidence"]:
            lines.append(f"- [{item['evidence_id']} · {item['section']}]({item['line_url']})")
    review=ROOT/"reviews/qa-speed-2026-10-15.md"
    review.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"budget":summary["budget"],"acceptance":{k:v for k,v in summary["acceptance"].items() if k!="rows"},"shared_performance":{k:{a:b for a,b in v.items() if a not in ["samples","evidence"]} if isinstance(v,dict) else v for k,v in shared.items()}},ensure_ascii=True))


if __name__=="__main__":main()
