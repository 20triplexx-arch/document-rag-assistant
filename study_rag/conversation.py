"""有界的本讨论上下文；历史回答用于理解追问，不作为事实证据。"""
from __future__ import annotations

import re

from .core import query_terms
from .limits import MAX_QUESTION_CHARS

CONTEXT_VERSION = "server-object-anchors-v3"
MAX_CONTEXT_TURNS = 4
MAX_CONTEXT_CHARS = 6000
STYLES = {
    "auto": "自动篇幅：按当前问题回答，定义用短段落，比较用几项差异，操作用必要步骤。清楚就停止。",
    "deep": "深入讲解：展开当前问题必要的因果关系和具体例子；不增加无关章节，不复述结论。",
    "practice": "实战步骤：直接给出完成目标所需的操作和关键检查，必要时交代前提与失败恢复。"
                "仅使用教材描述的步骤；没有实现代码依据时说明缺口，不编造可运行代码。",
    "compare": "方案对比：先指出决定选择的区别，只比较与当前问题有关的方面，给出有依据的选择理由。"
               "双方分别引用本轮证据；只有一方有依据时返回部分回答，明确另一方缺少什么。",
}
_REFERENCE = re.compile(r"(?:这里|该函数|^(?:请)?继续|(?:这个|这种)(?:怎么|如何|为什么|有什么|有何|能|可以|具体|步骤|例子|方案|机制)|"
                        r"这些(?:步骤|例子|方案|方法|区别|工具)|它|上面|上述|刚才|前面|之前|"
                        r"\b(?:it|this|that|above|continue)\b)", re.I)
_BARE_FOLLOWUP = re.compile(r"^(?:请)?(?:继续(?:详细|具体)?(?:讲解|解释|讲|说)?(?:一下)?|"
                           r"再(?:详细|具体)(?:一点|点|一些|些)?(?:讲解|解释|讲|说)?(?:一下)?|"
                           r"(?:这个|它)(?:具体)?(?:怎么|如何)(?:做|实现|工作)?|展开(?:讲解|讲|一下)?|"
                           r"(?:举|给)(?:个|一个)?(?:具体)?例子|continue|tell me more|how does it work)[？?。.!！\s]*$", re.I)
_RESET = re.compile(r"换个话题|换到|换成|新话题|另一个问题|不谈|不讨论|\bnew topic\b", re.I)


def prepare_context(question: str, recent: list[dict], book: str | None,
                    enabled: bool = True) -> dict:
    """recent 必须由服务端按用户及讨论所有权读取，不能接受客户端历史。"""
    eligible = [turn for turn in recent if enabled
                and turn["result"].get("status") in {"CITED_DRAFT", "RETRIEVAL_ONLY"}
                and (book is None or turn["result"].get("book_filter") == book)]
    refers_back = bool(_REFERENCE.search(question) or _BARE_FOLLOWUP.fullmatch(question.strip())) and not _RESET.search(question)
    if refers_back and eligible:
        from .question_plan import TOPIC_PATTERNS
        current={t for t,p in TOPIC_PATTERNS.items() if re.search(p,question,re.I)}
        previous={t for t,p in TOPIC_PATTERNS.items() if re.search(p,eligible[-1]["question"],re.I)}
        named_subject=bool(re.match(r"\s*(?:this|that|这个|这种)\s*(?:MCP|RAG|Memory|记忆|工具调用|多.?Agent)\b",question,re.I))
        if named_subject or (current and previous and not current&previous and not re.search(r"相比|对比|比较|区别|和.*相比",question)):
            refers_back=False
    context, remaining = [], MAX_CONTEXT_CHARS
    # 独立问题和显式换话题不发送旧摘要，避免旧主题污染本轮解释与检索。
    contextual = eligible if refers_back else []
    for turn in reversed(contextual[-MAX_CONTEXT_TURNS:]):
        previous_question = turn["question"][:min(1000, remaining)]
        remaining -= len(previous_question)
        from .answer_schema import answer_units
        summary = "\n".join(unit["text"] for unit in answer_units(turn["result"].get("answer") or {}))[:min(600, remaining)]
        remaining -= len(summary)
        if previous_question:
            context.append({"question": previous_question, "unverified_answer_summary": summary})
        if remaining == 0:
            break
    context.reverse()
    retrieval_question = question
    topic_question = question
    inherited = False; anchors=[]
    if contextual:
        previous = eligible[-1]
        topic = previous["result"].get("conversation_topic", previous["question"])
        anchors=previous['result'].get('object_anchors',[])[:8]
        if not anchors:
            from .provenance import named_symbols
            symbols=named_symbols(previous['question'])
            for item in previous['result'].get('evidence',[]):
                for row in item.get('provenance',{}).get('python',{}).get('local_definitions',[]):
                    if row['name'] in symbols or row['qualified_name'] in symbols:
                        anchors.append({'source_id':item['source_id'],'path':item['path'],'symbol':row['qualified_name'],
                            'cell_index':row.get('cell_index'),'scope_id':row.get('scope_id','file')})
        topic_question = topic
        prefix = "\n此前讨论主题："
        budget = MAX_QUESTION_CHARS - len(question) - len(prefix)
        if budget > 0:
            retrieval_question += prefix + topic[:min(1000, budget)]
            inherited = True
            if anchors:
                suffix='\n服务端对象定位：'+'; '.join(a['path']+' '+a['symbol'] for a in anchors)
                if len(retrieval_question)+len(suffix)<=MAX_QUESTION_CHARS:retrieval_question+=suffix
    return {"turns": context, "retrieval_question": retrieval_question, "topic_question": topic_question,
            "inherited_topic": inherited,
            "needs_topic": not eligible and bool(_BARE_FOLLOWUP.fullmatch(question.strip()))
                           and not query_terms(question)[1],
            "object_anchors":anchors,"version": CONTEXT_VERSION}
