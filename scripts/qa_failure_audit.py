"""Inspect public captured failures without another model request."""
from pathlib import Path
import sys,json,sqlite3,difflib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from study_rag.answer_schema import AnswerV2,answer_units,verify_reference
OUT=Path(__file__).resolve().parents[1]/"output/qa-v3"
def main():
    with sqlite3.connect(OUT/"budget.sqlite3") as db:rows=db.execute("SELECT question_id,raw FROM calls WHERE phase='candidate'").fetchall()
    findings=[]
    for qid,raw in rows:
        record=json.loads((OUT/f"candidate-{qid}.json").read_text(encoding="utf-8"));result=record["result"]
        if result["status"]=="CITED_DRAFT":continue
        issues=[]
        try:
            parsed=json.loads(raw)
        except json.JSONDecodeError as e:
            issues.append({"kind":"invalid_json","line":e.lineno,"column":e.colno,"near":raw[max(0,e.pos-80):e.pos+80]});parsed=None
        if parsed:
            try:AnswerV2.model_validate(parsed)
            except ValueError as e:issues.append({"kind":"schema","issues":str(e)[:800]})
            ev={e["evidence_id"]:e for e in result["evidence"]}
            for unit in answer_units(parsed):
                for ref in unit["references"]:
                    try:verify_reference(ref,ev.get(ref["evidence_id"]))
                    except (ValueError,KeyError) as e:
                        issues.append({"kind":"quote","id":ref["evidence_id"],"quote":ref["quote"],"reason":str(e)})
                if unit.get("origin")=="source" and not any(unit["text"] in e["context_text"] for e in ev.values()):
                    issues.append({"kind":"source_code","reason":"code changes whitespace or stitches multiple fragments","code_prefix":unit["text"][:160]})
        findings.append({"id":qid,"stage":result.get("failure_stage"),"issues":issues})
    (OUT/"candidate-failure-audit.json").write_text(json.dumps({"review_origin":"rule audit of captured public responses; no model judge","findings":findings},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for item in findings:
        print(item["id"],json.dumps(item["issues"][:3],ensure_ascii=False)[:1100])
if __name__=="__main__":main()
