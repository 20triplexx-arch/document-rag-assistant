"""Compact generation references resolved to exact public v2 quotations locally."""
from __future__ import annotations

from copy import deepcopy
import json
import re

from .answer_schema import AnswerV2, verify_reference
from .core import CorpusError


class GenerationShapeError(CorpusError):
    """The generated wire object violates its declared structural contract."""


def generation_schema(*, allow_table=True, spans=None, block_types=None, facts=None):
    schema = deepcopy(AnswerV2.model_json_schema())
    # Public v2 status/version are redundant on the generation wire. Derive them
    # from complete blocks and the typed gap string, without editing any prose.
    for name in ('schema_version','status'):
        schema['properties'].pop(name)
        schema['required'].remove(name)
    schema['required']=['blocks']
    ref = schema["$defs"]["Reference"]
    ref["properties"].pop("quote")
    ref["properties"]["span_id"] = {"type": "string", "pattern": r"^S[1-9][0-9]{0,2}$"}
    ref["required"] = ["evidence_id", "span_id"]
    if spans is not None:
        schema['$defs']['Reference']={'type':'string','enum':[eid+':'+s['span_id'] for eid,values in spans.items() for s in values]}
        paragraph=schema['$defs']['Paragraph']
        paragraph['properties'].pop('type')
        paragraph['required'].remove('type')
    for name in ("ListBlock", "TableBlock"):
        schema["$defs"][name]["properties"]["references"] = {"type":"array", "items":{"$ref":"#/$defs/Reference"},"maxItems":8}
    original_code = schema["$defs"]["CodeBlock"]
    source_code = deepcopy(original_code)
    source_code["properties"].pop("code")
    source_code["properties"]["origin"] = {"const":"source","type":"string"}
    source_code["properties"]["code_reference"] = {"type":"object","additionalProperties":False,
        "properties":{"evidence_id":{"type":"string","pattern":"^E[1-8]$"},
                      "span_ids":{"type":"array","minItems":1,"maxItems":6,"items":{"type":"string","pattern":r"^S[1-9][0-9]{0,2}$"}}},
        "required":["evidence_id","span_ids"]}
    source_code["required"] = ["type","origin","language","code_reference"]
    illustration=deepcopy(original_code);illustration["properties"]["origin"]={"const":"illustrative","type":"string"}
    schema["$defs"]["CodeBlock"] = {"oneOf":[source_code, illustration]}
    if not allow_table:
        items=schema["properties"]["blocks"]["items"]
        items["oneOf"]=[entry for entry in items["oneOf"] if entry.get("$ref")!="#/$defs/TableBlock"]
        items["discriminator"]["mapping"].pop("table",None)
    if block_types is not None:
        names={'paragraph':'Paragraph','list':'ListBlock','code':'CodeBlock','table':'TableBlock'}
        allowed={'#/$defs/'+names[k] for k in block_types}
        items=schema['properties']['blocks']['items']
        choices=[v for v in items['oneOf'] if v.get('$ref') in allowed]
        if len(choices)==1:schema['properties']['blocks']['items']=choices[0]
        else:
            items['oneOf']=choices
            items['discriminator']['mapping']={k:v for k,v in items['discriminator']['mapping'].items() if k in block_types}
    if facts:
        schema['$defs']['SourceFacts']={'type':'object','additionalProperties':False,
            'properties':{'type':{'const':'source_facts','type':'string'},
                          'fact_ids':{'type':'array','minItems':1,'maxItems':2,'uniqueItems':True,
                                      'items':{'type':'string','enum':list(facts)}}},'required':['type','fact_ids']}
        items=schema['properties']['blocks']['items']
        choices=items.get('oneOf',[items])
        schema['properties']['blocks']['items']={'oneOf':choices+[{'$ref':'#/$defs/SourceFacts'}]}
    return schema


def spans_for_evidence(evidence):
    """Never bridge masked text; every exported span passes the public verifier."""
    by_evidence = {}
    for item in evidence:
        raw = item["text"]
        spans = []
        # Keep paragraph context; code uses complete lines whenever possible.
        if item.get("content_type") == "code":
            ranges = [(0, len(raw))]
        else:
            ranges = [(m.start(), m.end()) for m in re.finditer(r"[^\n]+(?:\n(?![ \t]*\n)[^\n]+)*", raw)]
        candidates = []
        for start, end in ranges:
            while end - start > 720:
                window = raw[start:start + 720]
                stops = [m.end() for m in re.finditer(r"[。！？；.!?;](?:\s|$)|\n", window)]
                cut = start + (stops[-1] if stops and stops[-1] >= 100 else 720)
                candidates.append((start, cut)); start = cut
            candidates.append((start, end))
        if item.get("content_type") == "code" and len(candidates)>1 and candidates[-1][1]-candidates[-1][0]<10:
            left,right=candidates.pop();previous=candidates.pop()
            candidates.append((previous[0],right))
        seen = set()
        for start, end in candidates:
            quote = raw[start:end]
            if item.get("content_type") != "code":
                quote = quote.strip()
            if not 10 <= len(quote) <= 800 or (quote in seen and item.get("content_type") != "code"):
                continue
            try:
                location = verify_reference({"evidence_id": item["evidence_id"], "quote": quote}, item)
            except CorpusError:
                # A paragraph containing a masked component may still have valid
                # individual prose lines. Try those without concatenating them.
                for line in quote.splitlines():
                    if not 10 <= len(line) <= 800 or line in seen:
                        continue
                    try:
                        loc = verify_reference({"evidence_id": item["evidence_id"], "quote": line}, item)
                    except CorpusError:
                        continue
                    spans.append({"span_id": f"S{len(spans)+1}", "text": line, **loc}); seen.add(line)
                continue
            if item.get("content_type") == "code":
                location.update(start_char=item["start_char"]+start,end_char=item["start_char"]+end,
                                start_line=item["start_line"]+raw.count("\n",0,start),
                                end_line=item["start_line"]+raw.count("\n",0,end-1))
            spans.append({"span_id": f"S{len(spans)+1}", "text": quote, "content_type":item.get("content_type","prose"), **location}); seen.add(quote)
        by_evidence[item["evidence_id"]] = spans
    return by_evidence


