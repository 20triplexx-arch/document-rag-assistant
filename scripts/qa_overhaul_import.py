"""Pinned seven-repository teaching inventory; content-addressed downloads, no execution."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import ast
import hashlib
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from study_rag.core import Source, load_corpus, prepare_corpus, build_index, verified_corpus, json_text
from study_rag.source_views import source_view, source_text
from qa_import import local_mdx_dependencies

OUT = ROOT / 'output/qa-overhaul-20261015-v2'
CACHE = OUT / 'source-cache'
DATA = ROOT / 'data/qa-overhaul-20261015-v2'
MANIFEST = ROOT / 'sources-qa-overhaul-v4.json'
TEXT = {'.md', '.mdx', '.txt', '.py', '.ipynb', '.js', '.ts', '.mjs', '.cjs', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
CODE = {'.py', '.ipynb', '.js', '.ts', '.mjs', '.cjs'}
CONFIG = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.txt'}
EXCLUDED = {'node_modules', 'vendor', '.git', '.github', '__pycache__', '.venv', 'venv', 'dist', 'build',
            'frontend', 'front-end', 'assets', 'images', 'screenshots', 'evaluation_results', 'evaluation_reports',
            'generated_data', 'template_output', 'test-results', 'coverage', 'site-packages'}


def blob(raw): return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
def sid(repo, path): return 'qa-' + hashlib.sha256((repo + ':' + path).encode()).hexdigest()[:20]


def read(url, limit):
    with urlopen(Request(url, headers={'User-Agent': 'study-rag-pinned-teaching-import'}), timeout=30) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit: raise ValueError('Source too large')
    return raw


def excluded(path, entry):
    p = PurePosixPath(path)
    if any(part.lower() in EXCLUDED for part in p.parts): return 'generated, third-party, UI or non-teaching directory'
    if p.suffix.lower() not in TEXT: return 'unsupported or binary format'
    if entry.get('size') == 0: return 'empty upstream placeholder; no teaching content'
    if entry.get('mode') not in {'100644', '100755'}: return 'not a regular repository file'
    if entry.get('size', 0) > (8_000_000 if p.suffix == '.ipynb' else 2_000_000): return 'exceeds documented source size limit'
    if p.name.startswith('.env') or '.min.' in p.name or p.name.endswith(('-lock.json', '.lock')): return 'secret-shaped config, lock or generated bundle'
    return None


def preferred(path, paths):
    if path.endswith('.en.md') and path[:-6] + '.zh-Hans.md' in paths: return False
    if path.endswith('.md') and not path.endswith('.zh-Hans.md') and path[:-3] + '.zh-Hans.md' in paths: return False
    if '/translations/' in path or path.startswith('translations/'):
        return '/zh-CN/' in '/' + path or '/zh-Hans/' in '/' + path
    if path.startswith('units/'):
        return path.startswith(('units/en/', 'units/zh-CN/')) and not (path.startswith('units/en/') and path.replace('units/en/', 'units/zh-CN/', 1) in paths)
    return True


def root_candidate(book, path, paths, case_roots):
    suffix = PurePosixPath(path).suffix.lower()
    if not preferred(path, paths): return False
    if book == 'awesome-agentic-ai-zh':
        return path.startswith(('stages/', 'tracks/', 'branches/', 'walkthroughs/', 'resources/', 'examples/'))
    if book == 'Hello-Agents':
        return path.startswith(('docs/', 'Extra-Chapter/', 'Additional-Chapter/', 'code/'))
    if book == 'microsoft-ai-agents':
        p = re.sub(r'^translations/(?:zh-CN|zh-Hans)/', '', path)
        if not re.match(r'^(?:0\d|1[0-8])-[^/]+/', p): return False
        if p != path: return suffix in {'.md', '.mdx'}
        return suffix in CODE | CONFIG or suffix in {'.md', '.mdx'} and 'translations/zh-CN/' + p not in paths
    if book == 'huggingface-agents':
        return path.startswith(('notebooks/', 'units/zh-CN/', 'units/en/')) and not re.search(r'quiz|discord101|get-your-cert', path, re.I)
    if book == 'awesome-llm-apps-cases':
        return any(path.startswith(root + '/') for root in case_roots)
    if book == 'langchain-official':
        if path.startswith(('src/code-samples/langchain/', 'src/code-samples/langgraph/', 'src/code-samples/deepagents/', 'src/code-samples/langsmith/')):
            return suffix in CODE | CONFIG and bool(re.search(r'tool|memor|rag|retriev|context|mcp|agent|trac|observ|middleware|plan|workflow', path, re.I))
        return (path.startswith(('src/oss/concepts/', 'src/oss/deepagents/', 'src/oss/langchain/multi-agent/'))
                or path.startswith('src/oss/langchain/') and bool(re.search(r'tool|memor|retriev|context|middleware|agent|runtime|mcp|observ', path, re.I))
                or path.startswith('src/oss/langgraph/') and bool(re.search(r'memor|persist|context|runtime|graph-api|agent|workflow', path, re.I))
                or path.startswith('src/langsmith/') and bool(re.search(r'observ|trac|feedback|thread|run-concept', path, re.I))) and suffix in {'.md', '.mdx'}
    if book == 'mcp-specification':
        return bool(re.match(r'(?:docs/specification|schema)/(?:2025-11-25|2026-07-28)/', path))
    return False


def references(path, raw, paths, repo):
    text = source_view(path, raw)[0]
    found = set()
    def resolve(target):
        target = target.split('#')[0].split('?')[0]
        if not target or re.match(r'\w+://|//|data:', target): return
        base = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
        candidates = [base, base + '.md', base + '.mdx', base + '.py', base + '.js', base + '.ts', base + '/index.ts', base + '/index.js', base + '/__init__.py']
        found.update(p for p in candidates if p in paths)
    for match in re.finditer(r'\]\(([^\s)]+)', text): resolve(match[1])
    if path.endswith('.mdx'):
        redirect=re.fullmatch(r"---\s*\n.*?\nurl:\s*['\"]([^'\"]+)['\"]\s*\n---\s*",text,re.S)
        if redirect and repo=='langchain-ai/docs':
            if redirect[1].startswith(('https://','http://')):return found
            root='src/'+redirect[1].strip('/')
            targets={p for p in [root+'.mdx',root+'/index.mdx'] if p in paths}
            if len(targets)!=1:raise ValueError('Unresolved redirect')
            found.update(targets)
        else:found.update(local_mdx_dependencies(text, path, paths, repo))
    for match in re.finditer(r'(?:from\s+|import\s*\(?\s*)[\'\"](\.[^\'\"]+)', text): resolve(match[1])
    if path.endswith('.py'):
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = (node.module or '').replace('.', '/')
                    directory = posixpath.dirname(path)
                    for _ in range(max(0, node.level - 1)): directory = posixpath.dirname(directory)
                    for root in (directory, ''):
                        for extension in ('.py', '/__init__.py'):
                            candidate = posixpath.join(root, module) + extension
                            if candidate in paths: found.add(candidate)
                elif isinstance(node, ast.Import):
                    for name in node.names:
                        module = name.name.replace('.', '/')
                        for root in (posixpath.dirname(path), ''):
                            candidate = posixpath.join(root, module) + '.py'
                            if candidate in paths: found.add(candidate)
        except (SyntaxError, ValueError): pass
    return found - {path}


def run():
    OUT.mkdir(parents=True, exist_ok=True); CACHE.mkdir(exist_ok=True)
    base, contents = load_corpus(ROOT / 'data/qa-20261014-v1')
    catalog = deepcopy(base['catalog']); catalog['version'] = 4
    sources = [Source(**d['source']) for d in base['documents']]
    existing = {(s.repository, s.path): (s, raw) for s, raw in contents}
    mirror_exclusions={(s.repository,catalog['chapters'][s.source_id]['canonical_path']) for s in sources
                       if catalog['chapters'][s.source_id]['canonical_path']!=s.path}
    books = {b['book']: b for b in catalog['books']}
    repos = {b['repository']: b for b in catalog['books']}
    trees, inventory, gaps = {}, {}, []
    def tree_for(book):
        repo, commit = book['repository'], book['commit']
        target = CACHE / (repo.replace('/', '-') + '-tree.json')
        older = ROOT / 'output/qa-source-cache' / target.name
        raw = target.read_bytes() if target.exists() else older.read_bytes() if older.exists() else read(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1', 12_000_000)
        tree = json.loads(raw)
        if tree.get('sha') != commit or tree.get('truncated'): raise ValueError('Incomplete or unpinned tree: ' + repo)
        if not target.exists(): target.write_bytes(raw)
        return repo, {e['path']: e for e in tree['tree'] if e['type'] == 'blob'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for repo, tree in pool.map(tree_for, books.values()): trees[repo] = tree
    case_roots = {str(PurePosixPath(s.path).parent) for s in sources if catalog['chapters'][s.source_id].get('kind') == 'case'}
    selected = set(existing)
    for book in books.values():
        repo = book['repository']; paths = set(trees[repo])
        for path, entry in trees[repo].items():
            reason = 'canonical language mirror; retained existing Chinese body' if (repo,path) in mirror_exclusions else excluded(path, entry)
            selected_root = not reason and root_candidate(book['book'], path, paths, case_roots)
            inventory[repo, path] = {'repository': repo, 'commit': book['commit'], 'path': path, 'git_blob': entry['sha'],
                                     'bytes': entry.get('size', 0), 'state': 'excluded',
                                     'reason': reason or 'outside selected teaching roots/language'}
            if selected_root: selected.add((repo, path))
    downloaded = {key: value[1] for key, value in existing.items()}
    edges = set()
    def download(key):
        repo, path = key; entry = trees[repo][path]
        if key in downloaded: raw = downloaded[key]
        else:
            target = CACHE / (entry['sha'] + '.blob')
            raw = target.read_bytes() if target.exists() else read(f"https://raw.githubusercontent.com/{repo}/{repos[repo]['commit']}/{path}", 8_000_000 if path.endswith('.ipynb') else 2_000_000)
            if blob(raw) != entry['sha'] or len(raw) != entry['size']: raise ValueError('Blob mismatch')
            if not target.exists(): target.write_bytes(raw)
        source_view(path, raw)
        return key, raw, references(path, raw, set(trees[repo]), repo)
    seen = set()
    while selected - seen:
        batch = sorted(selected - seen)
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = {pool.submit(download, key): key for key in batch}
            for future in as_completed(jobs):
                key = jobs[future]; seen.add(key)
                try:
                    _, raw, deps = future.result()
                    if key not in existing and re.fullmatch(rb'---\s*\n.*?\nurl:\s*[\'\"]https?://.*?\n---\s*',raw,re.S):
                        inventory[key].update(state='excluded',reason='external redirect only; no pinned teaching body')
                        continue
                    downloaded[key] = raw
                    inventory[key].update(state='included', reason='preserved source' if key in existing else 'teaching root or local reference')
                    for dep in deps:
                        target = (key[0], dep)
                        if target not in mirror_exclusions and not excluded(dep, trees[key[0]][dep]) and preferred(dep, set(trees[key[0]])):
                            selected.add(target); edges.add((key, target))
                except Exception as error:
                    inventory[key].update(state='failed', reason=type(error).__name__)
                    gaps.append(inventory[key])
                if len(seen) % 100 == 0: print('verified', len(downloaded), 'pending', len(selected - seen), flush=True)
    audit = {'version': 4, 'execution': 'static only', 'model_calls': 0,
             'entries': [inventory[k] for k in sorted(inventory)], 'gaps': gaps,
             'counts': dict(Counter(row['state'] for row in inventory.values()))}
    (OUT / 'inventory.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    if gaps: raise ValueError(f'{len(gaps)} eligible sources failed; inventory saved, no complete snapshot published')
    new_sources = []
    orders = {name: max(catalog['chapters'][s.source_id]['order'] for s in sources if s.book == name) + 1 for name in books}
    by_repo_book = {b['repository']: b['book'] for b in books.values()}
    by_key = {key: value[0] for key, value in existing.items()}
    for key in sorted(downloaded):
        if key in existing: continue
        repo, path = key; book = by_repo_book[repo]; entry = trees[repo][path]
        source = Source(sid(repo, path), book, path, repo, books[book]['commit'], path)
        by_key[key] = source; new_sources.append(source)
        suffix = PurePosixPath(path).suffix.lower()
        versions = [re.search(r'(2025-11-25|2026-07-28)', path)[0]] if book == 'mcp-specification' and re.search(r'2025-11-25|2026-07-28', path) else ['pinned-documentation'] if book == 'langchain-official' else ['unknown']
        kind = 'notebook' if suffix == '.ipynb' else 'code' if suffix in CODE else 'configuration' if suffix in CONFIG else 'prose'
        catalog['chapters'][source.source_id] = {'canonical_path': path, 'language': 'zh-CN' if '/zh-CN/' in path or '.zh-Hans.' in path or book == 'Hello-Agents' else 'en',
            'order': orders[book], 'git_blob': entry['sha'], 'bytes': entry['size'],
            'kind': 'implementation' if kind in {'code', 'configuration', 'notebook'} else 'lesson', 'content_type': kind,
            'applicable_versions': versions, 'topics': [], 'parent_source_ids': [], 'dependencies': []}
        orders[book] += 1
    # Reciprocal actual local references; retained MDX relationships stay intact.
    for parent, child in sorted(edges):
        a, b = by_key[parent].source_id, by_key[child].source_id
        if a != b:
            for owner, field, target in [(a, 'dependencies', b), (b, 'parent_source_ids', a)]:
                values = catalog['chapters'][owner].setdefault(field, [])
                if target not in values: values.append(target)
    sources += new_sources
    if MANIFEST.exists():
        frozen=json.loads(MANIFEST.read_text(encoding='utf-8'))
        for source in sources:
            previous=frozen['catalog']['chapters'].get(source.source_id,{})
            current=catalog['chapters'][source.source_id]
            for field in ('dependencies','parent_source_ids','root_source_ids'):
                if field in previous and set(previous[field])==set(current.get(field,[])):
                    current[field]=previous[field]
    payload = {'version': 4, 'sources': [s.__dict__ for s in sources], 'catalog': catalog}
    if MANIFEST.exists() and json.loads(MANIFEST.read_text(encoding='utf-8')) != payload: raise ValueError('Frozen inventory changed')
    if not MANIFEST.exists(): MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    prepare_corpus(sources, DATA, lambda s: downloaded[s.repository, s.path], catalog=catalog)
    build_index(DATA, DATA / 'index.sqlite3')
    manifest, chunks, mapping, verified = verified_corpus(DATA, DATA / 'index.sqlite3')
    counts = Counter(c.source_id for c in chunks)
    cells = sum(len(source_view(s.path, raw)[1]) for s, raw in verified if s.path.endswith('.ipynb'))
    for source, raw in verified:
        text = source_text(source, raw); cursor = 0
        for a, b in sorted((c.start_char, c.end_char) for c in chunks if c.source_id == source.source_id):
            if text[cursor:a].strip(): raise ValueError('Unindexed source range: ' + source.path)
            cursor = max(cursor, b)
        if text[cursor:].strip(): raise ValueError('Unindexed source tail: ' + source.path)
        if (source.repository, source.path) in existing and existing[source.repository, source.path][1] != raw: raise ValueError('Preserved raw changed')
    coverage = {'corpus_version': manifest['corpus_version'], 'raw_files': len(mapping), 'preserved_raw_files': len(existing),
                'chunks': len(chunks), 'notebook_cells': cells, 'gaps': [], 'model_calls': 0,
                'files_by_book': dict(Counter(s.book for s in sources)), 'source_types': dict(Counter(catalog['chapters'][s.source_id].get('content_type','prose') for s in sources))}
    (DATA / 'coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(coverage, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    run()
