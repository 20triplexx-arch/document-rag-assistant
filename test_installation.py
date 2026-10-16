"""Synthetic installation and diagnosis tests; no downloads or live models."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from study_rag.core import verified_corpus, CorpusError
from study_rag.installation import install_corpus, diagnose, InstallationError
from test_overhaul import fixture


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='安装 空格-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source, self.raw, self.catalog = fixture()
        self.manifest = self.root / 'sources-cases.json'
        self.write_manifest([self.source], self.catalog)
        self.data = self.root / 'data' / 'default'
        self.cache = self.root / 'output' / 'install-cache'

    def write_manifest(self, sources, catalog):
        self.manifest.write_text(json.dumps({'version':4,'sources':[asdict(s) for s in sources],
                                            'catalog':catalog}),encoding='utf-8')

    def install(self, fetch=None):
        return install_corpus(self.manifest,self.data,self.cache,
                              fetch=fetch or (lambda _:self.raw),progress=lambda _:None)

    def test_first_install_and_verified_reuse_preserve_all_bytes(self):
        result = self.install()
        self.assertEqual((result['network_requests'],result['model_calls']),(1,0))
        before={p.name:sha(p) for p in self.data.iterdir() if p.is_file()}
        with patch('study_rag.installation.build_index',side_effect=AssertionError('No rebuild')):
            result=self.install(lambda _:self.fail('No second download'))
        self.assertEqual(result['network_requests'],0)
        self.assertEqual(before,{p.name:sha(p) for p in self.data.iterdir() if p.is_file()})
        verified_corpus(self.data,self.data/'index.sqlite3')

    def test_interruption_retains_checked_cache_and_resume_downloads_only_missing_file(self):
        other=replace(self.source,source_id='second-source',path='second.ipynb');raw2=self.raw+b' '
        catalog=deepcopy(self.catalog)
        catalog['chapters'][other.source_id]={**catalog['chapters'][self.source.source_id],'order':1,'canonical_path':other.path,
            'bytes':len(raw2),'git_blob':hashlib.sha1(f'blob {len(raw2)}\0'.encode()+raw2).hexdigest()}
        self.write_manifest([self.source,other],catalog)
        def interrupted(source):
            if source.source_id==other.source_id:raise TimeoutError('not logged')
            return self.raw
        with self.assertRaisesRegex(InstallationError,'second-source'):
            self.install(interrupted)
        self.assertFalse(self.data.exists())
        self.assertEqual(len(list(self.cache.glob('*.raw'))),1)
        requests=[]
        def resumed(source):requests.append(source.source_id);return raw2
        result=self.install(resumed)
        self.assertEqual(requests,[other.source_id])
        self.assertEqual(result['cache_hits'],1)

    def test_invalid_download_and_corrupt_cache_never_publish(self):
        with self.assertRaisesRegex(InstallationError,'核对失败'):
            self.install(lambda _:b'wrong')
        self.assertFalse(self.data.exists())
        cache=self.cache/(self.catalog['chapters'][self.source.source_id]['git_blob']+'.raw')
        cache.write_bytes(b'tampered')
        with self.assertRaises(InstallationError):self.install(lambda _:self.fail('Do not bypass cache'))
        self.assertEqual(cache.read_bytes(),b'tampered')

    def test_missing_index_is_rebuilt_but_corrupt_index_is_preserved(self):
        self.install();index=self.data/'index.sqlite3';index.unlink()
        self.install(lambda _:self.fail('No download'))
        verified_corpus(self.data,index)
        index.write_bytes(b'corrupt index')
        with self.assertRaises((CorpusError,sqlite3.Error)):self.install()
        self.assertEqual(index.read_bytes(),b'corrupt index')

    def test_partial_directory_and_corrupt_raw_are_not_overwritten(self):
        self.data.mkdir(parents=True);marker=self.data/'keep.txt';marker.write_text('keep')
        with self.assertRaises(InstallationError):self.install()
        self.assertEqual(marker.read_text(),'keep')
        marker.unlink();self.data.rmdir();self.install()
        raw_path=self.data/(self.source.source_id+'.md');raw_path.write_bytes(b'changed')
        with self.assertRaises(CorpusError):self.install()
        self.assertEqual(raw_path.read_bytes(),b'changed')

    def test_different_manifest_is_rejected_without_modifying_existing_snapshot(self):
        self.install();before=sha(self.data/'corpus.json')
        self.catalog['books'][0]['display_name']='different'
        self.write_manifest([self.source],self.catalog)
        with self.assertRaises(InstallationError):self.install()
        self.assertEqual(sha(self.data/'corpus.json'),before)

    def test_publication_failure_never_reports_success(self):
        with patch('pathlib.Path.rename',side_effect=PermissionError('locked')):
            with self.assertRaises((PermissionError,InstallationError)):self.install()
        self.assertFalse(self.data.exists())

    def test_doctor_is_read_only_and_missing_keys_are_not_fatal(self):
        self.install();(self.root/'requirements.lock').write_text('',encoding='utf-8')
        with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'','RAG_DEFAULT_MODEL':'','DEEPSEEK_MODEL':''}), \
             patch('study_rag.providers.create_model',side_effect=AssertionError('No provider')), \
             patch('study_rag.store.Store',side_effect=AssertionError('No account DB')):
            before={str(p.relative_to(self.root)):sha(p) for p in self.root.rglob('*') if p.is_file()}
            result=diagnose(project=self.root,data_dir=self.data)
            self.assertTrue(result['ready'])
            self.assertFalse(result['checks'][-1]['generation_configured'])
            self.assertEqual(before,{str(p.relative_to(self.root)):sha(p) for p in self.root.rglob('*') if p.is_file()})
        with patch.dict('os.environ',{'RAG_DEFAULT_MODEL':'deepseek-v4-pro'}):
            self.assertFalse(diagnose(project=self.root,data_dir=self.data)['ready'])

    def test_doctor_detects_wrong_runtime_missing_dependency_and_missing_corpus(self):
        (self.root/'requirements.lock').write_text('no-such-install-test-package==1.0\n')
        with patch('study_rag.installation.platform.machine',return_value='ARM64'):
            result=diagnose(project=self.root,data_dir=self.data)
        self.assertEqual([c['ok'] for c in result['checks'][:3]],[False,False,False])
        result=diagnose(project=self.root,data_dir=self.data,skip_corpus=True)
        self.assertFalse(result['ready'])
        self.assertFalse(result['corpus_checked'])

    def test_doctor_cli_without_site_packages_returns_safe_diagnostics(self):
        root=Path(__file__).resolve().parent
        result=subprocess.run([sys.executable,'-S',str(root/'starter.py'),'doctor','--skip-corpus','--json'],
                              capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['status'],'NOT_READY')
        self.assertNotIn('Traceback',result.stderr)


if __name__=='__main__':unittest.main()
