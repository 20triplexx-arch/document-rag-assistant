"""Pinned local E5 over typed body windows. Query tails are never discarded."""
from functools import lru_cache
import hashlib,json
from pathlib import Path
from .adapters import E5_MODEL,E5_REVISION
from .core import index_contract

VECTOR_VERSION="qa-e5-typed-480-48-v1"
CACHE=Path(__file__).resolve().parents[1]/"output/vector-cache"

@lru_cache(maxsize=1)
def encoder():
    import torch
    torch.set_num_threads(min(4,torch.get_num_threads()))
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(E5_MODEL,revision=E5_REVISION,device="cpu",cache_folder=str(CACHE/"models"),
        local_files_only=True,trust_remote_code=False)

@lru_cache(maxsize=2)
def typed_index(contract_json,entry_json):
    import numpy as np
    from filelock import FileLock
    contract=json.loads(contract_json);entries=json.loads(entry_json)
    key=hashlib.sha256(contract_json.encode()).hexdigest();CACHE.mkdir(exist_ok=True,parents=True)
    meta_path=CACHE/(key+".qa.json");matrix_path=CACHE/(key+".qa.npy")
    with FileLock(str(CACHE/(key+".qa.lock")),timeout=600):
        if meta_path.exists() and matrix_path.exists():
            meta=json.loads(meta_path.read_text(encoding="utf-8"));matrix=np.load(matrix_path,allow_pickle=False)
            if meta["contract"]!=contract or meta["sha256"]!=hashlib.sha256(matrix_path.read_bytes()).hexdigest():raise ValueError("QA E5 cache contract/hash mismatch")
            windows=meta["windows"]
            mapping={e["chunk_id"]:e for e in entries}
            if matrix.shape!=(len(windows),384) or not np.isfinite(matrix).all():raise ValueError("QA E5 invalid matrix")
            for w in windows:
                e=mapping.get(w["chunk_id"])
                if not e or not 0<=w["start"]<w["end"]<=len(e["body"]):raise ValueError("QA E5 invalid window")
            return matrix,windows,True
        model=encoder();windows=[];inputs=[]
        for e in entries:
            offsets=model.tokenizer(e["body"],add_special_tokens=False,return_offsets_mapping=True)["offset_mapping"]
            for i in range(0,len(offsets),432):
                part=offsets[i:i+480]
                if not part:continue
                start,end=part[0][0],part[-1][1]
                if start>=end:continue
                windows.append({"chunk_id":e["chunk_id"],"start":start,"end":end})
                inputs.append("passage: "+e["body"][start:end])
                if i+480>=len(offsets):break
        matrix=model.encode(inputs,batch_size=16,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=True).astype("float32")
        if matrix.shape!=(len(windows),384) or not np.isfinite(matrix).all():raise ValueError("QA E5 invalid embeddings")
        temp=matrix_path.with_suffix(".tmp")
        with temp.open("wb") as f:np.save(f,matrix,allow_pickle=False)
        temp.replace(matrix_path)
        meta={"contract":contract,"windows":windows,"sha256":hashlib.sha256(matrix_path.read_bytes()).hexdigest()}
        temp=meta_path.with_suffix(".tmp");temp.write_text(json.dumps(meta),encoding="utf-8");temp.replace(meta_path)
        return matrix,windows,False

def dense_ranks(data_dir,manifest,entries,question):
    rows=[{"chunk_id":e["chunk"].chunk_id,"body":e["body"],"content_type":e["content_type"]} for e in entries]
    encoded=json.dumps(rows,ensure_ascii=False,separators=(",",":"))
    contract={"corpus":manifest["corpus_version"],"index":index_contract(manifest),"model":E5_MODEL,"revision":E5_REVISION,
        "version":VECTOR_VERSION,"typed_body_sha256":hashlib.sha256(encoded.encode()).hexdigest()}
    matrix,windows,hit=typed_index(json.dumps(contract,sort_keys=True),encoded)
    model=encoder();tokens=model.tokenizer(question,add_special_tokens=False)["input_ids"]
    queries=["query: "+model.tokenizer.decode(tokens[i:i+480],skip_special_tokens=True) for i in range(0,len(tokens),432)]
    vectors=model.encode(queries,normalize_embeddings=True,convert_to_numpy=True)
    scores=(matrix@vectors.T).max(axis=1);best={}
    for w,score in zip(windows,scores):best[w["chunk_id"]]=max(best.get(w["chunk_id"],-1),float(score))
    return sorted(best,key=lambda cid:(-best[cid],cid)),{"model":E5_MODEL,"revision":E5_REVISION,"windows":len(windows),"query_windows":len(queries),"cache_hit":hit}
