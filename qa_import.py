"""Pinned QA source discovery/import. No execution of third party code or JSX."""
from __future__ import annotations
import argparse, hashlib, json, posixpath, re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
from study_rag.core import digest, json_text, load_corpus

PROJECT = Path(__file__).resolve().parent
BASE = PROJECT / "data/courses-cases-20261010-v1"
TARGET = PROJECT / "data/qa-20261014-v1"
CACHE = PROJECT / "output/qa-source-cache"
LC_REPO, LC_COMMIT = "langchain-ai/docs", "a28c75411093fdc0e57b03c1d6486ba78f005f51"
MCP_REPO, MCP_COMMIT = "modelcontextprotocol/modelcontextprotocol", "5ea996028df322ce97d1c906731cf8c05a6e268e"
LC_PAGES = [
    ("src/oss/concepts/memory.mdx","记忆概念",["memory"]),
    ("src/oss/langchain/tools.mdx","工具调用",["tools"]),
    ("src/oss/langchain/short-term-memory.mdx","短期记忆",["memory","context"]),
    ("src/oss/langchain/long-term-memory.mdx","长期记忆",["memory"]),
    ("src/oss/langchain/retrieval.mdx","检索与 RAG",["rag"]),
    ("src/oss/langchain/context-engineering.mdx","上下文工程",["context"]),
    ("src/oss/langchain/observability.mdx","Agent 可观测性",["observability"]),
    ("src/oss/langchain/multi-agent/index.mdx","多 Agent 模式",["multi_agent"]),
    ("src/oss/langchain/multi-agent/subagents.mdx","子 Agent",["multi_agent","context"]),
    ("src/oss/langchain/multi-agent/handoffs.mdx","控制权转接",["multi_agent"]),
    ("src/oss/deepagents/overview.mdx","Deep Agents 概览",["planning","context","multi_agent"]),
    ("src/langsmith/observability-concepts.mdx","LangSmith 可观测性概念",["observability"]),
]
MCP_PATHS = ["index.mdx","architecture/index.mdx","basic/index.mdx","server/tools.mdx","server/resources.mdx","server/prompts.mdx"]

def blob(raw):
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()

def read(url):
    with urlopen(Request(url,headers={"User-Agent":"study-rag-pinned-qa-import"}),timeout=45) as r:
        data = r.read(8_000_001)
    if len(data)>8_000_000: raise ValueError("Public source too large")
    return data

def source_id(repo,path):
    return "qa-"+hashlib.sha256((repo+":"+path).encode()).hexdigest()[:20]

def local_mdx_dependencies(text, path, available, repository):
    """Only statically declared local MDX; remote paths/JS/components are not bodies."""
    imports = re.findall(r"\b(?:from\s*|import\s*)['\"]([^'\"]+\.mdx)['\"]",text)
    # A docs redirect is a local body dependency, not substantive teaching text.
    redirect = re.fullmatch(r"---\s*\n.*?\nurl:\s*['\"]([^'\"]+)['\"]\s*\n---\s*", text, re.S)
    if redirect and repository == LC_REPO:
        imports.append(redirect[1].rstrip("/")+".mdx")
    result=[]
    for target in imports:
        if re.match(r"^(?:https?:|//|data:)",target): continue
        candidates = (["src/"+target.lstrip("/"),target.lstrip("/")] if target.startswith("/") else
                      [posixpath.normpath(posixpath.join(posixpath.dirname(path),target))])
        matches=[p for p in candidates if p in available]
        if len(matches)!=1: raise ValueError(f"Unresolved or ambiguous local MDX import: {repository}:{path}:{target}")
        result.append(matches[0])
    return sorted(set(result))

