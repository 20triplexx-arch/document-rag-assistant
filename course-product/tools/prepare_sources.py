"""Collect only permissively licensed, pinned public sources for course review."""
from pathlib import Path
import hashlib
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
manifest = json.loads((PROJECT / 'sources-cases.json').read_text(encoding='utf-8'))
allowed = {'awesome-agentic-ai-zh', 'microsoft-ai-agents', 'huggingface-agents', 'awesome-llm-apps-cases'}
out = ROOT / 'research' / 'upstream'
out.mkdir(parents=True, exist_ok=True)
jobs = []
for source in manifest['sources']:
    if source['book'] == 'awesome-llm-apps-cases':
        for item in manifest['catalog']['chapters'][source['source_id']]['implementation_files']:
            jobs.append((source, item['path'], item['git_blob']))
        parent = str(Path(source['path']).parent).replace('\\', '/')
        jobs.append((source, parent + '/requirements.txt', None))
        if source['source_id'] == 'llm-case-4c44994e272b2621':
            jobs.append((source, parent + '/mcp_agent.config.yaml', None))
            jobs.append((source, parent + '/mcp_agent.config.yaml.example', None))
        if source['source_id'] == 'llm-case-0f13208459a60aa8':
            for name in ['backend/main.py', 'backend/config/llm.py', 'backend/pyproject.toml',
                         'backend/.env.example', 'backend/api/app.py', 'client/package.json', 'client/README.md']:
                jobs.append((source, parent + '/' + name, None))

def fetch(job):
    source, path, expected = job
    target = out / path
    url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{path}"
    if target.exists():
        raw = target.read_bytes()
    else:
        request = urllib.request.Request(url, headers={'User-Agent': 'CourseSourceReview/1.0'})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
        except Exception as exc:
            if expected is not None:
                raise RuntimeError(f'Cannot verify implementation {path}: {type(exc).__name__}') from exc
            return {'path': path, 'status': 'requirements_not_available', 'url': url}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if expected and blob != expected:
        raise RuntimeError(f'Blob mismatch: {path}')
    return {'path': path, 'git_blob': blob, 'bytes': len(raw), 'url': url, 'status': 'downloaded_and_checked'}

with ThreadPoolExecutor(max_workers=4) as pool:
    records = list(pool.map(fetch, jobs))
(ROOT / 'research' / 'source-review.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'files_checked': sum(r['status'] == 'downloaded_and_checked' for r in records),
                  'implementations_checked': sum(bool(j[2]) for j in jobs),
                  'missing_requirements': [r['path'] for r in records if r['status'] != 'downloaded_and_checked']}, ensure_ascii=False))
