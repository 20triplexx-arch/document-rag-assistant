"""本地回答篇幅建议；不调用模型分类，不截断生成结果。"""
from __future__ import annotations

import re

RESPONSE_POLICY_VERSION = "adaptive-answer-v1"


def response_plan(question: str, style: str = "auto") -> dict:
    """长度是软上限，不能为达到上限补内容；用户明确要求优先。"""
    brief = bool(re.search(r"一句话|简短|简洁|简要|简单介绍|只(?:要|说|给).{0,5}(?:结论|答案)|"
                          r"不要.{0,4}(?:展开|长篇|详细)|\b(?:brief|concise|short answer)\b", question, re.I))
    requested_limit = re.search(r"(?:不超过|最多|控制在|限|用)?\s*(\d{1,4})\s*字(?:以内|内|左右)?", question)
    detailed = bool(re.search(r"详细|深入|讲透|完整推导|从零|逐步解释|展开讲|\b(?:in detail|in depth)\b", question, re.I))
    comparison = bool(re.search(r"区别|比较|对比|怎么选|如何选|优缺点|\b(?:versus|vs\.?|compare|difference)\b", question, re.I))
    steps = bool(re.search(r"步骤|如何实现|怎么实现|怎么做|如何做|如何搭建|怎么搭建|怎么安装|如何安装|"
                          r"\b(?:steps|how to (?:build|implement|install))\b", question, re.I))
    definition = bool(re.search(r"是什么|什么意思|什么是|\b(?:what is|define)\b", question, re.I))
    if brief or requested_limit:
        kind, limit, preferred = "brief", 160, "plain"
    elif detailed or style == "deep":
        kind, limit, preferred = "detailed", 1400, "plain"
    elif comparison or style == "compare":
        kind, limit, preferred = "comparison", 650, "bullets"
    elif steps or style == "practice":
        kind, limit, preferred = "steps", 800, "steps"
    elif definition:
        kind, limit, preferred = "definition", 260, "plain"
    else:
        kind, limit, preferred = "focused", 500, "plain"
    if requested_limit:
        limit = max(1, int(requested_limit[1]))
    return {"version": RESPONSE_POLICY_VERSION, "kind": kind,
            "suggested_max_characters": limit, "preferred_format": preferred,
            "instruction": "字数包含claims.text与missing_information，不含quote和JSON字段名；是篇幅建议而非最低要求。回答清楚就停止；"
                           "具体步骤或多个必要子问题可适当超出建议，不添加题目未问的通用章节。"
                           "用户要求的长度和形式优先；资料少就少写。"}
