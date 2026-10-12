"""Reproducible 100-question draft. New annotations require human review in the lab."""
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from study_rag.evaluation import DEFAULT_DATASET, load_dataset
from study_rag.settings import DEFAULT_DATA

# Curated source passages and five question variants per learning objective.
# These are AI-assisted proposals, not asserted human-approved labels.
SPECS=[
 ("09-metacognition","dev","metacognitive-adjustment","元认知指的是涉及思考自身思维的高级认知过程。","评估并调整其行为。",
  "元认知涉及思考自身思维，代理据自我意识和过去经验评估、调整行为。",
  ["Microsoft 教材如何定义代理的元认知？","元认知中的‘思考自身思维’是什么意思？","代理为什么需要评估并调整自身行为？请依据元认知定义说明。","按元认知介绍，过去经验如何参与代理行为调整？","Metacognition 在代理中指什么？请用教材定义解释。"]),
 ("unit2/llama-index/llama-hub","dev","llamahub-registry","**LlamaHub 是一个包含数百个集成组件","均可用于LlamaIndex框架。**",
  "LlamaHub 是可供 LlamaIndex 使用的集成组件、智能体和工具注册中心。",
  ["LlamaHub 是什么，收录哪几类资源？","我需要找 LlamaIndex 集成组件，LlamaHub 能提供什么？","请解释 LlamaHub 注册中心的定位。","LlamaHub 中的集成、智能体和工具供哪个框架使用？","为什么学习 LlamaIndex 时会遇到 LlamaHub？请说明它的资源类型。"]),
 ("unit2/langgraph/building_blocks","dev","langgraph-state-nodes","**Nodes** 是 Python 函数。每个节点：","返回状态更新",
  "LangGraph 节点是接收状态、执行操作并返回状态更新的 Python 函数。",
  ["LangGraph 的节点接收什么输入，返回什么？","Nodes 在 LangGraph 中是什么，如何处理状态？","请按输入、操作、输出解释 LangGraph 节点。","LangGraph 中一个节点函数承担哪些步骤？","为什么 LangGraph 节点会返回状态更新？请按教材说明节点工作方式。"]),
 ("unit2/langgraph/building_blocks","dev","langgraph-state-nodes","边可以是：","根据当前状态选择下一个节点",
  "直接边始终从节点 A 到 B；条件边根据当前状态选择下一个节点。",
  ["LangGraph 直接边与条件边有什么区别？","我想让流程按状态分支，应理解哪种 LangGraph 边？","直接边是否每次都走同一个后续节点？条件边呢？","LangGraph 的条件边根据什么选择下一节点？","请比较 LangGraph 两类边的控制流行为。"]),
 ("17-creating-local-ai-agents","dev","local-slm-bounded-tasks","**SLMs 擅长：**","私密地对你自己的数据迭代。",
  "SLM 适合结构化有界任务、工具调用，以及快速廉价私密地迭代自有数据。",
  ["本地代理课程列出的 SLM 优势有哪些？","小型语言模型适合哪类有界任务？","按本地代理教材，SLM 在工具调用上有什么用途？","为什么自有数据的快速迭代适合本地 SLM？请列教材优势。","SLMs 擅长哪些任务和迭代方式？请依据固定教材说明。"]),
 ("unit2/llama-index/components","dev","queryengine-role","**我们将重点关注 `QueryEngine` 组件**。","智能体的检索增强生成（RAG）工具。",
  "QueryEngine 可作为智能体的 RAG 工具，是该课重点关注的组件。",
  ["LlamaIndex 组件课为何重点介绍 QueryEngine？","QueryEngine 在智能体中可以充当什么工具？","请说明 QueryEngine 与智能体 RAG 的关系。","在 LlamaIndex 教材中，应关注哪个组件作为 RAG 工具？","QueryEngine 组件的课程定位和用途是什么？"]),
 ("unit1/what-are-llms","calibration","transformer-encoder-decoder","基于编码器的 Transformer 接收文本","逐个生成 token 以完成序列**。",
  "编码器输出输入的密集表示或嵌入；解码器逐个生成 token 完成序列。",
  ["编码器与解码器 Transformer 的输出方式有何不同？","编码器产生嵌入，解码器产生什么？","请比较 encoder 与 decoder 的核心工作方式。","用于生成文本的解码器与产生密集表示的编码器有何区别？","按照 LLM 教材，Transformer 两种架构分别如何处理输入与输出？"]),
 ("unit1/messages-and-special-tokens","calibration","chat-template-formatting","这就是聊天模板的用武之地。","正确格式化的提示。",
  "聊天模板连接对话消息与模型的特定格式要求，让模型收到正确格式化提示。",
  ["聊天模板在对话消息与模型输入之间起什么作用？","为什么不同模型需要对应的 chat template？","聊天模板如何帮助模型接收对话消息？","Chat templates 是哪些内容之间的桥梁？","请解释聊天模板与模型特殊 token 格式要求的关系。"]),
 ("unit2/smolagents/tool_calling_agents","calibration","action-representation","关键区别在于**操作结构方式**：","执行相应工具。",
  "ToolCallingAgent 生成工具名与参数的 JSON，系统解析并执行；CodeAgent 生成可执行代码。",
  ["ToolCallingAgent 和 CodeAgent 的操作结构有何区别？","工具调用智能体生成 JSON 后由谁执行工具？","smolagents 的工具调用智能体为什么不直接生成可执行代码？","请解释 JSON 形式的工具名称和参数如何变成实际工具执行。","比较两种 smolagents 智能体生成操作指令的形式。"]),
 ("unit2/llama-index/workflows","calibration","workflow-events","这种工作流通过定义由","触发后续步骤。",
  "LlamaIndex 工作流由事件触发步骤，步骤发出事件触发后续步骤。",
  ["LlamaIndex 工作流的事件与步骤如何连接？","Events 如何触发 Steps，步骤又如何触发下一步？","请解释 LlamaIndex 工作流的事件驱动机制。","LlamaIndex 中一个步骤发出事件有什么作用？","LlamaIndex Workflow 如何组织连续的执行步骤？"]),
 ("unit2/smolagents/vision_agents","holdout","vision-task-images","该方法在智能体启动时","持续处理这些图像。",
  "通过 task_images 在启动时传入图像，智能体执行过程中持续处理它们。",
  ["smolagents 视觉智能体启动时如何接收图像？","task_images 参数用于哪个阶段，图像之后如何处理？","初始执行阶段提供图像的方式是什么？","视觉智能体能否在启动时获得供后续处理的图像？请依据课程说明。","按视觉智能体教材，task_images 怎样参与执行流程？"]),
 ("11-agentic-protocols","holdout","protocol-interoperability","MCP 专注于连接 LLM 与工具","共同完成共享任务。",
  "MCP 连接 LLM 与工具；A2A 支持不同组织、环境及技术栈的代理通信协作。",
  ["MCP 与 A2A 分别连接什么对象？","不同技术栈的代理要协作，A2A 的定位是什么？","为什么连接 LLM 与工具和连接代理之间要区分协议？","请按教材比较 MCP 与 Agent-to-Agent 的目的。","MCP 面向工具连接，A2A 如何支持跨组织的代理共享任务？"]),
]


