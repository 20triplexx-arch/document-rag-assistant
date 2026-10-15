"use strict";
const $ = (id) => document.getElementById(id);
let user = null, currentChat = null, registerMode = false, busy = false;
let libraryBooks = [];
let modelChoices = [];
let modelSelectionSupported = false;
let streamingSupported = false;
let casesOnly = false;
let exchangeSequence = 0;
const QUESTION_MAX_CHARS = 10000;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function readableHeading(text) {
  return text.replace(/<[^>]*>/g, "").replace(/!?\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\*\*|__|`/g, "").trim();
}
function renderModels(library) {
  streamingSupported = library.streaming_answers === true;
  const previous = $("model-select").value;
  modelSelectionSupported = Array.isArray(library.models);
  // 旧版服务仍提供 model 字段，保持升级时的页面兼容。
  modelChoices = library.models || (library.model ? [{id:library.model, display_name:library.model}] : []);
  $("model-select").replaceChildren();
  modelChoices.forEach(item => {
    const option = node("option", `${item.display_name}${item.description ? " · 费用较高" : ""}`);
    option.value = item.id; option.title = item.description || item.display_name;
    $("model-select").append(option);
  });
  $("model-select").value = modelChoices.some(item => item.id === previous) ? previous
    : library.default_model || library.model || modelChoices[0]?.id || "";
  $("model-select").disabled = busy || $("mode-select").value === "retrieve" || !modelChoices.length;
  const autoOption = $("style-select").querySelector('option[value="auto"]');
  if (autoOption) autoOption.disabled = !library.adaptive_answers;
  if (!library.adaptive_answers && $("style-select").value === "auto") $("style-select").value = "deep";
}
function notice(text = "", tone = "info") { $("notice").textContent = text; $("notice").hidden = !text; $("notice").dataset.tone = tone; }
function updateWorkspace() { $("workspace").classList.toggle("has-results", $("results").children.length > 0); }
function clearResults() { $("results").replaceChildren(); updateWorkspace(); }
if (typeof ResizeObserver !== "undefined") {
  new ResizeObserver(() => {
    document.documentElement.style.setProperty("--composer-height", `${$("composer").getBoundingClientRect().height}px`);
  }).observe($("composer"));
}
async function api(path, method = "GET", body) {
  const headers = {"Content-Type": "application/json"};
  if (user && method !== "GET") headers["X-CSRF-Token"] = user.csrf;
  const response = await fetch(path, {method, headers, credentials: "same-origin", body: body === undefined ? undefined : JSON.stringify(body)});
  let payload;
  try { payload = await response.json(); } catch { throw new Error("服务响应异常，请稍后再试。"); }
  if (!response.ok) throw new Error(payload.detail || "操作失败，请重试。");
  return payload;
}
function updateAccount() {
  $("account-button").textContent = user ? `${user.username}${user.role === "admin" ? " · 管理员" : ""} · 退出` : "登录 / 注册";
  $("admin-button").hidden = !user || user.role !== "admin";
  $("quota").textContent = user ? `今日讲解 ${user.quota.used} / ${user.quota.limit}` : "";
}
function showAuth() { $("auth-error").textContent = ""; $("auth-dialog").showModal(); }
function resizeQuestion() {
  const field = $("question");
  if (!field.style || !field.scrollHeight) return;
  field.style.height = "0px";
  field.style.height = `${field.scrollHeight}px`;
}
function updateQuestionCount() {
  // Unicode 字符计数与后端一致；HTML maxlength 留出代理对的空间。
  const count = Array.from($("question").value).length;
  $("question-count").textContent = `${count} / ${QUESTION_MAX_CHARS}`;
  $("question-count").dataset.overLimit = String(count > QUESTION_MAX_CHARS);
  resizeQuestion();
}
$("question").addEventListener("input", updateQuestionCount);
function setHistoryOpen(open) {
  document.querySelector(".sidebar").classList.toggle("history-open", open);
  $("history-toggle").setAttribute("aria-expanded", String(open));
}
$("history-toggle").addEventListener("click", () => setHistoryOpen($("history-toggle").getAttribute("aria-expanded") !== "true"));
$("close-library").addEventListener("click", () => $("library-dialog").close());
function renderLibrary() {
  const query = $("library-search").value.trim().toLocaleLowerCase();
  let count = 0;
  $("library-list").replaceChildren();
  libraryBooks.forEach(book => {
    if (casesOnly && book.kind !== "case_collection") return;
    const chapters = book.chapters.filter(chapter => `${book.book} ${book.display_name || book.book} ${chapter.title} ${chapter.path} ${(chapter.topics || []).join(" ")}`.toLocaleLowerCase().includes(query));
    if (!chapters.length) return;
    count += chapters.length;
    const group = node("section", undefined, "library-group");
    group.append(node("h3", `${book.display_name || book.book} · ${book.documents} 篇 · ${book.chunks} 个片段`));
    if (book.source_files > book.documents || book.notebook_cells) {
      group.append(node("p", `${book.source_files} 个原始文件${book.notebook_cells ? ` · ${book.notebook_cells} 个 Notebook 教学单元` : ""}`, "result-meta"));
    }
    const license = node("a", `作者与许可：${book.license}`);
    license.href = book.license_url; license.target = "_blank"; license.rel = "noopener noreferrer";
    group.append(license);
    chapters.forEach(chapter => {
      const row = node("div", undefined, "library-row");
      const link = node("a", chapter.title === "README" || chapter.title === "readme" ? chapter.path : chapter.title);
      link.href = chapter.source_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      row.append(link, node("small", `${chapter.language === "en" ? "英文" : "中文"} · ${chapter.chunks} 个片段 · ${chapter.path}`));
      if (chapter.topics && chapter.topics.length) row.append(node("small", chapter.topics.join(" · ")));
      if (chapter.implementation_links && chapter.implementation_links.length) {
        const implementations = node("small");
        chapter.implementation_links.forEach(item => {
          const code = node("a", `实现：${item.path.split("/").slice(-1)[0]} `);
          code.href = item.url; code.target = "_blank"; code.rel = "noopener noreferrer";
          implementations.append(code);
        });
        row.append(implementations);
      }
      group.append(row);
    });
    $("library-list").append(group);
  });
  $("library-search-count").textContent = `${count} ${casesOnly ? "个案例" : "篇资料"}${query ? "匹配" : "已收录"}`;
  if (!count) $("library-list").append(node("p", casesOnly ? "没有找到相关案例，试试其他关键词。" : "没有找到相关章节，试试其他关键词。", "library-empty"));
}
$("library-search").addEventListener("input", renderLibrary);
function openLibrary(showCases = false) {
  casesOnly = showCases;
  $("library-title").textContent = showCases ? "实战案例" : "资料目录";
  $("library-search").value = "";
  renderLibrary();
  $("library-dialog").showModal();
}
$("library-button").addEventListener("click", () => openLibrary());
$("cases-button").addEventListener("click", () => openLibrary(true));
$("close-admin").addEventListener("click", () => $("admin-dialog").close());
$("admin-button").addEventListener("click", async () => {
  if (busy) return;
  try {
    const stats = await api("/api/admin/overview");
    $("admin-stats").replaceChildren();
    const labels = [["学习账号", stats.users], ["学习讨论", stats.chats], ["问答记录", stats.exchanges],
      ["今日已预留讲解", `${stats.today_reserved} / ${stats.global_daily_limit}`],
      ["正在生成", `${stats.active_generations} / ${stats.max_concurrent}`]];
    labels.forEach(([label, value]) => {
      const card = node("div", undefined, "stat-card");
      card.append(node("span", label), node("strong", String(value)));
      $("admin-stats").append(card);
    });
    $("admin-dialog").showModal();
  } catch (error) { notice(error.message); }
});
function selectBook(book) {
  if (busy) return;
  $("book-select").value = book;
  $("ask-form").classList.toggle("single-book", Boolean(book));
  document.querySelectorAll(".book-card").forEach(card => {
    const selected = card.dataset.book === book;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", String(selected));
    card.querySelector(".book-state").textContent = selected ? "已选" : "";
  });
}
function renderBooks() {
  $("book-grid").replaceChildren();
  const all = node("option", "全部教材"); all.value = "";
  $("book-select").replaceChildren(all);
  libraryBooks.forEach(book => {
    const name = book.display_name || book.book;
    const isCase = book.kind === "case_collection";
    const option = node("option", name); option.value = book.book; $("book-select").append(option);
    const card = node("button", undefined, "book-card"); card.type = "button"; card.dataset.book = book.book;
    card.setAttribute("aria-pressed", "false");
    card.setAttribute("aria-label", isCase ? `浏览 ${name} 并设为提问范围` : `选择 ${name} 教材`);
    if (isCase) { card.setAttribute("aria-haspopup", "dialog"); card.setAttribute("aria-controls", "library-dialog"); }
    const info = node("span", undefined, "book-info");
    info.append(node("strong", name), node("span", isCase ? `${book.documents} 个案例 · 查看目录` : `${book.documents} 篇资料`));
    card.append(info, node("span", "", "book-state"));
    card.addEventListener("click", () => {
      if (isCase) { selectBook(book.book); openLibrary(true); }
      else selectBook($("book-select").value === book.book ? "" : book.book);
    });
    $("book-grid").append(card);
  });
  selectBook("");
}
$("book-select").addEventListener("change", () => selectBook($("book-select").value));
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => { if (busy) return; $("question").value = button.dataset.question; updateQuestionCount(); $("question").focus(); }));

async function refreshChats() {
  $("chat-list").replaceChildren();
  if (!user) { $("chat-list").append(node("p", "登录后保存学习记录", "side-hint")); return; }
  const chats = await api("/api/chats");
  if (!chats.length) $("chat-list").append(node("p", "还没有讨论", "side-hint"));
  chats.forEach(chat => {
    const row = node("div", undefined, "chat-row");
    const open = node("button", chat.title, "chat-open");
    open.classList.toggle("active", chat.id === currentChat);
    open.addEventListener("click", async () => {
      if (busy) return;
      try {
        const history = await api(`/api/chats/${chat.id}`);
        currentChat = chat.id; clearResults();
        history.forEach(item => renderResult(item.question, item.result));
        setHistoryOpen(false);
        await refreshChats(); notice();
      } catch (error) { notice(error.message); }
    });
    const remove = node("button", undefined, "chat-delete");
    const removeIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    removeIcon.setAttribute("viewBox", "0 0 24 24"); removeIcon.setAttribute("aria-hidden", "true");
    const removePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    removePath.setAttribute("d", "m6 6 12 12M6 18 18 6");
    removeIcon.append(removePath); remove.append(removeIcon);
    remove.setAttribute("aria-label", `删除讨论：${chat.title}`);
    remove.addEventListener("click", async () => {
      if (busy || !window.confirm("删除这条讨论及其中的问答记录？")) return;
      try {
        await api(`/api/chats/${chat.id}`, "DELETE");
        if (currentChat === chat.id) { currentChat = null; clearResults(); }
        await refreshChats();
      } catch (error) { notice(error.message); }
    });
    row.append(open, remove); $("chat-list").append(row);
  });
}

function renderResult(question, result, preview = false) {
  const section = node("article", undefined, "exchange");
  const exchangeId = `exchange-${++exchangeSequence}`;
  const evidenceTargets = new Map();
  const sourcePanel = result.answer && result.evidence?.length ? node("details", undefined, "answer-sources") : null;
  if (sourcePanel) sourcePanel.append(node("summary", `查看原文依据 · ${result.evidence.length} 条`));
  const questionChars = Array.from(question);
  section.append(node("h2", questionChars.length > 240 ? `${questionChars.slice(0, 160).join("")}…` : question));
  if (questionChars.length > 240) {
    const fullQuestion = node("details", undefined, "full-question");
    fullQuestion.append(node("summary", `展开完整问题 · ${questionChars.length} 字`));
    fullQuestion.append(node("pre", question));
    section.append(fullQuestion);
  }
  const top = node("div", undefined, "result-top");
  top.append(node("h3", result.answer ? "讲解" : "检索结果"));
  const badge = node("span", preview ? "生成中" : result.quote_verified ? "引用已核对" : "候选原文", "badge");
  top.append(badge);
  section.append(top);
  const usedModel = result.usage?.model || result.selected_model;
  const modelInfo = node("p", "", "result-model");
  modelInfo.hidden = !usedModel || !(result.model_calls > 0);
  if (!modelInfo.hidden) modelInfo.textContent = `模型：${modelChoices.find(item => item.id === usedModel)?.display_name || usedModel}`;
  if (preview || !modelInfo.hidden) section.append(modelInfo);
  const answerBody = node("div", undefined, "answer-body");
  const missing = node("p", "", "missing"); missing.hidden = true;
  const streamedBlocks = [];
  function addReferences(wrap, references) {
      const grouped = new Map();
      for (const ref of references) {
        if (!grouped.has(ref.evidence_id)) grouped.set(ref.evidence_id, {evidence_id:ref.evidence_id,quotes:[]});
        const quotes = grouped.get(ref.evidence_id).quotes;
        if (!quotes.includes(ref.quote)) quotes.push(ref.quote);
      }
      for (const ref of grouped.values()) {
        if (!(result.evidence || []).some(item => item.evidence_id === ref.evidence_id)) continue;
        const reference = node("button", `[${ref.evidence_id}]`, "claim-ref");
        reference.type = "button";
        reference.setAttribute("aria-label", `查看本轮依据 ${ref.evidence_id}`);
        reference.setAttribute("aria-controls", `${exchangeId}-${ref.evidence_id}`);
        reference.addEventListener("click", () => {
          const target = evidenceTargets.get(ref.evidence_id);
          if (!target) return;
          if (sourcePanel) sourcePanel.open = true;
          target.open = true;
          const excerpt = target.querySelector(".quote");
          excerpt.textContent = ref.quotes.length > 1
            ? ref.quotes.map((quote,index) => `摘录 ${index+1}：\n${quote}`).join("\n\n") : ref.quotes[0];
          excerpt.hidden = false;
          const summary = target.querySelector("summary");
          summary.scrollIntoView({block: "start"});
          summary.focus({preventScroll: true});
        });
        wrap.append(reference);
      }
  }
  if (result.answer) {
    appendAnswerBlocks(answerBody, result.answer, node, addReferences);
    section.append(answerBody, missing);
    missing.textContent = result.answer.missing_information || ""; missing.hidden = !missing.textContent;
  } else {
    const labels = {CONTEXT_REQUIRED: "请写明想继续学习的主题，或打开有相关内容的讨论后追问。", RETRIEVAL_ONLY: "已找到以下原文。这个模式不调用模型。", NO_RETRIEVAL_MATCH: "当前章节没有检索到匹配片段，可以换一种表述或扩大资料范围。", MODEL_FAILED: "讲解服务暂时不可用，仍可阅读下面的原文。", CITATION_VALIDATION_FAILED: "模型回复的引用未通过检查，本次讲解未展示。你可以先阅读原文。"};
    const failureLabels = {response_schema:"回复结构未通过检查，本次讲解未展示。可先阅读下方原文。", quote_source:"引用与原文不符，本次讲解未展示。可先阅读下方原文。", source_scope:"回复中的源码归属或依赖关系未通过检查，本次讲解未展示。可先阅读下方原文。", service:"讲解服务暂时不可用，可先阅读下方原文。"};
    const statusText = result.error_type === "MODEL_OUTPUT_LIMIT"
      ? "讲解达到输出上限，未能完整生成。你可以把问题拆成几部分分别提问；本轮原文仍可阅读。"
      : failureLabels[result.failure_stage] || labels[result.status] || "本次处理未完成。";
    section.append(node("p", statusText, "result-status"));
  }
  if (result.evidence && result.evidence.length) {
    const evidenceContainer = sourcePanel || section;
    if (!sourcePanel) section.append(node("div", "原文依据", "evidence-title"));
    result.evidence.forEach(item => {
      const detail = node("details", undefined, "evidence");
      detail.id = `${exchangeId}-${item.evidence_id}`;
      evidenceTargets.set(item.evidence_id, detail);
      const language = item.language === "en" ? " · 英文" : "";
      const version = item.applicable_versions?.filter(v => v !== "pinned-documentation").join("、");
      detail.append(node("summary", `[${item.evidence_id}] ${item.display_name || item.book}${language}${version ? ` · ${version === "unknown" ? "版本未声明" : version}` : ""} · ${readableHeading(item.section.split(" / ").slice(-1)[0])}`));
      if (sourcePanel) { const quote = node("blockquote", "", "quote"); quote.hidden = true; detail.append(quote); }
      detail.append(node("pre", item.context_text || item.text, item.content_type === "code" ? "source-code" : ""));
      const location = item.source_locator;
      const link = node("a", location?.kind === "notebook_cell"
        ? `打开 Notebook · 单元 ${location.cell_index} · 第 ${location.start_line}–${location.end_line} 行`
        : `打开原文 · 第 ${item.start_line}–${item.end_line} 行`);
      link.href = item.line_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      detail.append(link); evidenceContainer.append(detail);
    });
    if (sourcePanel) section.append(sourcePanel);
  }
  const metadataContainer = sourcePanel || section;
  if (result.books_without_match && result.books_without_match.length) metadataContainer.append(node("p", `未匹配到依据的教材：${result.books_without_match.join("、")}`, "missing"));
  if (result.context_turns) metadataContainer.append(node("p", `联系了最近 ${result.context_turns} 轮讨论。`, "result-meta"));
  function addFollowups() {
  if (result.answer && answerUnits(result.answer).length) {
    const followups = node("div", undefined, "followup-actions");
    followups.setAttribute("aria-label", "继续学习");
    const topic = Array.from(question).slice(0, 180).join("");
    const suggestions = result.followups || [
      {label:"看具体例子", question:`围绕问题「${topic}」，请用资料中的具体例子解释机制和适用条件。`},
      {label:"找常见失败", question:`围绕问题「${topic}」，容易在哪一步失败？请给出有依据的检查方法。`},
    ];
    for (const suggestion of suggestions.slice(0, 2)) {
      const {label, question:prompt} = suggestion;
      const button = node("button", label, "text-button");
      button.type = "button";
      button.addEventListener("click", () => {
        if (busy) return;
        if ($("question").value.trim()) { notice("输入框中已有问题，请先发送或清空。", "info"); return; }
        $("question").value = prompt;
        $("style-select").value = "auto"; $("mode-select").value = "explain";
        $("style-select").disabled = false; $("use-history").checked = true;
        $("model-select").disabled = !modelChoices.length;
        updateQuestionCount(); $("question").focus();
      });
      followups.append(button);
    }
    section.append(followups);
  }
  }
  if (!preview) addFollowups();
  section.appendAnswerBlock = block => {
    streamedBlocks.push(block);
    appendAnswerBlocks(answerBody, {schema_version:2, blocks:[block]}, node, addReferences);
  };
  section.completeStream = finalResult => {
    result = finalResult;
    if (JSON.stringify(answerBlocks(result.answer)) !== JSON.stringify(streamedBlocks)) {
      answerBody.replaceChildren();
      appendAnswerBlocks(answerBody, result.answer, node, addReferences);
    }
    badge.textContent = result.quote_verified ? "引用已核对" : "候选原文";
    const name = result.usage?.model || result.selected_model;
    modelInfo.hidden = !name || !(result.model_calls > 0);
    modelInfo.textContent = modelInfo.hidden ? "" : `模型：${modelChoices.find(item => item.id === name)?.display_name || name}`;
    missing.textContent = result.answer?.missing_information || ""; missing.hidden = !missing.textContent;
    addFollowups();
  };
  $("results").append(section);
  updateWorkspace();
  return section;
}

$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  if (!user) { showAuth(); return; }
  const question = $("question").value.trim();
  if (!question) return;
  if (Array.from(question).length > QUESTION_MAX_CHARS) {
    notice(`问题最多 ${QUESTION_MAX_CHARS} 字，请删减后再提问。`, "error");
    $("question").focus();
    return;
  }
  const book = $("book-select").value || null;
  const explain = $("mode-select").value === "explain";
  busy = true; $("send-button").disabled = true; $("send-label").textContent = explain ? "生成中" : "检索中";
  $("question").readOnly = true; $("book-select").disabled = true; $("mode-select").disabled = true;
  $("style-select").disabled = true; $("use-history").disabled = true;
  $("model-select").disabled = true;
  $("ask-form").setAttribute("aria-busy", "true");
  notice(explain ? "生成中" : "检索中");
  let preview = null;
  try {
    if (!currentChat) { const chat = await api("/api/chats", "POST", {title: Array.from(question).slice(0, 40).join("")}); currentChat = chat.id; }
    const body = {chat_id: currentChat, request_key: crypto.randomUUID(), question, book, explain,
      explanation_style: $("style-select").value, use_history: $("use-history").checked,
      ...(modelSelectionSupported ? {model: $("model-select").value || null} : {})};
    let result;
    if (explain && streamingSupported) {
      const response = await fetch("/api/ask/stream", {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json", "X-CSRF-Token":user.csrf}, body:JSON.stringify(body)});
      result = await readAnswerStream(response, event => {
        if (event.type === "progress") notice(({retrieval:"检索中", generation:"生成中", validation:"核对引用中"})[event.stage] || "处理中");
        if (event.type === "evidence") {
          preview = renderResult(question, {...event.pack, model_calls:0,
            answer:{schema_version:2, status:"answered", blocks:[], missing_information:""}}, true);
          preview.scrollIntoView({block:"start"});
        }
        if (event.type === "block" && preview) preview.appendAnswerBlock(event.block);
      });
    } else result = await api("/api/ask", "POST", body);
    if (preview && result.answer) preview.completeStream(result);
    else {
      if (preview) preview.remove();
      const exchange = renderResult(question, result);
      if (!preview) exchange.scrollIntoView({block:"start"});
    }
    user.quota = result.quota; updateAccount();
    if (!["MODEL_FAILED", "CITATION_VALIDATION_FAILED", "CONTEXT_REQUIRED"].includes(result.status)) { $("question").value = ""; updateQuestionCount(); }
    notice(); await refreshChats();
  } catch (error) {
    if (preview) preview.remove();
    updateWorkspace(); notice(error.message, "error");
  }
  finally { busy = false; $("send-button").disabled = false; $("send-label").textContent = "提问"; $("question").readOnly = false; $("book-select").disabled = false; $("mode-select").disabled = false; $("use-history").disabled = false; $("style-select").disabled = $("mode-select").value === "retrieve"; $("model-select").disabled = $("mode-select").value === "retrieve" || !modelChoices.length; $("ask-form").setAttribute("aria-busy", "false"); }
});

$("mode-select").addEventListener("change", () => { $("style-select").disabled = $("mode-select").value === "retrieve"; $("model-select").disabled = $("mode-select").value === "retrieve" || !modelChoices.length; });

$("new-chat").addEventListener("click", () => { if (!user) { showAuth(); return; } if (busy) return; currentChat = null; clearResults(); notice(); setHistoryOpen(false); refreshChats().catch(error => notice(error.message)); $("question").focus(); });
$("close-auth").addEventListener("click", () => $("auth-dialog").close());
$("auth-toggle").addEventListener("click", () => {
  registerMode = !registerMode;
  $("auth-title").textContent = registerMode ? "创建账号" : "登录";
  $("auth-submit").textContent = registerMode ? "注册" : "登录";
  $("auth-toggle").textContent = registerMode ? "返回登录" : "创建账号";
  $("password").autocomplete = registerMode ? "new-password" : "current-password";
  $("auth-error").textContent = "";
});
$("auth-form").addEventListener("submit", async event => {
  event.preventDefault(); $("auth-submit").disabled = true;
  try {
    user = await api(registerMode ? "/api/register" : "/api/login", "POST", {username: $("username").value.trim(), password: $("password").value});
    $("password").value = ""; currentChat = null; clearResults();
    $("auth-dialog").close(); updateAccount(); await refreshChats(); notice("已进入你的学习空间。输入问题即可开始。");
  } catch (error) { $("auth-error").textContent = error.message; }
  finally { $("auth-submit").disabled = false; }
});
$("account-button").addEventListener("click", async () => {
  if (!user) { showAuth(); return; }
  if (busy) return;
  try { await api("/api/logout", "POST", {}); user = null; currentChat = null; clearResults(); updateAccount(); await refreshChats(); notice("已退出账号。"); }
  catch (error) { notice(error.message); }
});

async function initialize() {
  try {
    const library = await api("/api/library");
    libraryBooks = library.books;
    if (Number.isInteger(library.source_files)) {
      $("library-coverage").textContent = `${library.snapshot ? `当前语料 ${library.snapshot} · ` : ""}当前收录 ${library.source_files} 个文件${library.notebook_cells ? ` · ${library.notebook_cells} 个 Notebook 教学单元` : ""} · ${library.chunks} 个检索片段`;
      $("library-coverage").hidden = false;
    }
    renderModels(library);
    renderBooks();
    $("library-button").disabled = false;
    $("cases-button").disabled = !libraryBooks.some(book => book.kind === "case_collection");
  } catch (error) { notice(error.message); }
  try { user = await api("/api/me"); updateAccount(); await refreshChats(); } catch { user = null; updateAccount(); }
}
initialize();
