"""Shared v2 answer contract / legacy read adapter / source checks."""
from __future__ import annotations
import re
from typing import Annotated,Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .core import CorpusError
from .limits import MAX_MISSING_CHARS,MAX_QUOTE_CHARS

ANSWER_SCHEMA_VERSION=2
class Strict(BaseModel):model_config=ConfigDict(extra="forbid",strict=True)
class Reference(Strict):
    evidence_id:str=Field(pattern=r"^E[1-8]$")
    quote:str=Field(min_length=10,max_length=MAX_QUOTE_CHARS)
class CitedText(Strict):
    text:str=Field(min_length=1,max_length=1800)
    references:list[Reference]=Field(min_length=1,max_length=8)
class Paragraph(CitedText):type:Literal["paragraph"]
class ListBlock(Strict):
    type:Literal["list"]
    ordered:bool=False
    items:list[CitedText]=Field(min_length=1,max_length=12)
class CodeBlock(Strict):
    type:Literal["code"]
    origin:Literal["source","illustrative"]
    language:str=Field(min_length=1,max_length=30)
    code:str=Field(min_length=1,max_length=3200)
    references:list[Reference]=Field(min_length=1,max_length=8)
class TableRow(Strict):
    cells:list[str]=Field(min_length=1,max_length=6)
    references:list[Reference]=Field(min_length=1,max_length=8)
class TableBlock(Strict):
    type:Literal["table"]
    columns:list[str]=Field(min_length=1,max_length=6)
    rows:list[TableRow]=Field(min_length=1,max_length=10)
    @model_validator(mode="after")
    def widths(self):
        if any(len(r.cells)!=len(self.columns) for r in self.rows):raise ValueError("表格行列数量不同。")
        if any(len(c)>800 for r in self.rows for c in r.cells) or any(len(c)>120 for c in self.columns):raise ValueError("表格单元格过长。")
        return self
Block=Annotated[Paragraph|ListBlock|CodeBlock|TableBlock,Field(discriminator="type")]
class AnswerV2(Strict):
    schema_version:Literal[2]
    status:Literal["answered","partial","insufficient"]
    blocks:list[Block]=Field(max_length=20)
    missing_information:str=Field(default="",max_length=MAX_MISSING_CHARS)
    @model_validator(mode="after")
    def shape(self):
        if self.status=="insufficient" and (self.blocks or not self.missing_information.strip()):raise ValueError("资料不足须无事实正文并说明具体缺口。")
        if self.status!="insufficient" and not self.blocks:raise ValueError("回答缺少正文。")
        if (self.status=="partial")!=bool(self.missing_information.strip()) and self.status!="insufficient":raise ValueError("回答状态与资料缺口不符。")
        units=answer_units(self.model_dump())
        if len(units)>40 or sum(len(u["text"]) for u in units)>16000:raise ValueError("回答超过总容量。")
        return self

def as_blocks(answer):
    """Read-only conversion; never rewrites old discussions on disk."""
    if not answer:return {"schema_version":2,"status":"insufficient","blocks":[],"missing_information":""}
    if answer.get("schema_version")==2:return answer
    claims=answer.get("claims",[])
    items=[{"text":c["text"],"references":[{"evidence_id":c["evidence_id"],"quote":c["quote"]}]} for c in claims]
    blocks=([{"type":"list","ordered":answer.get("format")=="steps","items":items}] if items and answer.get("format") in {"steps","bullets"}
            else [{"type":"paragraph",**item} for item in items])
    return {"schema_version":2,"status":answer["status"],"blocks":blocks,"missing_information":answer.get("missing_information","")}