def hydrate(value, spans, facts=None):
    """Only IDs supplied this turn can turn into a quotation; no fuzzy repair."""
    records = {(eid, span["span_id"]): span for eid, values in spans.items() for span in values}
    lookup = {key:span["text"] for key,span in records.items()}

    def visit(node):
        if isinstance(node, list):
            return [visit(item) for item in node]
        if not isinstance(node, dict):
            return node
        if node.get('type')=='source_facts':
            ids=node.get('fact_ids')
            if set(node)!={'type','fact_ids'} or not isinstance(ids,list) or not 1<=len(ids)<=2 or any(not isinstance(i,str) or i not in (facts or {}) for i in ids) or len(set(ids))!=len(ids):
                raise GenerationShapeError('静态事实编号不属于本轮，或混入自定义文本。')
            selected=[facts[i] for i in ids]
            refs=list(dict.fromkeys(ref for fact in selected for ref in fact['references']))
            return visit({'text':' '.join(fact['text'] for fact in selected),'references':refs})
        result = {}
        for key, item in node.items():
            if key == "references":
                if not isinstance(item, list):
                    raise CorpusError("引用编号结构无效。")
                refs = []
                for ref in item:
                    if isinstance(ref,str):
                        match=re.fullmatch(r'(E[1-8]):(S[1-9][0-9]{0,2})',ref)
                        if not match:raise CorpusError('引用必须选择本轮完整片段编号。')
                        ref={'evidence_id':match[1],'span_id':match[2]}
                    if not isinstance(ref, dict) or set(ref) != {"evidence_id", "span_id"}:
                        raise CorpusError("引用必须选择本轮片段编号。")
                    eid, sid = ref["evidence_id"], ref["span_id"]
                    if isinstance(eid,str) and isinstance(sid,str) and sid.startswith(eid+':'):sid=sid[len(eid)+1:]
                    if not isinstance(eid, str) or not isinstance(sid, str) or (eid, sid) not in lookup:
                        raise CorpusError("引用编号不属于本轮原文片段。")
                    refs.append({"evidence_id": eid, "quote": lookup[eid, sid]})
                result[key] = refs
            else:
                result[key] = visit(item)
        if node.get("type") in {"table","list"} and "references" in result:
            # The generation wire permits a redundant wrapper summary. It may
            # only repeat child citations; every row/item is still checked itself.
            children=result.get("rows",[]) if node["type"]=="table" else result.get("items",[])
            child_refs=[ref for child in children if isinstance(child,dict) for ref in child.get("references",[])]
            if any(ref not in child_refs for ref in result["references"]):
                raise CorpusError("父块引用不是子项引用的重复汇总。")
            result.pop("references")
        if "code_reference" in result:
            selection=result.pop("code_reference")
            if result.get("type")!="code" or result.get("origin")!="source" or "code" in result:
                raise CorpusError("原文代码选择结构无效。")
            if not isinstance(selection,dict) or set(selection)!={"evidence_id","span_ids"}:
                raise CorpusError("原文代码编号结构无效。")
            eid,ids=selection["evidence_id"],selection["span_ids"]
            if isinstance(eid,str) and isinstance(ids,list):
                ids=[sid[len(eid)+1:] if isinstance(sid,str) and sid.startswith(eid+':') else sid for sid in ids]
            if not isinstance(eid,str) or not isinstance(ids,list) or not 1<=len(ids)<=6 or any(not isinstance(sid,str) or (eid,sid) not in records for sid in ids):
                raise CorpusError("原文代码编号不属于本轮。")
            selected=[records[eid,sid] for sid in ids]
            if any(s.get("content_type")!="code" for s in selected) or any(a["end_char"]!=b["start_char"] for a,b in zip(selected,selected[1:])):
                raise CorpusError("原文代码片段不连续或不是代码。")
            references=[{"evidence_id":eid,"quote":s["text"]} for s in selected]
            if any(ref not in references for ref in result.get("references",[])):
                raise CorpusError("原文代码与引用选择不一致。")
            result["code"]="".join(s["text"] for s in selected)
            result["references"]=references
        return result
    result=visit(value)
    # A text+references object in a content-block slot has exactly one meaning.
    # List items retain the untagged CitedText shape; never add tags recursively.
    def paragraph_block(block):
        return {'type':'paragraph',**block} if isinstance(block,dict) and set(block)=={'text','references'} else block
    if isinstance(result,dict) and 'blocks' in result and isinstance(result['blocks'],list):
        result['blocks']=[paragraph_block(block) for block in result['blocks']]
    else:result=paragraph_block(result)
    if isinstance(result,dict) and 'blocks' in result and set(result)<={'blocks','missing_information'}:
        result.setdefault('missing_information','')
        if not isinstance(result['blocks'],list) or not isinstance(result['missing_information'],str):
            raise CorpusError('生成正文与缺口类型无效。')
        result={'schema_version':2,'status':('partial' if result['blocks'] else 'insufficient') if result['missing_information'].strip() else 'answered',**result}
    return result


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate response field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)
