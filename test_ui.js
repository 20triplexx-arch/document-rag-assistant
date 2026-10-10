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
  addEventListener(name, callback) { this.events[name] = callback; }
  async trigger(name) { return this.events[name]({preventDefault() {}}); }
  focus() { this.focused = true; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

async function setup({modelFailure = false, savedChats = []} = {}) {
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const books = ["awesome-agentic-ai-zh", "Hello-Agents"].map(book => {
    const card = new Element("button"); card.dataset.book = book; return card;
  });
  const suggestions = [...html.matchAll(/data-question="([^"]+)"/g)].map(match => {
    const button = new Element("button"); button.dataset.question = match[1]; return button;
  });
  const sidebar = new Element("aside");
  ids.get("mode-select").value = "explain";
  const library = {chunks: 9, books: books.map((card, index) => ({
    book: card.dataset.book, documents: 2, chunks: index ? 5 : 4,
    license: "TEST", license_url: "https://example.test/license",
    chapters: [
      {title: index ? "第七章：RAG" : "Memory", path: index ? "docs/chapter7/RAG.md" : "stages/memory.md", chunks: 2, source_url: "https://example.test/source"},
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
      querySelectorAll: selector => selector === ".book-card" ? books : suggestions,
    },
    window: {confirm: () => false}, crypto: {randomUUID: () => "test-request-key"},
    fetch: async (url, options) => {
      calls.push({url, options});
      if (url === "/api/ask" && modelFailure) throw new Error("测试网络故障");
      const ok = url !== "/api/me";
      const payload = url === "/api/library" ? library : url === "/api/chats" ? savedChats : url === "/api/ask" ? result : {detail: "请登录"};
      return {ok, json: async () => payload};
    },
  });
  vm.runInContext(script.replace(/initialize\(\);\s*$/, "globalThis.initialization = initialize();"), context);
  await context.initialization;
  const asUser = () => vm.runInContext('user = {username: "test-user", role: "learner", csrf: "test-csrf", quota: {used: 0, limit: 20}}; currentChat = "existing-test-chat";', context);
  return {ids, books, suggestions, sidebar, calls, context, asUser};
}

test("每个 JS 固定 DOM 入口存在且 ID 唯一", () => {
  const identifiers = [...html.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(identifiers.length, new Set(identifiers).size);
  for (const match of script.matchAll(/\$\("([^"]+)"\)/g)) assert.ok(identifiers.includes(match[1]), match[1]);
  assert.ok(!/\bon\w+\s*=|<style\b/.test(html), "保留禁止内联脚本和样式的 CSP");
});
test("教材篇数来自接口，不再展示首页统计，匿名管理入口隐藏", async () => {
  const {ids, calls} = await setup();
  assert.equal(ids.get("count-a").textContent, "2 篇资料");
  assert.equal(ids.get("count-b").textContent, "2 篇资料");
  assert.ok(!ids.has("total-books"));
  assert.ok(!ids.has("total-documents"));
  assert.ok(!ids.has("total-chunks"));
  assert.equal(ids.get("admin-button").hidden, true);
  assert.equal(ids.get("library-button").disabled, false);
  assert.ok(calls.every(call => call.options.method === "GET"));
});
test("选书同步下拉框和无障碍状态，重复点击恢复两本", async () => {
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
