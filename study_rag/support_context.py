"""Build an oracle intervention from actual annotated positions, without a model."""
from .core import corpus_catalog
from .rag import visible_prose

def annotated_evidence(question,loaded):
    sources,texts,masks=loaded[4:];catalog=corpus_catalog(loaded[2]);unique={}
    for point in question.points:
        spans=point.supports if getattr(point,"coverage","any")=="all" else point.supports[:1]
        for span in spans:unique[(span.source_id,span.start_char,span.end_char,getattr(span,"kind","prose"))]=span
    ev=[]
    for (sid,a,b,kind),span in unique.items():
        source=sources[sid];text=texts[sid][a:b];meta=catalog["chapters"][sid]
        ev.append({"evidence_id":f"E{len(ev)+1}","source_id":sid,"book":source.book,"chapter":source.chapter,"path":source.path,
            "display_name":next(book["display_name"] for book in catalog["books"] if book["book"]==source.book),
            "section":"已标注支持上下文；复核来源见题集","language":meta["language"],"content_type":kind,
            "code_role":"implementation" if source.path.endswith(".py") else "example" if kind=="code" else None,
            "applicable_versions":meta.get("applicable_versions",["unknown"]),"start_char":a,"end_char":b,"start_line":span.start_line,"end_line":span.end_line,
            "text":text,"context_text":text if kind=="code" else visible_prose(text,masks[sid][a:b]),"source_url":source.source_url,
            "line_url":f"{source.source_url}#L{span.start_line}-L{span.end_line}","score":0.0})
    if len(ev)>8 or any(len(e["context_text"])>3200 for e in ev) or sum(len(e["context_text"]) for e in ev)>20000:
        raise ValueError("已标注支持上下文超出全局证据预算，不能把干预当成充分上下文。")
    return ev
