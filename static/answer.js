"use strict";
// All answer text is DOM text. No HTML, markdown execution, or source-code execution.
function answerBlocks(answer) {
  if (answer?.schema_version === 2) return answer.blocks || [];
  const items = (answer?.claims || []).map(c => ({text:c.text, heading:c.heading,
    references:[{evidence_id:c.evidence_id, quote:c.quote}]}));
  if (["steps", "bullets"].includes(answer?.format)) return items.length ? [{type:"list", ordered:answer.format === "steps", items}] : [];
  return items.map(item => ({type:"paragraph", ...item}));
}
function answerUnits(answer) {
  return answerBlocks(answer).flatMap(b => b.type === "paragraph" ? [b] : b.type === "list" ? b.items
    : b.type === "table" ? b.rows.map(r => ({text:r.cells.join(" | "), references:r.references}))
    : b.type === "code" ? [{text:b.code, references:b.references}] : []);
}
function appendAnswerBlocks(container, answer, make, addReferences) {
  let lastHeading = "";
  function content(parent, item) {
    if (item.heading && item.heading !== lastHeading) { parent.append(make("h4", item.heading, "answer-heading")); lastHeading = item.heading; }
    const wrap = make("div", undefined, "claim");
    wrap.append(make("span", item.text, "claim-text"));
    addReferences(wrap, item.references || []); parent.append(wrap);
  }
  for (const block of answerBlocks(answer)) {
    if (block.type === "paragraph") content(container, block);
    else if (block.type === "list") {
      const list = make(block.ordered ? "ol" : "ul", undefined, "answer-list");
      for (const item of block.items) { const li = make("li"); content(li, item); list.append(li); }
      container.append(list);
    } else if (block.type === "code") {
      const wrap = make("div", undefined, "answer-code");
      wrap.append(make("p", `${block.origin === "source" ? "原文代码" : "教学示意"} · 未执行`, "code-origin"));
      const pre = make("pre"); pre.append(make("code", block.code)); wrap.append(pre);
      addReferences(wrap, block.references || []); container.append(wrap);
    } else if (block.type === "table") {
      const wrap = make("div", undefined, "answer-table-scroll");
      wrap.setAttribute("role", "region"); wrap.setAttribute("aria-label", "回答对照表，可左右滚动"); wrap.tabIndex = 0;
      const table = make("table", undefined, "answer-table"); const head = make("thead"); const header = make("tr");
      for (const label of [...block.columns, "依据"]) { const th = make("th", label); th.setAttribute("scope", "col"); header.append(th); }
      head.append(header); table.append(head); const body = make("tbody");
      for (const row of block.rows) { const tr = make("tr"); for (const cell of row.cells) tr.append(make("td", cell));
        const refs = make("td"); addReferences(refs, row.references || []); tr.append(refs); body.append(tr); }
      table.append(body); wrap.append(table); container.append(wrap);
    }
  }
}
