"""Offset-preserving static Python / fenced-code indexing. Never imports source code."""
import ast
import re

def _chunks(source,raw,text,ranges,max_chars,overlap):
    from .core import Chunk,digest,json_text
    chunks=[]
    for left,right,label in ranges:
        start=left
        while start<right:
            end=min(right,start+max_chars)
            if end<right:
                newline=text.rfind("\n",start+max_chars//2,end)
                if newline>=0:end=newline+1
            if text[start:end].strip():
                identity=json_text([source.source_id,digest(raw),label,start,end])
                chunks.append(Chunk(source.source_id+"-"+digest(identity.encode())[:20],source.source_id,label,
                    start,end,text.count("\n",0,start)+1,text.count("\n",0,end-1)+1,text[start:end]))
            if end==right:break
            start=max(start+1,end-overlap)
    return chunks

def python_chunks(source,raw,*,max_chars=1400,overlap=160):
    from .core import validate_text,CorpusError
    text=validate_text(raw)
    try: tree=ast.parse(text,filename=source.path)
    except (SyntaxError,ValueError):raise CorpusError("Python 源码无法静态解析："+source.path) from None
    lines=text.splitlines(keepends=True); offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    def position(line,col):
        # AST columns are UTF-8 byte offsets, unlike evidence character offsets.
        return offsets[line-1]+len(lines[line-1].encode("utf-8")[:col].decode("utf-8"))
    ranges=[];cursor=0
    for node in tree.body:
        decorators=getattr(node,"decorator_list",[])
        first=min([node.lineno]+[d.lineno for d in decorators])
        start=offsets[first-1]
        end=position(node.end_lineno,node.end_col_offset)
        if end<len(text) and text[end]=="\n":end+=1
        if start>cursor:ranges.append((cursor,start,"[code] module comments"))
        label=type(node).__name__+" "+getattr(node,"name", "module statement")
        ranges.append((start,end,"[code] "+label));cursor=end
    if cursor<len(text):ranges.append((cursor,len(text),"[code] module comments"))
    return _chunks(source,raw,text,ranges,max_chars,overlap)

def markdown_code_chunks(source,raw):
    from .core import validate_text
    from .mdx import mdx_mask
    text=validate_text(raw);structural=mdx_mask(text) if source.path.endswith(".mdx") else text
    ranges=[];marker="";length=0;start=offset=0;language="";heading="正文"
    for line in structural.splitlines(keepends=True):
        # Fences nested in Markdown lists may have four or more leading spaces.
        match=re.match(r"^[ \t]*(`{3,}|~{3,})(.*)$",line)
        if match:
            token,suffix=match.groups()
            if not marker:
                marker,length=token[0],len(token);start=offset+len(line);language=suffix.split()[0] if suffix.strip() else "text"
            elif token[0]==marker and len(token)>=length and not suffix.strip():
                ranges.append((start,offset,f"[code] {heading} · {language}"));marker=""
        elif not marker:
            title=re.match(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$",line)
            if title:heading=title[1]
        offset+=len(line)
    if marker:ranges.append((start,len(text),f"[code] {heading} · {language}"))
    return _chunks(source,raw,text,ranges,1400,160)
