"""Verified, deterministic source views and cell locations. Never executes code."""
from functools import lru_cache
import json
import re
from types import SimpleNamespace

VERSION = 'source-view-atomic-v4.1'
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.mjs', '.cjs', '.tsx'}
CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.txt'}


@lru_cache(maxsize=4096)
def source_view(path, raw):
    from .core import CorpusError, validate_text
    if path.endswith('.ipynb'):
        if not raw or len(raw) > 8_000_000:
            raise CorpusError('Notebook 超过原始文件容量限制。')
        try:
            document = json.loads(raw.decode('utf-8-sig'))
            if document.get('nbformat') != 4 or not isinstance(document['cells'], list):
                raise ValueError('Notebook v4 cells required')
            pieces, cells, offset = [], [], 0
            language = document.get('metadata', {}).get('language_info', {}).get('name', 'python')
            for index, cell in enumerate(document['cells'], 1):
                if cell.get('cell_type') not in {'markdown', 'code'}:
                    continue
                body = cell.get('source', '')
                if isinstance(body, list):
                    if any(not isinstance(line, str) for line in body): raise ValueError('Invalid source')
                    body = ''.join(body)
                if not isinstance(body, str) or '\0' in body: raise ValueError('Invalid source')
                body = body.replace('\r\n', '\n').replace('\r', '\n')
                if not body.strip(): continue
                if pieces: pieces.append('\n\n'); offset += 2
                cells.append({'cell_index': index, 'kind': cell['cell_type'], 'language': language,
                              'start': offset, 'end': offset + len(body)})
                pieces.append(body); offset += len(body)
            return ''.join(pieces), tuple(cells)
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            raise CorpusError('Notebook 无法建立可核对的单元视图。') from None
    text = validate_text(raw)
    suffix = '.' + path.rsplit('.', 1)[-1].lower()
    kind = 'code' if suffix in CODE_EXTENSIONS else 'configuration' if suffix in CONFIG_EXTENSIONS and not path.endswith('.txt') else 'markdown'
    return text, ({'cell_index': None, 'kind': kind, 'language': 'python' if suffix == '.py' else suffix[1:],
                   'start': 0, 'end': len(text)},)


def source_text(source, raw):
    return source_view(source.path, raw)[0]


def locator(source, raw, start, end):
    text, cells = source_view(source.path, raw)
    if not source.path.endswith('.ipynb'): return None
    cell = next((c for c in cells if c['start'] <= start < end <= c['end']), None)
    if cell is None:
        from .core import CorpusError
        raise CorpusError('Notebook 引用跨单元或不属于教学源码。')
    return {'kind': 'notebook_cell', 'cell_index': cell['cell_index'],
            'start_line': text.count('\n', cell['start'], start) + 1,
            'end_line': text.count('\n', cell['start'], end - 1) + 1,
            'view_start_char': cell['start'], 'view_start_line': text.count('\n', 0, cell['start']) + 1}


def _markdown_ranges(text):
    """Whole paragraphs/list items/table rows, retaining original whitespace/offsets."""
    lines = text.splitlines(keepends=True)
    offset, start, section, fence, level_titles = 0, 0, '正文', '', []
    ranges = []
    for line in lines:
        heading = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$', line)
        marker = re.match(r'^[ \t]*(`{3,}|~{3,})(.*)', line)
        boundary = not fence and (heading or not line.strip() or re.match(r'^\s*(?:[-*+]\s|\d+[.)]\s|\|)', line))
        if boundary and offset > start:
            ranges.append((start, offset, section)); start = offset
        if heading and not fence:
            level = len(heading[1])
            while level_titles and level_titles[-1][0] >= level: level_titles.pop()
            level_titles.append((level, heading[2]))
            section = ' / '.join(title for _, title in level_titles)
        if marker:
            if not fence: fence = marker[1][0]
            elif marker[1][0] == fence and not marker[2].strip(): fence = ''
        offset += len(line)
    if offset > start: ranges.append((start, offset, section))
    return ranges


def view_chunks(source, raw, max_chars=1000):
    from .core import Chunk, digest, json_text
    from .code_index import python_chunks, markdown_code_chunks
    text, cells = source_view(source.path, raw)
    chunks = []
    def add(a, b, label, atomic=False):
        while a < b:
            end = b if atomic else min(a + max_chars, b)
            if end < b:
                cut = text.rfind('\n', a + max_chars // 2, end)
                if cut >= 0: end = cut + 1
            if text[a:end].strip():
                identity = json_text([source.source_id, digest(raw), VERSION, label, a, end])
                chunks.append(Chunk(source.source_id + '-' + digest(identity.encode())[:20], source.source_id,
                                    label, a, end, text.count('\n', 0, a) + 1,
                                    text.count('\n', 0, end - 1) + 1, text[a:end]))
            a = end
    for cell in cells:
        left, right = cell['start'], cell['end']; body = text[left:right]
        prefix = f"Notebook cell {cell['cell_index']} / " if cell['cell_index'] else ''
        if cell['kind'] in {'code', 'configuration'}:
            python = source.path.endswith('.py') or (cell['cell_index'] and cell['language'] == 'python')
            if python:
                try:
                    units = python_chunks(SimpleNamespace(source_id=source.source_id, path=source.path), body.encode(), max_chars=max_chars)
                    for unit in units: add(left + unit.start_char, left + unit.end_char, prefix + unit.section)
                    continue
                except ValueError:
                    # Notebook magics/legacy syntax remain readable; no false AST claim.
                    pass
            add(left, right, prefix + ('[config]' if cell['kind'] == 'configuration' else '[code]') + ' ' + cell['language'])
        else:
            for a, b, label in _markdown_ranges(body): add(left + a, left + b, prefix + label,atomic=True)
            # Fenced examples are a separate typed channel, not duplicated prose.
            for unit in markdown_code_chunks(SimpleNamespace(source_id=source.source_id, path=source.path), body.encode()):
                add(left + unit.start_char, left + unit.end_char, prefix + unit.section)
    return chunks
