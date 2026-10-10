"""默认语料版本独立于账号库；旧快照不覆盖，切换需完整验证。"""
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
# 此路径在完整导入和验证通过后由维护者显式切换。
DEFAULT_DATA = PROJECT / "data" / "fulltext-20261009-v2"
DEFAULT_SOURCES = PROJECT / "sources-full.json"
