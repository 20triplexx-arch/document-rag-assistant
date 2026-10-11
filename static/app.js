"use strict";
const $ = (id) => document.getElementById(id);
let user = null, currentChat = null, registerMode = false, busy = false;
let libraryBooks = [];
let casesOnly = false;
let exchangeSequence = 0;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
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
function updateQuestionCount() { $("question-count").textContent = `${$("question").value.length} / 500`; }
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

function renderResult(question, result) {
  const section = node("article", undefined, "exchange");
  const exchangeId = `exchange-${++exchangeSequence}`;
  const evidenceTargets = new Map();
  section.append(node("h2", question));
  const top = node("div", undefined, "result-top");
  top.append(node("h3", result.answer ? "讲解" : "检索结果"));
  top.append(node("span", result.quote_verified ? "引用已核对" : "候选原文", "badge"));
  section.append(top);
  if (result.answer) {
    result.answer.claims.forEach(claim => {
      const wrap = node("div", undefined, "claim");
      wrap.append(node("span", claim.text));
      if ((result.evidence || []).some(item => item.evidence_id === claim.evidence_id)) {
        const reference = node("button", `[${claim.evidence_id}]`, "claim-ref");
        reference.type = "button";
        reference.setAttribute("aria-label", `查看本轮依据 ${claim.evidence_id}`);
        reference.setAttribute("aria-controls", `${exchangeId}-${claim.evidence_id}`);
        reference.addEventListener("click", () => {
          const target = evidenceTargets.get(claim.evidence_id);
          if (!target) return;
          target.open = true;
          const summary = target.querySelector("summary");
          summary.scrollIntoView({block: "start"});
          summary.focus({preventScroll: true});
        });
        wrap.append(reference);
      }
      wrap.append(node("blockquote", claim.quote, "quote")); section.append(wrap);
    });
    if (result.answer.missing_information) section.append(node("p", result.answer.missing_information, "missing"));
  } else {
    const labels = {RETRIEVAL_ONLY: "已找到以下原文。这个模式不调用模型。", NO_RETRIEVAL_MATCH: "当前章节没有检索到匹配片段，可以换一种表述或扩大资料范围。", MODEL_FAILED: "讲解服务暂时不可用，仍可阅读下面的原文。", CITATION_VALIDATION_FAILED: "模型回复的引用未通过检查，本次讲解未展示。你可以先阅读原文。"};
    section.append(node("p", labels[result.status] || "本次处理未完成。", "result-status"));
  }
  if (result.evidence && result.evidence.length) {
    section.append(node("div", "原文依据", "evidence-title"));
    result.evidence.forEach(item => {
      const detail = node("details", undefined, "evidence");
      detail.id = `${exchangeId}-${item.evidence_id}`;
      evidenceTargets.set(item.evidence_id, detail);
      const language = item.language === "en" ? " · 英文" : "";
      detail.append(node("summary", `[${item.evidence_id}] ${item.display_name || item.book}${language} · ${item.section.split(" / ").slice(-1)[0]}`));
      detail.append(node("pre", item.context_text || item.text));
      const link = node("a", `打开原文 · 第 ${item.start_line}–${item.end_line} 行`);
      link.href = item.line_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      detail.append(link); section.append(detail);
    });
  }
  if (result.books_without_match && result.books_without_match.length) section.append(node("p", `未匹配到依据的教材：${result.books_without_match.join("、")}`, "missing"));
  section.append(node("p", "引用核对不代表答案正确。", "result-meta"));
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
  const book = $("book-select").value || null;
  const explain = $("mode-select").value === "explain";
  busy = true; $("send-button").disabled = true; $("send-label").textContent = explain ? "生成中" : "检索中";
  $("question").readOnly = true; $("book-select").disabled = true; $("mode-select").disabled = true;
  $("ask-form").setAttribute("aria-busy", "true");
  notice(explain ? "生成中" : "检索中");
  try {
    if (!currentChat) { const chat = await api("/api/chats", "POST", {title: question.slice(0, 40)}); currentChat = chat.id; }
    const result = await api("/api/ask", "POST", {chat_id: currentChat, request_key: crypto.randomUUID(), question, book, explain});
    const exchange = renderResult(question, result); user.quota = result.quota; updateAccount();
    exchange.scrollIntoView({block: "start"});
    if (!["MODEL_FAILED", "CITATION_VALIDATION_FAILED"].includes(result.status)) { $("question").value = ""; updateQuestionCount(); }
    notice(); await refreshChats();
  } catch (error) { notice(error.message, "error"); }
  finally { busy = false; $("send-button").disabled = false; $("send-label").textContent = "提问"; $("question").readOnly = false; $("book-select").disabled = false; $("mode-select").disabled = false; $("ask-form").setAttribute("aria-busy", "false"); }
});

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
    renderBooks();
    $("library-button").disabled = false;
    $("cases-button").disabled = !libraryBooks.some(book => book.kind === "case_collection");
  } catch (error) { notice(error.message); }
  try { user = await api("/api/me"); updateAccount(); await refreshChats(); } catch { user = null; updateAccount(); }
}
initialize();