def discover():
    CACHE.mkdir(parents=True,exist_ok=True)
    base, contents=load_corpus(BASE)
    if len(contents)!=216: raise ValueError("Expected preserved 216 sources")
    sources=[deepcopy(r["source"]) for r in base["documents"]]
    catalog=deepcopy(base["catalog"])
    catalog["version"]=3
    tree_by_repo={}
    def get_tree(pair):
        repo,commit=pair
        dest=CACHE/(repo.replace("/","-")+"-tree.json")
        raw=dest.read_bytes() if dest.exists() else read(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1")
        tree=json.loads(raw)
        if tree.get("truncated") or tree.get("sha")!=commit: raise ValueError("Unverified tree")
        if not dest.exists():dest.write_bytes(raw)
        return repo,{e["path"]:e for e in tree["tree"] if e["type"]=="blob"}
    for repo, entries in map(get_tree,[(LC_REPO,LC_COMMIT),(MCP_REPO,MCP_COMMIT)]):tree_by_repo[repo]=entries
    def download(repo,commit,path,entry):
        dest=CACHE/(source_id(repo,path)+PurePosixPath(path).suffix)
        raw=dest.read_bytes() if dest.exists() else read(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}")
        if blob(raw)!=entry["sha"] or len(raw)!=entry["size"]: raise ValueError("Blob mismatch: "+path)
        raw.decode("utf-8-sig")
        if not dest.exists():dest.write_bytes(raw)
        return raw
    for i,(book,repo,commit,label,license_name) in enumerate([
        ("langchain-official",LC_REPO,LC_COMMIT,"LangChain / LangSmith 官方文档","MIT"),
        ("mcp-specification",MCP_REPO,MCP_COMMIT,"MCP 官方规范（双版本）","Apache-2.0 / legacy MIT / CC-BY-4.0; see full notice")],5):
        license_raw=download(repo,commit,"LICENSE",tree_by_repo[repo]["LICENSE"])
        catalog["books"].append({"book":book,"display_name":label,"order":i,"kind":"official_documentation",
            "repository":repo,"commit":commit,"license":license_name,"license_path":"LICENSE",
            "license_text":license_raw.decode("utf-8"),"license_git_blob":blob(license_raw)})
    code_records=[]
    for parent in list(sources):
        meta=catalog["chapters"][parent["source_id"]]
        for impl in meta.get("implementation_files",[]):
            sid=source_id(parent["repository"],impl["path"])
            code={**parent,"source_id":sid,"path":impl["path"],"chapter":parent["chapter"]+" · "+PurePosixPath(impl["path"]).name}
            sources.append(code)
            catalog["chapters"][sid]={"language":"en","canonical_path":impl["path"],"order":12+len(code_records),
                "kind":"implementation","content_type":"code","parent_source_ids":[parent["source_id"]],"topics":meta["topics"],
                "applicable_versions":["unknown"],"git_blob":impl["git_blob"],"bytes":impl["bytes"]}
            code_records.append((code,{"sha":impl["git_blob"],"size":impl["bytes"]}))
    if len(code_records)!=17: raise ValueError("Expected registered 17 implementations")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda item:download(item[0]["repository"],item[0]["commit"],item[0]["path"],item[1]),code_records))
    roots=[(LC_REPO,LC_COMMIT,"langchain-official",path,title,topics,["pinned-documentation"]) for path,title,topics in LC_PAGES]
    roots += [(MCP_REPO,MCP_COMMIT,"mcp-specification",f"docs/specification/{ver}/{path}",f"MCP {ver} · {path.removesuffix('.mdx')}",["mcp","tools"] if path=="server/tools.mdx" else ["mcp"],[ver]) for ver in ("2025-11-25","2026-07-28") for path in MCP_PATHS]
    discovered={}
    queue=list(roots)
    edges=[]
    root_paths={(r[0],r[3]) for r in roots}
    while queue:
        repo,commit,book,path,title,topics,versions=queue.pop(0)
        key=(repo,path)
        if key in discovered: continue
        if path not in tree_by_repo[repo]:raise ValueError("Missing pinned page "+path)
        entry=tree_by_repo[repo][path]
        raw=download(repo,commit,path,entry)
        deps=local_mdx_dependencies(raw.decode("utf-8-sig"),path,set(tree_by_repo[repo]),repo)
        discovered[key]=(repo,commit,book,path,title,topics,versions,entry)
        for dep in deps:
            edges.append((key,(repo,dep)))
            queue.append((repo,commit,book,dep,"正文依赖 · "+PurePosixPath(dep).stem,topics,versions))
    # Parent linkage and inherited versions/topics are a closure, not first-parent guesses.
    inherited={key:{"roots":set(),"topics":set(),"versions":set()} for key in discovered}
    for root in roots:
        key=(root[0],root[3]); inherited[key]["roots"].add(source_id(*key));inherited[key]["topics"].update(root[5]);inherited[key]["versions"].update(root[6])
    changed=True
    while changed:
        changed=False
        for parent,child in edges:
            for field in ("roots","topics","versions"):
                before=len(inherited[child][field]); inherited[child][field].update(inherited[parent][field]);changed|=len(inherited[child][field])!=before
    orders={"langchain-official":0,"mcp-specification":0}
    for key,record in discovered.items():
        repo,commit,book,path,title,topics,versions,entry=record
        sid=source_id(repo,path)
        sources.append({"source_id":sid,"book":book,"chapter":title,"repository":repo,"commit":commit,"path":path})
        is_root=key in root_paths
        catalog["chapters"][sid]={"language":"en","canonical_path":path,"order":orders[book],
            "kind":"official" if is_root else "dependency","content_type":"prose" if is_root else "snippet",
            "parent_source_ids":sorted(source_id(*p) for p,c in edges if c==key),"root_source_ids":sorted(inherited[key]["roots"]),
            "dependencies":sorted(source_id(*c) for p,c in edges if p==key),"topics":sorted(inherited[key]["topics"]),
            "applicable_versions":sorted(inherited[key]["versions"]),"git_blob":entry["sha"],"bytes":entry["size"],
            "license_notice":"Full repository LICENSE and file notices retained; do not assume MIT" if repo==MCP_REPO else "MIT"}
        orders[book]+=1
    payload={"version":3,"sources":sources,"catalog":catalog}
    (PROJECT/"sources-qa-v3.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    inventory={"date":"2026-10-14","base_corpus_version":base["corpus_version"],"preserved_sources":216,"implementation_files":17,"official_roots":24,"dependency_files":len(discovered)-24,"source_files":len(sources),"edges":[{"parent":source_id(*p),"dependency":source_id(*c)} for p,c in edges],"execution":"static only","model_calls":0}
    (PROJECT/"data/qa-inventory.json").write_text(json.dumps(inventory,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in inventory.items() if k!="edges"},ensure_ascii=False),flush=True)

