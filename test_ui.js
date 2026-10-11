"use strict";
// 离线交互单元测试，不启动浏览器、不写账号数据库、不调用模型。
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const html = fs.readFileSync(path.join(__dirname, "static/index.html"), "utf8");
const script = fs.readFileSync(path.join(__dirname, "static/app.js"), "utf8");

class Element {
  constructor(tag = "div") {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {};
    this.value = ""; this.content = ""; this.events = {}; this.classes = new Set();
    this.classList = {toggle: (name, value) => {
      const next = value === undefined ? !this.classes.has(name) : value;
      if (next) this.classes.add(name); else this.classes.delete(name);
      return next;
    }};
  }
  set textContent(value) { this.content = String(value); this.children = []; }
  get textContent() { return this.content + this.children.map(child => child.textContent).join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.content = ""; }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  querySelector(selector) { return this.children.find(child => selector.startsWith(".") ? child.className === selector.slice(1) : child.tagName === selector); }
  addEventListener(name, callback) { this.events[name] = callback; }
  async trigger(name) { return this.events[name]({preventDefault() {}}); }
  focus() { this.focused = true; }
  scrollIntoView(options) { this.scrolled = true; this.scrollOptions = options; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

async function setup({modelFailure = false, savedChats = [], expanded = false, cases = false, fetchHook} = {}) {
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const bookIds = ["awesome-agentic-ai-zh", "Hello-Agents", ...(expanded || cases ? ["microsoft-ai-agents", "huggingface-agents"] : []), ...(cases ? ["awesome-llm-apps-cases"] : [])];
  const suggestions = [...html.matchAll(/data-question="([^"]+)"/g)].map(match => {
    const button = new Element("button"); button.dataset.question = match[1]; return button;
  });
  const sidebar = new Element("aside");
  ids.get("mode-select").value = "explain";
  const library = {chunks: 9, books: bookIds.map((book, index) => ({
    book, display_name: ["Agentic AI 学习路线", "Hello-Agents", "Microsoft 课程", "Hugging Face 课程", "GitHub 实战案例"][index], documents: 2, chunks: index ? 5 : 4,
    kind: index === 4 ? "case_collection" : "course",
    license: index === 3 ? "Apache-2.0" : "TEST", license_url: "https://example.test/license",
    chapters: [
      {title: index ? "第七章：RAG" : "Memory", path: index ? "docs/chapter7/RAG.md" : "stages/memory.md", language: index >= 3 ? "en" : "zh-CN", chunks: 2, source_url: "https://example.test/source",
        topics: index === 4 ? ["混合检索", "重排"] : [], implementation_links: index === 4 ? [{path: "examples/main.py", url: "https://github.com/example/cases/blob/" + "a".repeat(40) + "/examples/main.py"}] : []},
      {title: "<img src=x onerror=alert(1)>", path: "README.md", chunks: 2, source_url: "https://example.test/source"},
    ],
  }))};
  const calls = [];
  const result = {status: "RETRIEVAL_ONLY", quote_verified: false, quota: {used: 1, limit: 20}, evidence: [
    {evidence_id: "E1", book: "Hello-Agents", section: "教材 / RAG", context_text: "<script>危险文本必须作为文字显示</script>", start_line: 1, end_line: 2, line_url: "https://example.test/source#L1-L2"},
  ]};
  const context = vm.createContext({
    document: {
      getElementById: id => ids.get(id), createElement: tag => new Element(tag),
      createElementNS: (namespace, tag) => new Element(tag),
      querySelector: selector => selector === ".sidebar" ? sidebar : null,
      querySelectorAll: selector => selector === ".book-card" ? ids.get("book-grid").children : suggestions,
    },
    window: {confirm: () => false}, crypto: {randomUUID: () => "test-request-key"},
    fetch: async (url, options) => {
      calls.push({url, options});
      if (fetchHook) { const response = await fetchHook(url, options); if (response) return response; }
      if (url === "/api/ask" && modelFailure) throw new Error("测试网络故障");
      const ok = url !== "/api/me";
      const payload = url === "/api/library" ? library : url === "/api/chats" ? savedChats : url === "/api/ask" ? result : {detail: "请登录"};
      return {ok, json: async () => payload};
    },
  });
  vm.runInContext(script.replace(/initialize\(\);\s*$/, "globalThis.initialization = initialize();"), context);
  await context.initialization;
  const asUser = () => vm.runInContext('user = {username: "test-user", role: "learner", csrf: "test-csrf", quota: {used: 0, limit: 20}}; currentChat = "existing-test-chat";', context);
  return {ids, books: ids.get("book-grid").children, suggestions, sidebar, calls, context, asUser, result};
}

