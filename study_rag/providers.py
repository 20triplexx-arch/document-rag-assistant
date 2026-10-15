"""Explicit provider routing. Never borrows another provider's credentials."""
import os
import re
import json

from .rag import DeepSeekModel, MODEL_LABELS, ProviderError

BAILIAN_MODELS = ("qwen3.8-flash", "qwen3.8-max-0902")
DEEPSEEK_MODELS = ("deepseek-flash",)
ENABLED_MODELS = ("deepseek-flash", "qwen3.8-flash")


def bailian_free_only_confirmed():
    # Operator confirmation means both the exact model's free balance and the
    # provider's stop-when-exhausted protection were checked. A key is not proof.
    return os.getenv('RAG_BAILIAN_FREE_ONLY_CONFIRMED','').strip()=='1'


class BailianModel(DeepSeekModel):
    """Independent configuration; shared bounded Chat Completions transport only."""
    provider = "bailian"

    def __init__(self, model_name="qwen3.8-flash"):
        if model_name not in BAILIAN_MODELS:
            raise ValueError("未注册的百炼型号。")
        super().__init__(model_name)

    def _provider_config(self):
        key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        workspace = os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip()
        if not key:
            raise ProviderError("BAILIAN_KEY_MISSING", attempts=0)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", workspace):
            raise ProviderError("BAILIAN_WORKSPACE_INVALID", attempts=0)
        if not bailian_free_only_confirmed():
            raise ProviderError('BAILIAN_FREE_ONLY_UNCONFIRMED',attempts=0)
        base = f"https://{workspace}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        return key, base, {"enable_thinking": False, "enable_search": False}

    def _response_format(self, messages):
        try:
            payload=json.loads(messages[-1]['content'])
        except (ValueError,TypeError,KeyError):
            return super()._response_format(messages)
        schema=payload.get('ANSWER_SCHEMA') or payload.get('review_schema')
        if not isinstance(schema,dict):return super()._response_format(messages)
        def clean(value):
            if isinstance(value,list):return [clean(v) for v in value]
            if not isinstance(value,dict):return value
            result={k:clean(v) for k,v in value.items() if k not in {'title','default','discriminator'}}
            if 'const' in result:result['enum']=[result.pop('const')]
            return result
        return {'type':'json_schema','json_schema':{'name':'study_rag_output','strict':True,'schema':clean(schema)}}


def create_model(name=None):
    from .settings import DEFAULT_CHAT_MODEL
    selected = name if name is not None else (os.getenv("RAG_DEFAULT_MODEL", "").strip()
                or os.getenv("DEEPSEEK_MODEL", "").strip() or DEFAULT_CHAT_MODEL)
    if selected in {'deepseek-v4-pro','qwen3.8-max-0902'}:
        raise ValueError('Pro 和 Max 已按用户要求停用；请选择 Flash。')
    return BailianModel(selected) if selected in BAILIAN_MODELS else DeepSeekModel(selected)


def configured_models(default):
    options = {default.model_name: default}
    for name in DEEPSEEK_MODELS:
        if name not in options: options[name] = DeepSeekModel(name)
    if bailian_free_only_confirmed() and os.getenv("DASHSCOPE_API_KEY", "").strip() and os.getenv("DASHSCOPE_WORKSPACE_ID", "").strip():
        for name in ('qwen3.8-flash',):
            if name not in options: options[name] = BailianModel(name)
    return options


def provider_name(name):
    return "bailian" if name in BAILIAN_MODELS else "deepseek" if name.startswith("deepseek-") else "custom"