def import_snapshot():
    from study_rag.core import read_source_manifest,prepare_corpus,build_index,verified_corpus,validate_text
    sources,catalog=read_source_manifest(PROJECT/"sources-qa-v3.json")
    old,contents=load_corpus(BASE)
    preserved={s.source_id:(s,raw) for s,raw in contents}
    if sources[:216]!=[s for s,_ in contents]:raise ValueError("Old source declarations changed")
    def fetch(source):
        if source.source_id in preserved:return preserved[source.source_id][1]
        return (CACHE/(source.source_id+PurePosixPath(source.path).suffix)).read_bytes()
    imported=prepare_corpus(sources,TARGET,fetch,catalog=catalog)
    imported["network_requests"] = 0  # Import consumes the independently verified download cache.
    index=build_index(TARGET,TARGET/"index.sqlite3")
    manifest,chunks,mapping,new_contents=verified_corpus(TARGET,TARGET/"index.sqlite3")
    for source,raw in new_contents:
        if source.source_id in preserved and preserved[source.source_id]!=(source,raw):raise ValueError("Old bytes changed")
        text=validate_text(raw);cursor=0
        for start,end in sorted((c.start_char,c.end_char) for c in chunks if c.source_id==source.source_id):
            if text[cursor:start].strip():raise ValueError("Source not completely indexed: "+source.path)
            cursor=max(cursor,end)
        if text[cursor:].strip():raise ValueError("Source tail not indexed")
    report={"date":"2026-10-14","import":imported,"index":index,"corpus_version":manifest["corpus_version"],"source_files":len(sources),"chunks":len(chunks),"old_sources_and_bytes_unchanged":216,"position_coverage":"all nonwhitespace","model_calls":0}
    (TARGET/"coverage.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("operation",choices=("discover","import"));args=p.parse_args()
    discover() if args.operation=="discover" else import_snapshot()
