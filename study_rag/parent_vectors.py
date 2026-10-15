"""Pinned local E5 over explicit parent descriptors; query tails are retained."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from .adapters import E5_MODEL,E5_REVISION
from .qa_vectors import encoder

VERSION='parent-descriptor-e5-v1'
CACHE=Path(__file__).resolve().parents[1]/'output/vector-cache'
ROW_BANK=Path(__file__).resolve().parents[1]/'output/qa-overhaul-20261015-v2/parent-row-bank'


@lru_cache(maxsize=2)
def parent_index(corpus_version,rows):
    import numpy as np
    from filelock import FileLock
    encoded=json.dumps(rows,ensure_ascii=False,separators=(',',':'))
    contract={'corpus':corpus_version,'version':VERSION,'model':E5_MODEL,'revision':E5_REVISION,
              'descriptor_sha256':hashlib.sha256(encoded.encode()).hexdigest()}
    key=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    CACHE.mkdir(exist_ok=True,parents=True);matrix_path=CACHE/(key+'.parents.npy');meta_path=CACHE/(key+'.parents.json')
    with FileLock(str(meta_path)+'.lock',timeout=600):
        if matrix_path.exists() and meta_path.exists():
            meta=json.loads(meta_path.read_text(encoding='utf-8'));matrix=np.load(matrix_path,allow_pickle=False)
            if meta['contract']!=contract or meta['sha256']!=hashlib.sha256(matrix_path.read_bytes()).hexdigest():raise ValueError('Parent E5 integrity mismatch')
        else:
            model=encoder()
            known={};old=None
            if ROW_BANK.with_suffix('.json').is_file() and ROW_BANK.with_suffix('.npy').is_file():
                bank=json.loads(ROW_BANK.with_suffix('.json').read_text(encoding='utf-8'))
                encoded=ROW_BANK.with_suffix('.npy').read_bytes()
                row_hash=hashlib.sha256(json.dumps(bank['rows'],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
                if bank['model']!=E5_MODEL or bank['revision']!=E5_REVISION or hashlib.sha256(encoded).hexdigest()!=bank['sha256'] or row_hash!=bank['descriptor_sha256']:
                    raise ValueError('Reusable parent embeddings failed integrity')
                import io
                old=np.load(io.BytesIO(encoded),allow_pickle=False)
                if old.shape!=(len(bank['rows']),384) or not np.isfinite(old).all():raise ValueError('Reusable parent embedding shape')
                known={row:i for i,row in enumerate(bank['rows'])}
            matrix=np.empty((len(rows),384),dtype='float32');missing=[]
            for i,row in enumerate(rows):
                if row in known:matrix[i]=old[known[row]]
                else:missing.append(i)
            if missing:
                vectors=model.encode(['passage: '+rows[i] for i in missing],batch_size=48,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False).astype('float32')
                matrix[missing]=vectors
            print('LOCAL_E5_PARENT_CACHE',json.dumps({'parents':len(rows),'reused':len(rows)-len(missing),'encoded':len(missing)}),flush=True)
            if matrix.shape!=(len(rows),384) or not np.isfinite(matrix).all():raise ValueError('Invalid parent embeddings')
            temp=matrix_path.with_suffix('.tmp')
            with temp.open('wb') as stream:np.save(stream,matrix,allow_pickle=False)
            temp.replace(matrix_path)
            meta={'contract':contract,'sha256':hashlib.sha256(matrix_path.read_bytes()).hexdigest()}
            temp=meta_path.with_suffix('.tmp');temp.write_text(json.dumps(meta),encoding='utf-8');temp.replace(meta_path)
        if matrix.shape!=(len(rows),384) or not np.isfinite(matrix).all():raise ValueError('Invalid parent embedding shape')
        matrix.setflags(write=False)
    return matrix


@lru_cache(maxsize=128)
def query_vector(question, max_queries=None):
    model=encoder();ids=model.tokenizer(question,add_special_tokens=False)['input_ids']
    windows=['query: '+model.tokenizer.decode(ids[i:i+480],skip_special_tokens=True) for i in range(0,len(ids),432)]
    if max_queries and len(windows)>max_queries:windows=[windows[0],windows[-1]][:max_queries]
    return model.encode(windows,normalize_embeddings=True,convert_to_numpy=True,show_progress_bar=False)


def semantic_parent_ranks(corpus_version,rows,allowed,question, max_queries=None):
    matrix=parent_index(corpus_version,rows);vectors=query_vector(question,max_queries)
    if not allowed:return []
    import numpy as np
    ids=np.array(sorted(allowed),dtype='int32')
    scores=(matrix[ids]@vectors.T).max(axis=1)
    order=np.argsort(-scores,kind='stable')[:60]
    return [(int(ids[index]),float(scores[index])) for index in order]