def main():
    loaded=load_dataset(DEFAULT_DATASET,DEFAULT_DATA)
    dataset=deepcopy(loaded[0].model_dump())
    dataset.update(schema_version=2,dataset_version="agent-learning-v2.0-draft",annotated_on="2026-10-12",
        annotation_method="40题继承v1.1人工标注；60题为Codex阅读原文后的AI辅助草稿，必须由维护者逐题复核；同学习目标不跨分组。")
    for q in dataset["questions"]:
        q.update(review_status="approved",review_note="继承冻结v1.1的人工原文标注；本轮未重新宣称人工审阅。")
    for spec_index,(chapter,split,group,start_marker,end_marker,answer,questions) in enumerate(SPECS,1):
        source=next(s for s in loaded[4].values() if s.chapter==chapter)
        text=loaded[5][source.source_id]
        start=text.index(start_marker)
        end=text.index(end_marker,start)+len(end_marker)
        support=dict(source_id=source.source_id,start_char=start,end_char=end,quote=text[start:end],
                     start_line=text.count('\n',0,start)+1,end_line=text.count('\n',0,end-1)+1,
                     rationale="AI辅助选择的明确支持段落；待维护者核对题面、要点、全文位置与分组。")
        for variant,question in enumerate(questions,1):
            dataset["questions"].append(dict(id=f"N{spec_index:02}_{variant}",group=group,split=split,
                category="single" if variant==1 else "paraphrase",question=question,book=source.book,
                required_books=[source.book],answerability="answerable",points=[dict(id="p1",answer=answer,supports=[support])],
                distractors=[],missing_information=[],review_scope=None,review_status="pending",review_note="AI辅助标注，待人工复核。"))
    path=DEFAULT_DATASET.with_name("agent-learning-v2.json")
    path.write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n',encoding="utf-8")
    checked=load_dataset(path,DEFAULT_DATA)
    from collections import Counter
    print(json.dumps({"questions":len(checked[0].questions),"splits":dict(Counter(q.split for q in checked[0].questions)),"sha256":checked[1],"pending":60},ensure_ascii=False))


if __name__=="__main__":main()