test("每个 JS 固定 DOM 入口存在且 ID 唯一", () => {
  const identifiers = [...html.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(identifiers.length, new Set(identifiers).size);
  for (const match of script.matchAll(/\$\("([^"]+)"\)/g)) assert.ok(identifiers.includes(match[1]), match[1]);
  assert.ok(!/\bon\w+\s*=|<style\b/.test(html), "保留禁止内联脚本和样式的 CSP");
});
test("教材篇数来自接口，不再展示首页统计，匿名管理入口隐藏", async () => {
  const {ids, books, calls} = await setup();
  assert.ok(books.every(book => book.textContent.includes("2 篇资料")));
  assert.ok(!ids.has("total-books"));
  assert.ok(!ids.has("total-documents"));
  assert.ok(!ids.has("total-chunks"));
  assert.equal(ids.get("admin-button").hidden, true);
  assert.equal(ids.get("library-button").disabled, false);
  assert.ok(calls.every(call => call.options.method === "GET"));
});
test("选书同步下拉框和无障碍状态，重复点击恢复全部", async () => {
  const {ids, books} = await setup();
  await books[1].trigger("click");
  assert.equal(ids.get("book-select").value, "Hello-Agents");
  assert.equal(books[1].getAttribute("aria-pressed"), "true");
  assert.equal(books[0].getAttribute("aria-pressed"), "false");
  assert.equal(ids.get("ask-form").classes.has("single-book"), true);
  await books[1].trigger("click");
  assert.equal(ids.get("book-select").value, "");
  assert.equal(books[1].getAttribute("aria-pressed"), "false");
  assert.equal(ids.get("ask-form").classes.has("single-book"), false);
});
test("四套教材按接口顺序生成卡片与下拉框，展示许可和英文补缺", async () => {
  const {ids, books} = await setup({expanded: true});
  assert.deepEqual(books.map(card => card.dataset.book), ["awesome-agentic-ai-zh", "Hello-Agents", "microsoft-ai-agents", "huggingface-agents"]);
  assert.equal(ids.get("book-select").children.length, 5);
  assert.equal(ids.get("book-select").children[0].textContent, "全部教材");
  assert.equal(ids.get("book-select").value, "");
  await books[3].trigger("click");
  assert.equal(ids.get("book-select").value, "huggingface-agents");
  ids.get("book-select").value = "microsoft-ai-agents";
  await ids.get("book-select").trigger("change");
  assert.equal(books[2].getAttribute("aria-pressed"), "true");
  assert.equal(books[3].getAttribute("aria-pressed"), "false");
  ids.get("library-search").value = "Hugging Face";
  await ids.get("library-search").trigger("input");
  assert.match(ids.get("library-list").textContent, /Apache-2.0/);
  assert.match(ids.get("library-list").textContent, /英文/);
  assert.equal(ids.get("library-search-count").textContent, "2 篇资料匹配");
});
test("点击案例卡片直接打开案例目录、设置范围，并链接固定版本实现文件", async () => {
  const {ids, books} = await setup({cases: true});
  assert.equal(books.length, 5);
  await books[4].trigger("click");
  assert.equal(ids.get("book-select").value, "awesome-llm-apps-cases");
  assert.match(books[4].textContent, /GitHub 实战案例/);
  assert.equal(ids.get("library-dialog").open, true);
  assert.equal(ids.get("library-title").textContent, "实战案例");
  assert.equal(ids.get("library-list").children.length, 1);
  assert.equal(ids.get("library-search-count").textContent, "2 个案例已收录");
  ids.get("library-search").value = "重排";
  await ids.get("library-search").trigger("input");
  assert.equal(ids.get("library-search-count").textContent, "1 个案例匹配");
  assert.match(ids.get("library-list").textContent, /英文/);
  assert.match(ids.get("library-list").textContent, /实现：main.py/);
  const flatten = element => [element, ...element.children.flatMap(flatten)];
  const code = flatten(ids.get("library-list")).find(e => e.tagName === "a" && e.textContent === "实现：main.py ");
  assert.match(code.href, /\/blob\/a{40}\/examples\/main.py/);
  await ids.get("close-library").trigger("click");
  await books[4].trigger("click");
  assert.equal(ids.get("library-dialog").open, true);
  assert.equal(ids.get("book-select").value, "awesome-llm-apps-cases");
  assert.equal(ids.get("library-search").value, "");
});
test("案例快捷入口支持匿名浏览、不改写问题或范围，完整目录恢复全部资料", async () => {
  const {ids, calls} = await setup({cases: true});
  ids.get("question").value = "保留正在输入的问题";
  assert.equal(ids.get("cases-button").disabled, false);
  await ids.get("cases-button").trigger("click");
  assert.equal(ids.get("library-dialog").open, true);
  assert.equal(ids.get("library-search-count").textContent, "2 个案例已收录");
  assert.equal(ids.get("question").value, "保留正在输入的问题");
  assert.equal(ids.get("book-select").value, "");
  ids.get("library-search").value = "Memory";
  await ids.get("library-search").trigger("input");
  assert.equal(ids.get("library-search-count").textContent, "0 个案例匹配");
  assert.match(ids.get("library-list").textContent, /没有找到相关案例/);
  await ids.get("close-library").trigger("click");
  await ids.get("library-button").trigger("click");
  assert.equal(ids.get("library-title").textContent, "资料目录");
  assert.equal(ids.get("library-search-count").textContent, "10 篇资料已收录");
  assert.equal(ids.get("library-list").children.length, 5);
  assert.equal(ids.get("library-search").value, "");
  assert.ok(calls.every(call => call.options.method === "GET"));
});
test("旧课程语料没有案例时禁用案例入口", async () => {
  const {ids} = await setup({expanded: true});
  assert.equal(ids.get("cases-button").disabled, true);
});
test("目录按标题或路径搜索，零结果清晰，查询不发网络请求", async () => {
  const {ids, calls} = await setup();
  await ids.get("library-button").trigger("click");
  assert.equal(ids.get("library-dialog").open, true);
  assert.equal(ids.get("library-search-count").textContent, "4 篇资料已收录");
  ids.get("library-search").value = "rAg";
  await ids.get("library-search").trigger("input");
  assert.equal(ids.get("library-search-count").textContent, "1 篇资料匹配");
  ids.get("library-search").value = "stages/";
  await ids.get("library-search").trigger("input");
  assert.equal(ids.get("library-search-count").textContent, "1 篇资料匹配");
  ids.get("library-search").value = "不存在的章节";
  await ids.get("library-search").trigger("input");
  assert.equal(ids.get("library-search-count").textContent, "0 篇资料匹配");
  assert.match(ids.get("library-list").textContent, /没有找到/);
  assert.equal(calls.length, 2);
});
test("建议填入问题并更新字数，手机历史可展开收起", async () => {
  const {ids, suggestions, sidebar} = await setup();
  await suggestions[0].trigger("click");
  assert.equal(ids.get("question").value, suggestions[0].dataset.question);
  assert.equal(ids.get("question-count").textContent, `${suggestions[0].dataset.question.length} / 500`);
  await ids.get("history-toggle").trigger("click");
  assert.equal(ids.get("history-toggle").getAttribute("aria-expanded"), "true");
  assert.equal(sidebar.classes.has("history-open"), true);
  await ids.get("history-toggle").trigger("click");
  assert.equal(ids.get("history-toggle").getAttribute("aria-expanded"), "false");
});
test("未登录不创建讨论或调用模型", async () => {
  const {ids, calls} = await setup();
  ids.get("question").value = "RAG";
  await ids.get("ask-form").trigger("submit");
  assert.equal(ids.get("auth-dialog").open, true);
  assert.ok(!calls.some(call => call.options.method === "POST"));
});
test("检索结果以文字渲染、引用保留，完成后按钮结构和字数恢复", async () => {
  const {ids, calls, asUser} = await setup();
  asUser(); ids.get("question").value = "RAG 是什么？"; ids.get("mode-select").value = "retrieve";
  const arrow = new Element("span"); ids.get("send-button").append(ids.get("send-label"), arrow);
  await ids.get("ask-form").trigger("submit");
  const request = JSON.parse(calls.find(call => call.url === "/api/ask").options.body);
  assert.equal(request.explain, false);
  assert.match(ids.get("results").textContent, /<script>危险文本/);
  const detail = ids.get("results").children[0].children.find(child => child.tagName === "details");
  assert.equal(detail.children[1].tagName, "pre");
  assert.equal(detail.children[2].href, "https://example.test/source#L1-L2");
  assert.equal(ids.get("send-button").children[1], arrow);
  assert.equal(ids.get("send-label").textContent, "提问");
  assert.equal(ids.get("question-count").textContent, "0 / 500");
  assert.equal(ids.get("ask-form").getAttribute("aria-busy"), "false");
});
test("请求失败不清空问题，加载按钮恢复并展示错误", async () => {
  const {ids, asUser} = await setup({modelFailure: true});
  asUser(); ids.get("question").value = "保留这个问题";
  await ids.get("ask-form").trigger("submit");
  assert.equal(ids.get("question").value, "保留这个问题");
  assert.equal(ids.get("send-button").disabled, false);
  assert.equal(ids.get("send-label").textContent, "提问");
  assert.match(ids.get("notice").textContent, /测试网络故障/);
});

test("历史讨论删除图标用 SVG，取消确认不发删除请求", async () => {
  const {ids, calls, asUser, context} = await setup({savedChats: [{id: "saved", title: "已有讨论"}]});
  asUser(); await vm.runInContext("refreshChats()", context);
  const remove = ids.get("chat-list").children[0].children[1];
  assert.equal(remove.children[0].tagName, "svg");
  assert.equal(remove.children[0].children[0].tagName, "path");
  assert.equal(remove.getAttribute("aria-label"), "删除讨论：已有讨论");
  await remove.trigger("click");
  assert.ok(!calls.some(call => call.options.method === "DELETE"));
});

test("精简的注册登录切换保持密码自动填充类型", async () => {
  const {ids} = await setup();
  await ids.get("auth-toggle").trigger("click");
  assert.equal(ids.get("auth-title").textContent, "创建账号");
  assert.equal(ids.get("auth-submit").textContent, "注册");
  assert.equal(ids.get("password").autocomplete, "new-password");
  await ids.get("auth-toggle").trigger("click");
  assert.equal(ids.get("auth-title").textContent, "登录");
  assert.equal(ids.get("auth-toggle").textContent, "创建账号");
  assert.equal(ids.get("password").autocomplete, "current-password");
});

test("回答切换为阅读状态，新讨论恢复同一个表单与输入焦点", async () => {
  const {ids, asUser} = await setup();
  const form = ids.get("ask-form");
  asUser(); ids.get("question").value = "工具调用";
  await form.trigger("submit");
  assert.equal(ids.get("workspace").classes.has("has-results"), true);
  await ids.get("new-chat").trigger("click");
  assert.equal(ids.get("workspace").classes.has("has-results"), false);
  assert.equal(ids.get("results").children.length, 0);
  assert.equal(ids.get("ask-form"), form);
  assert.equal(ids.get("question").focused, true);
});

test("两轮重复 E1 引用分别展开本轮依据并定位焦点", async () => {
  const {ids, context, result} = await setup();
  result.answer = {claims: [{text: "第一轮说明", evidence_id: "E1", quote: "危险文本必须作为文字显示"}], missing_information: ""};
  context.fixture = result;
  vm.runInContext('renderResult("第一轮", fixture); renderResult("第二轮", fixture);', context);
  const [first, second] = ids.get("results").children;
  const reference = article => article.children.find(e => e.className === "claim").children.find(e => e.tagName === "button");
  const evidence = article => article.children.find(e => e.tagName === "details");
  assert.notEqual(evidence(first).id, evidence(second).id);
  assert.equal(reference(second).getAttribute("aria-controls"), evidence(second).id);
  await reference(second).trigger("click");
  assert.equal(evidence(second).open, true);
  assert.equal(evidence(first).open, undefined);
  assert.equal(evidence(second).children[0].focused, true);
  await reference(first).trigger("click");
  assert.equal(evidence(first).open, true);
  assert.equal(evidence(first).children[0].scrolled, true);
  assert.equal(evidence(first).children[0].scrollOptions.block, "start");
});

test("加载锁定本轮输入及范围，重复提交不重试，失败恢复后可重发", async () => {
  let rejectRequest, started;
  const requested = new Promise(resolve => { started = resolve; });
  const {ids, books, calls, asUser} = await setup({fetchHook: async url => {
    if (url === "/api/ask") { started(); return new Promise((resolve, reject) => { rejectRequest = reject; }); }
  }});
  asUser(); await books[1].trigger("click"); ids.get("question").value = "保留输入";
  const pending = ids.get("ask-form").trigger("submit"); await requested;
  assert.equal(ids.get("send-label").textContent, "生成中");
  assert.equal(ids.get("question").readOnly, true);
  assert.equal(ids.get("book-select").disabled, true);
  assert.equal(ids.get("mode-select").disabled, true);
  await books[0].trigger("click"); await ids.get("ask-form").trigger("submit");
  assert.equal(ids.get("book-select").value, "Hello-Agents");
  assert.equal(calls.filter(call => call.url === "/api/ask").length, 1);
  rejectRequest(new Error("离线失败")); await pending;
  assert.equal(ids.get("question").value, "保留输入");
  assert.equal(ids.get("question").readOnly, false);
  assert.equal(ids.get("mode-select").disabled, false);
  assert.equal(ids.get("notice").dataset.tone, "error");
});

test("登录成功进入私人历史，失败保留用户名并显示错误", async () => {
  const account = {username: "offline-user", role: "learner", csrf: "csrf", quota: {used: 0, limit: 20}};
  const {ids, calls} = await setup({fetchHook: async url => url === "/api/login" ? {ok: true, json: async () => account} : null});
  ids.get("username").value = " offline-user "; ids.get("password").value = "temporary-pass";
  await ids.get("auth-form").trigger("submit");
  assert.match(ids.get("account-button").textContent, /offline-user/);
  assert.equal(ids.get("password").value, "");
  assert.equal(ids.get("auth-dialog").open, false);
  assert.equal(JSON.parse(calls.find(call => call.url === "/api/login").options.body).username, "offline-user");
  const failed = await setup({fetchHook: async url => url === "/api/login" ? {ok: false, json: async () => ({detail: "账号或密码不正确"})} : null});
  failed.ids.get("username").value = "offline-user";
  await failed.ids.get("auth-form").trigger("submit");
  assert.equal(failed.ids.get("username").value, "offline-user");
  assert.match(failed.ids.get("auth-error").textContent, /不正确/);
});

test("模型或引文检查失败仍展示依据并保留问题，零匹配展示空结果", async () => {
  for (const status of ["MODEL_FAILED", "CITATION_VALIDATION_FAILED"]) {
    const {ids, asUser, result, calls} = await setup();
    result.status = status; asUser(); ids.get("question").value = "保留待讲解问题";
    await ids.get("ask-form").trigger("submit");
    assert.equal(ids.get("question").value, "保留待讲解问题");
    assert.match(ids.get("results").textContent, /原文/);
    assert.equal(calls.filter(call => call.url === "/api/ask").length, 1);
  }
  const {ids, context, result} = await setup();
  result.status = "NO_RETRIEVAL_MATCH"; result.evidence = []; context.fixture = result;
  vm.runInContext('renderResult("资料不足", fixture)', context);
  assert.match(ids.get("results").textContent, /没有检索到匹配片段/);
});
