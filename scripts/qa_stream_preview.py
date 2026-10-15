"""Replay already-recorded public answers over streaming HTTP; zero model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from study_rag.rag import ProviderError
from study_rag.store import Store
from study_rag.web import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/qa-speed-20261015-v1"


class ReplayModel:
    model_name = "deepseek-flash"

    def __init__(self, samples):
        self.samples = samples

    def generate_stream(self, messages, callback):
        question = json.loads(messages[1]["content"])["QUESTION"]
        answer = self.samples.get(question)
        if answer is None:
            raise ProviderError("OFFLINE_PREVIEW_ONLY", attempts=0)
        raw = json.dumps(deepcopy(answer), ensure_ascii=False)
        for start in range(0, len(raw), 25):
            callback(raw[start:start+25]); time.sleep(.008)
        return raw, {"model":self.model_name,"attempts":0}

    def generate(self, messages):
        return self.generate_stream(messages, lambda _:None)


def main():
    samples = {}
    for phase in ("dev", "acceptance"):
        for path in sorted(OUT.glob(phase+"-*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["result"].get("answer"):
                samples[record["scenario"]["question"]] = record["result"]["answer"]
    with tempfile.TemporaryDirectory(prefix="qa-stream-preview-") as temp:
        store = Store(Path(temp)/"preview.sqlite3")
        store.create_admin("stream-preview","stream-preview-pass")
        app = create_app(data_dir=ROOT/"data/qa-20261014-v1",store=store,model=ReplayModel(samples),
                         session_cookie_name="stream_preview_session")
        print("Offline public replay http://127.0.0.1:8870/ ; stream-preview / stream-preview-pass",flush=True)
        print(json.dumps(list(samples),ensure_ascii=True),flush=True)
        uvicorn.run(app,host="127.0.0.1",port=8870,log_level="error")


if __name__=="__main__":main()