def answer_units(answer):
    if "claims" in answer:
        return [{"text":c["text"],"references":[{"evidence_id":c["evidence_id"],"quote":c["quote"]}] if c.get("evidence_id") and c.get("quote") else [],"kind":"prose"} for c in answer["claims"]]
    units=[]
    for block in answer.get("blocks",[]):
        if block["type"]=="paragraph":units.append({"text":block["text"],"references":block["references"],"kind":"prose"})
        elif block["type"]=="list":units.extend({**item,"kind":"prose"} for item in block["items"])
        elif block["type"]=="table":units.extend({"text":" | ".join(row["cells"]),"references":row["references"],"kind":"prose"} for row in block["rows"])
        elif block["type"]=="code":units.append({"text":block["code"],"references":block["references"],"kind":"code","origin":block["origin"]})
    return units

def answer_text(answer):return "\n\n".join(u["text"] for u in answer_units(answer))+(("\n\n"+answer["missing_information"]) if answer.get("missing_information") else "")

def normalize_with_positions(text):
    hidden=set()
    for m in re.finditer(r"<[^>]+>|\*\*|__",text):hidden.update(range(m.start(),m.end()))
    # Markdown display syntax is not claim text. Retain labels and their raw
    # character map; do not skip intervening sentences, pipes, or ellipses.
    for m in re.finditer(r"\[([^\]\n]+)\]\((?:[^()\n]|\([^()\n]*\))*\)",text):
        hidden.add(m.start());hidden.update(range(m.start(1)+len(m[1]),m.end()))
    for m in re.finditer(r"`[^`\n]+`|(?<!\w)_[^_\n]+_(?!\w)|(?<!\*)\*[^*\n]+\*(?!\*)",text):
        hidden.add(m.start());hidden.add(m.end()-1)
    chars=[];positions=[];space=True
    for i,ch in enumerate(text):
        if i in hidden:continue
        if ch.isspace():
            if not space:chars.append(" ");positions.append(i)
            space=True
        else:chars.append(ch);positions.append(i);space=False
    if chars and chars[-1]==" ":chars.pop();positions.pop()
    return "".join(chars),positions

def verify_reference(ref,item):
    if not item:raise CorpusError("引文编号不属于本轮证据。")
    quote=ref["quote"];raw=item["text"];context=item["context_text"]
    if item.get("content_type")=="code":
        pos=raw.find(quote)
        if pos<0 or quote not in context:raise CorpusError("代码引文不是保留缩进的连续原文。")
        start,end=pos,pos+len(quote)
    else:
        q,_=normalize_with_positions(quote);body,_=normalize_with_positions(context);original,positions=normalize_with_positions(raw)
        pos=original.find(q)
        if len(q)<10 or q not in body or pos<0:raise CorpusError("引文非本轮正文与原文的连续片段。")
        start,end=positions[pos],positions[pos+len(q)-1]+1
    location={"evidence_id":ref["evidence_id"],"source_id":item["source_id"],"start_char":item["start_char"]+start,"end_char":item["start_char"]+end,
            "start_line":item["start_line"]+raw.count("\n",0,start),"end_line":item["start_line"]+raw.count("\n",0,end-1)}
    if item.get('source_locator',{}).get('kind')=='notebook_cell':
        parent=item['source_locator']
        location['source_locator']={'kind':'notebook_cell','cell_index':parent['cell_index'],
            'start_line':location['start_line']-parent['view_start_line']+1,
            'end_line':location['end_line']-parent['view_start_line']+1}
    return location

def validate_v2(raw,evidence):
    answer=AnswerV2.model_validate_json(raw);by_id={e["evidence_id"]:e for e in evidence}
    for unit in answer_units(answer.model_dump()):
        for ref in unit["references"]:verify_reference(ref,by_id.get(ref["evidence_id"]))
        if unit.get("origin")=="source":
            candidates=[by_id[r["evidence_id"]] for r in unit["references"] if r["evidence_id"] in by_id]
            if not any(e.get("content_type")=="code" and unit["text"] in e["context_text"] and unit["text"] in e["text"] for e in candidates):raise CorpusError("标为原文的代码未匹配实际片段。")
    return answer

def quote_locations(answer,evidence):
    by_id={e["evidence_id"]:e for e in evidence}
    return [verify_reference(ref,by_id.get(ref["evidence_id"])) for unit in answer_units(answer) for ref in unit["references"]]
