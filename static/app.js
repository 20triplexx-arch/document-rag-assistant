"use strict";
const $ = (id) => document.getElementById(id);
let user = null, currentChat = null, registerMode = false, busy = false;
let libraryBooks = [];

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(text = "") { $("notice").textContent = text; $("notice").hidden = !text; }
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
    const chapters = book.chapters.filter(chapter => `${book.book} ${chapter.title} ${chapter.path}`.toLocaleLowerCase().includes(query));
    if (!chapters.length) return;
    count += chapters.length;
    const group = node("section", undefined, "library-group");
    group.append(node("h3", `${book.book} · ${book.documents} 篇 · ${book.chunks} 个片段`));
    const license = node("a", `作者与许可：${book.license}`);
    license.href = book.license_url; license.target = "_blank"; license.rel = "noopener noreferrer";
    group.append(license);
    chapters.forEach(chapter => {
      const row = node("div", undefined, "library-row");
      const link = node("a", chapter.title === "README" || chapter.title === "readme" ? chapter.path : chapter.title);
      link.href = chapter.source_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      row.append(link, node("small", `${chapter.chunks} 个片段 · ${chapter.path}`));
      group.append(row);
    });
    $("library-list").append(group);
  });
  $("library-search-count").textContent = `${count} 篇资料${query ? "匹配" : "已收录"}`;
  if (!count) $("library-list").append(node("p", "没有找到相关章节，试试其他关键词。", "library-empty"));
}
$("library-search").addEventListener("input", renderLibrary);
$("library-button").addEventListener("click", () => {
  $("library-search").value = "";
  renderLibrary();
  $("library-dialog").showModal();
});
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
  $("book-select").value = book;
  $("ask-form").classList.toggle("single-book", Boolean(book));
  document.querySelectorAll(".book-card").forEach(card => {
    const selected = card.dataset.book === book;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", String(selected));
  });
}
document.querySelectorAll(".book-card").forEach(card => card.addEventListener("click", () => selectBook($("book-select").value === card.dataset.book ? "" : card.dataset.book)));
$("book-select").addEventListener("change", () => selectBook($("book-select").value));
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => { $("question").value = button.dataset.question; updateQuestionCount(); $("question").focus(); }));

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
        currentChat = chat.id; $("results").replaceChildren();
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
        if (currentChat === chat.id) { currentChat = null; $("results").replaceChildren(); }
        await refreshChats();
      } catch (error) { notice(error.message); }
    });
    row.append(open, remove); $("chat-list").append(row);
  });
}

function renderResult(question, result) {
  const section = node("article", undefined, "exchange");
  section.append(node("div", "学习问题", "question-label"), node("h3", question));
  const top = node("div", undefined, "result-top");
  top.append(node("h4", result.answer ? "教材讲解" : "原文与检索结果"));
  top.append(node("span", result.quote_verified ? "引文已核对 · 内容待核查" : "候选原文 · 尚未生成结论", "badge"));
  section.append(top);
  if (result.answer) {
    result.answer.claims.forEach(claim => {
      const wrap = node("div", undefined, "claim");
      wrap.append(node("span", claim.text), node("span", `[${claim.evidence_id}]`, "claim-ref"));
      wrap.append(node("blockquote", claim.quote, "quote")); section.append(wrap);
    });
    if (result.answer.missing_information) section.append(node("p", result.answer.missing_information, "missing"));
  } else {
    const labels = {RETRIEVAL_ONLY: "已找到以下原文。这个模式不调用模型。", NO_RETRIEVAL_MATCH: "当前章节没有检索到匹配片段，可以换一种表述或扩大资料范围。", MODEL_FAILED: "讲解服务暂时不可用，仍可阅读下面的原文。", CITATION_VALIDATION_FAILED: "模型回复的引用未通过检查，本次讲解未展示。你可以先阅读原文。"};
    section.append(node("p", labels[result.status] || "本次处理未完成。", "result-status"));
  }
  if (result.evidence && result.evidence.length) {
    section.append(node("div", "查看教材依据", "evidence-title"));
    result.evidence.forEach(item => {
      const detail = node("details", undefined, "evidence");
      detail.append(node("summary", `[${item.evidence_id}] ${item.book} · ${item.section.split(" / ").slice(-1)[0]}`));
      detail.append(node("pre", item.context_text || item.text));
      const link = node("a", `打开原文 · 第 ${item.start_line}–${item.end_line} 行`);
      link.href = item.line_url; link.target = "_blank"; link.rel = "noopener noreferrer";
      detail.append(link); section.append(detail);
    });
  }
  if (result.books_without_match && result.books_without_match.length) section.append(node("p", `未匹配到依据的教材：${result.books_without_match.join("、")}`, "missing"));
  section.append(node("p", "每次问题独立检索教材。引用存在不等于结论一定被原文支持。", "result-meta"));
  $("results").append(section);
}

$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  if (!user) { showAuth(); return; }
  const question = $("question").value.trim();
  if (!question) return;
  busy = true; $("send-button").disabled = true; $("send-label").textContent = "正在学习…";
  $("ask-form").setAttribute("aria-busy", "true");
  notice($("mode-select").value === "explain" ? "正在查找教材依据并生成讲解，请稍候。" : "正在查找教材原文…");
  try {
    if (!currentChat) { const chat = await api("/api/chats", "POST", {title: question.slice(0, 40)}); currentChat = chat.id; }
    const result = await api("/api/ask", "POST", {chat_id: currentChat, request_key: crypto.randomUUID(), question, book: $("book-select").value || null, explain: $("mode-select").value === "explain"});
    renderResult(question, result); user.quota = result.quota; updateAccount(); await refreshChats(); notice();
    $("question").value = ""; updateQuestionCount();
  } catch (error) { notice(error.message); }
  finally { busy = false; $("send-button").disabled = false; $("send-label").textContent = "提问"; $("ask-form").setAttribute("aria-busy", "false"); }
});

$("new-chat").addEventListener("click", () => { if (!user) { showAuth(); return; } if (busy) return; currentChat = null; $("results").replaceChildren(); setHistoryOpen(false); refreshChats().catch(error => notice(error.message)); $("question").focus(); });
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
    $("password").value = ""; currentChat = null; $("results").replaceChildren();
    $("auth-dialog").close(); updateAccount(); await refreshChats(); notice("已进入你的学习空间。输入问题即可开始。");
  } catch (error) { $("auth-error").textContent = error.message; }
  finally { $("auth-submit").disabled = false; }
});
$("account-button").addEventListener("click", async () => {
  if (!user) { showAuth(); return; }
  if (busy) return;
  try { await api("/api/logout", "POST", {}); user = null; currentChat = null; $("results").replaceChildren(); updateAccount(); await refreshChats(); notice("已退出账号。"); }
  catch (error) { notice(error.message); }
});

async function initialize() {
  try {
    const library = await api("/api/library");
    libraryBooks = library.books;
    library.books.forEach(book => { const label = book.book === "Hello-Agents" ? "count-b" : "count-a"; $(label).textContent = `${book.documents} 篇资料`; });
    $("library-button").disabled = false;
  } catch (error) { notice(error.message); }
  try { user = await api("/api/me"); updateAccount(); await refreshChats(); } catch { user = null; updateAccount(); }
}
initialize();
