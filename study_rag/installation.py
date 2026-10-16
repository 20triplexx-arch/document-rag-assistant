"""Local installation and read-only diagnostics. Never constructs a model or Store."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import struct
import sys
import tempfile
from uuid import uuid4

from .core import (CorpusError, build_index, fetch_source, load_corpus,
                   prepare_corpus, read_source_manifest, verified_corpus)
from .settings import DEFAULT_CHAT_MODEL, DEFAULT_DATA, DEFAULT_SOURCES, PROJECT


class InstallationError(ValueError):
    """Safe, public-file-only diagnostic; never contains provider responses."""


@contextmanager
def staging_directory(parent):
    # Windows honors mkdir(0700) with a private ACL. TemporaryDirectory uses
    # that mode; moving its children would retain that ACL after publication.
    # Public textbook staging must inherit the same parent ACL as the final tree.
    parent = Path(parent).resolve()
    directory = parent / ('.rag-install-' + uuid4().hex)
    directory.mkdir()
    try:
        yield directory
    finally:
        if directory.exists():
            if directory.resolve().parent != parent or directory.is_symlink():
                raise InstallationError('临时目录身份不同，未清理。')
            shutil.rmtree(directory)


def install_corpus(sources_path, data_dir, cache_dir, *, fetch=fetch_source, progress=print):
    sources_path, data_dir, cache_dir = map(Path, (sources_path, data_dir, cache_dir))
    sources, catalog = read_source_manifest(sources_path)
    if catalog is None:
        raise InstallationError('安装需要带 Git blob 和字节数的固定来源清单。')
    if data_dir.exists():
        if not (data_dir / 'corpus.json').is_file():
            raise InstallationError(f'已有未发布目录，未覆盖：{data_dir}')
        manifest, _ = load_corpus(data_dir)
        if ([r['source'] for r in manifest['documents']] != [asdict(s) for s in sources]
                or manifest.get('catalog') != catalog):
            raise InstallationError(f'已有语料与来源清单不同，未覆盖：{data_dir}')
        index = data_dir / 'index.sqlite3'
        if not index.exists():
            # Publish only a complete, verified index; never repair over corruption.
            with staging_directory(data_dir.parent) as temporary:
                staged = temporary / 'index.sqlite3'
                build_index(data_dir, staged)
                verified_corpus(data_dir, staged)
                if index.exists():
                    raise InstallationError('另一进程已建立索引，请重新核对。')
                staged.rename(index)
        manifest, chunks, _, _ = verified_corpus(data_dir, index)
        progress(f'已复用并核对 {len(sources)} 个原始文件及索引。')
        return {'status': 'CORPUS_REUSED', 'documents': len(sources), 'chunks': len(chunks),
                'corpus_version': manifest['corpus_version'], 'network_requests': 0, 'model_calls': 0}

    cache_dir.mkdir(parents=True, exist_ok=True)
    downloads = hits = 0

    def cached(source):
        nonlocal downloads, hits
        expected = catalog['chapters'][source.source_id]
        path = cache_dir / (expected['git_blob'] + '.raw')
        position = downloads + hits + 1
        try:
            raw = path.read_bytes() if path.exists() else fetch(source)
            blob = hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()
            if blob != expected['git_blob'] or len(raw) != expected['bytes']:
                raise InstallationError(f'原文或下载缓存核对失败：{source.source_id}；缓存 {path}')
            if path.exists():
                hits += 1
                origin = '缓存已核对'
            else:
                with tempfile.NamedTemporaryFile(dir=cache_dir, prefix='.download-', delete=False) as stream:
                    partial = Path(stream.name)
                    stream.write(raw)
                try:
                    # A competing writer cannot silently replace a checked cache.
                    if path.exists():
                        if path.read_bytes() != raw:
                            raise InstallationError(f'并发缓存内容不同：{source.source_id}')
                    else:
                        partial.rename(path)
                finally:
                    partial.unlink(missing_ok=True)
                downloads += 1
                origin = '已下载并核对'
            progress(f'[{position}/{len(sources)}] {source.source_id} {origin}')
            return raw
        except InstallationError:
            raise
        except Exception as error:
            raise InstallationError(f'下载失败：{source.source_id} ({source.path})；'
                                    f'{type(error).__name__}，未自动重试；重新运行可复用已核对缓存。') from None

    data_dir.parent.mkdir(parents=True, exist_ok=True)
    with staging_directory(data_dir.parent) as temporary:
        staged = temporary / 'snapshot'
        prepare_corpus(sources, staged, cached, catalog=catalog)
        build_index(staged, staged / 'index.sqlite3')
        manifest, chunks, _, _ = verified_corpus(staged, staged / 'index.sqlite3')
        if data_dir.exists():
            raise InstallationError(f'目标目录已出现，未覆盖：{data_dir}')
        staged.rename(data_dir)
    return {'status': 'CORPUS_INSTALLED', 'documents': len(sources), 'chunks': len(chunks),
            'corpus_version': manifest['corpus_version'], 'network_requests': downloads,
            'cache_hits': hits, 'model_calls': 0}


def diagnose(*, project=PROJECT, data_dir=DEFAULT_DATA, skip_corpus=False):
    project, data_dir = Path(project), Path(data_dir)
    checks = []
    compatible = (sys.platform == 'win32' and sys.version_info[:2] == (3, 12)
                  and struct.calcsize('P') == 8 and platform.machine().upper() in {'AMD64', 'X86_64'})
    checks.append({'check': 'runtime', 'ok': compatible, 'python': platform.python_version(),
                   'required': 'Windows x64 / Python 3.12 x64'})
    mismatches = []
    for line in (project / 'requirements.lock').read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, expected = line.strip().split('==', 1)
        try:
            actual = metadata.version(name)
        except metadata.PackageNotFoundError:
            actual = None
        if actual != expected:
            mismatches.append({'package': name, 'expected': expected, 'installed': actual})
    checks.append({'check': 'locked_dependencies', 'ok': not mismatches, 'mismatches': mismatches})
    if not skip_corpus:
        try:
            manifest, chunks, sources, _ = verified_corpus(data_dir, data_dir / 'index.sqlite3')
            declared, catalog = read_source_manifest(project / 'sources-cases.json')
            if ([r['source'] for r in manifest['documents']] != [asdict(s) for s in declared]
                    or manifest.get('catalog') != catalog):
                raise InstallationError('默认语料与固定来源清单不同。')
            checks.append({'check': 'default_corpus', 'ok': True, 'documents': len(sources),
                           'chunks': len(chunks), 'corpus_version': manifest['corpus_version']})
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            checks.append({'check': 'default_corpus', 'ok': False, 'error_type': type(error).__name__,
                           'action': ('检查当前账号对教材目录的读取权限；不会自动修改权限。' if isinstance(error, PermissionError)
                                      else '缺失时运行 .\\setup.ps1；已有损坏内容不会被自动覆盖。')})
    selected = (os.getenv('RAG_DEFAULT_MODEL', '').strip() or os.getenv('DEEPSEEK_MODEL', '').strip()
                or DEFAULT_CHAT_MODEL)
    enabled = selected in {'deepseek-flash', 'qwen3.8-flash'}
    configured = bool(os.getenv('DEEPSEEK_API_KEY', '').strip()) if selected == 'deepseek-flash' else bool(
        os.getenv('DASHSCOPE_API_KEY', '').strip() and os.getenv('DASHSCOPE_WORKSPACE_ID', '').strip()
        and os.getenv('RAG_BAILIAN_FREE_ONLY_CONFIRMED') == '1')
    checks.append({'check': 'model_configuration', 'ok': enabled,
                   'generation_configured': configured if enabled else False,
                   'note': '仅检查配置存在，不请求供应商；未配置密钥可使用只查原文。' if enabled
                   else '所选型号不允许；清除型号覆盖或设置为 deepseek-flash。'})
    ok = all(row['ok'] for row in checks)
    return {'status': ('ENVIRONMENT_READY' if skip_corpus else 'READY') if ok else 'NOT_READY',
            'ready': ok and not skip_corpus, 'environment_ready': ok, 'corpus_checked': not skip_corpus,
            'checks': checks, 'model_calls': 0, 'network_requests': 0}


def doctor_cli(argv):
    parser = argparse.ArgumentParser(description='离线安装诊断；不创建账号、不调用模型。')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--output-dir', type=Path)  # Existing global CLI option; no report is written.
    sub = parser.add_subparsers(dest='operation', required=True).add_parser('doctor')
    sub.add_argument('--data-dir', type=Path, default=argparse.SUPPRESS)
    sub.add_argument('--skip-corpus', action='store_true')
    sub.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    result = diagnose(data_dir=args.data_dir, skip_corpus=args.skip_corpus)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['environment_ready'] else 1


def main():
    try:
        result = install_corpus(DEFAULT_SOURCES, DEFAULT_DATA, PROJECT / 'output/install-cache')
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        # Corpus exceptions contain only public source metadata; do not expose a traceback.
        print(f'安装未完成：{error}', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
