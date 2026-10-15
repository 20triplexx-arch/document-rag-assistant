"use strict";
// 离线交互单元测试，不启动浏览器、不写账号数据库、不调用模型。
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {TextEncoder, TextDecoder} = require("node:util");
const html = fs.readFileSync(path.join(__dirname, "static/index.html"), "utf8");
const script = ["answer.js", "stream.js", "app.js"].map(name => fs.readFileSync(path.join(__dirname, "static", name), "utf8")).join("\n");

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
  append(...children) { children.forEach(child => { child.owner = this; }); this.children.push(...children); }
  remove() { if (this.owner) this.owner.children = this.owner.children.filter(child => child !== this); }
  replaceChildren(...children) { this.children = []; this.content = ""; this.append(...children); }
  setAttribute(name, value) { this.attributes[name] = value; }
  getAttribute(name) { return this.attributes[name]; }
  querySelector(selector) {
    for (const child of this.children) {
      if (selector.startsWith(".") ? child.className === selector.slice(1) : child.tagName === selector) return child;
      const nested = child.querySelector(selector); if (nested) return nested;
    }
  }
  addEventListener(name, callback) { this.events[name] = callback; }
  async trigger(name) { return this.events[name]({preventDefault() {}}); }
  focus() { this.focused = true; }
  scrollIntoView(options) { this.scrolled = true; this.scrollOptions = options; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

async function setup({modelFailure = false, savedChats = [], expanded = false, cases = false, streaming = false, fetchHook} = {}) {
  const ids = new Map([...html.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Element()]));
  const bookIds = ["awesome-agentic-ai-zh", "Hello-Agents", ...(expanded || cases ? ["microsoft-ai-agents", "huggingface-agents"] : []), ...(cases ? ["awesome-llm-apps-cases"] : [])];
  const suggestions = [...html.matchAll(/data-question="([^"]+)"/g)].map(match => {
    const button = new Element("button"); button.dataset.question = match[1]; return button;
  });
  const sidebar = new Element("aside");
  ids.get("mode-select").value = "explain";
  ids.get("style-select").value = "auto";
  ids.get("use-history").checked = true;
  const library = {chunks: 9, adaptive_answers:true, streaming_answers:streaming, model:"deepseek-flash", default_model:"deepseek-flash",
    models:[{id:"deepseek-flash",display_name:"DeepSeek Flash",is_default:true},
            {id:"deepseek-v4-pro",display_name:"DeepSeek Pro",description:"费用较高",is_default:false}],
    books: bookIds.map((book, index) => ({
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
    window: {confirm: () => false}, crypto: {randomUUID: () => "test-request-key"}, TextDecoder,
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

function streamResponse(events, {truncate = false, crlf = false} = {}) {
  let text = events.map(event => `data: ${JSON.stringify(event)}\n\n`).join("");
  if (crlf) text = text.replaceAll("\n", "\r\n");
  if (truncate) text = text.slice(0, -5);
  const bytes = new TextEncoder().encode(text); let position = 0;
  const reader = {read:async () => position < bytes.length ? {done:false,value:bytes.slice(position,++position)} : {done:true},
    cancel:async()=>{},releaseLock:()=>{}};
  return {ok:true,body:{getReader:()=>reader}};
}

test("流式逐字节解码中文和转义，只有最终结果才完成，不重试截断流", async () => {
  const {context} = await setup();
  context.response = streamResponse([{type:"progress",stage:"generation"},
    {type:"block",block:{text:'中文与引号"、反斜线\\、换行\n、括号 } ]'}},
    {type:"result",result:{status:"CITED_DRAFT"}}],{crlf:true});
  context.seen=[];
  const result = await vm.runInContext("readAnswerStream(response, event => seen.push(event))",context);
  assert.equal(result.status,"CITED_DRAFT");assert.equal(context.seen.length,3);
  assert.equal(context.seen[1].block.text,'中文与引号"、反斜线\\、换行\n、括号 } ]');
  context.response=streamResponse([{type:"result",result:{status:"CITED_DRAFT"}}],{truncate:true});
  await assert.rejects(vm.runInContext("readAnswerStream(response, () => {})",context),/连接已中断/);
});

test("流式按块追加且完成时保留同一正文节点，携带CSRF并只提交一次", async () => {
  let fixture;
  const state=await setup({streaming:true,fetchHook:async (url,options) => url==="/api/ask/stream"
    ? streamResponse([{type:"evidence",pack:{evidence:fixture.evidence}},
      ...fixture.answer.blocks.map((block,index)=>({type:"block",index,block})),{type:"result",result:fixture}]) : undefined});
  fixture=state.result;fixture.status="CITED_DRAFT";fixture.quote_verified=true;
  fixture.answer={schema_version:2,status:"answered",missing_information:"",blocks:[{type:"paragraph",text:"已核对的中文正文。",references:[{evidence_id:"E1",quote:"危险文本必须作为文字显示"}]}]};
  state.asUser();state.ids.get("question").value="工具如何工作？";
  await state.ids.get("ask-form").trigger("submit");
  const article=state.ids.get("results").children[0];
  assert.equal(state.ids.get("results").children.length,1);
  assert.equal(article.querySelector(".claim-text").textContent,"已核对的中文正文。");
  assert.equal(article.querySelector(".badge").textContent,"引用已核对");
  assert.equal(state.ids.get("question").value,"");
  const requests=state.calls.filter(call=>call.url.includes("/api/ask"));assert.equal(requests.length,1);
  assert.equal(requests[0].options.headers["X-CSRF-Token"],"test-csrf");
  assert.equal(requests[0].url,"/api/ask/stream");
});

test("最终校验失败撤回流式预览，保留证据和输入，不回退追加模型请求", async () => {
  let fixture;
  const state=await setup({streaming:true,fetchHook:async url=>url==="/api/ask/stream"
    ? streamResponse([{type:"evidence",pack:{evidence:fixture.evidence}},
      {type:"block",block:{type:"paragraph",text:"待最终核对的预览内容",references:[]}},
      {type:"result",result:fixture}]) : undefined});
  fixture=state.result;fixture.status="CITATION_VALIDATION_FAILED";fixture.failure_stage="response_schema";fixture.answer=null;
  state.asUser();state.ids.get("question").value="保留我的问题";
  await state.ids.get("ask-form").trigger("submit");
  assert.equal(state.ids.get("results").children.length,1);
  assert.ok(!state.ids.get("results").textContent.includes("待最终核对的预览内容"));
  assert.ok(state.ids.get("results").querySelector(".evidence"));
  assert.equal(state.ids.get("question").value,"保留我的问题");
  assert.equal(state.calls.filter(call=>call.url.includes("/api/ask")).length,1);
  assert.equal(state.ids.get("send-button").disabled,false);
});

test("每个 JS 固定 DOM 入口存在且 ID 唯一", () => {
  const identifiers = [...html.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
  assert.equal(identifiers.length, new Set(identifiers).size);
  for (const match of script.matchAll(/\$\("([^"]+)"\)/g)) assert.ok(identifiers.includes(match[1]), match[1]);
  assert.ok(!/\bon\w+\s*=|<style\b/.test(html), "保留禁止内联脚本和样式的 CSP");
});

test("模型选项来自接口、切换后提交并保留选择，原文模式禁用模型", async () => {
  const {ids, calls, asUser, context} = await setup();
  assert.equal(ids.get("model-select").children.length, 2);
  assert.equal(ids.get("model-select").value, "deepseek-flash");
  assert.match(ids.get("model-select").children[1].textContent, /费用较高/);
  ids.get("model-select").value = "deepseek-v4-pro";
  asUser(); ids.get("question").value = "RAG 工作机制";
  await ids.get("ask-form").trigger("submit");
  assert.equal(JSON.parse(calls.find(c=>c.url==="/api/ask").options.body).model,"deepseek-v4-pro");
  assert.equal(ids.get("model-select").value,"deepseek-v4-pro");
  ids.get("mode-select").value="retrieve";
  await ids.get("mode-select").trigger("change");
  assert.equal(ids.get("model-select").disabled,true);
  ids.get("mode-select").value="explain";
  await ids.get("mode-select").trigger("change");
  assert.equal(ids.get("model-select").disabled,false);
  vm.runInContext("renderModels({model:'legacy-model'})",context);
  assert.equal(ids.get("model-select").value,"legacy-model");
  ids.get("question").value="旧服务检索问题";
  await ids.get("ask-form").trigger("submit");
  assert.equal(Object.hasOwn(JSON.parse(calls.filter(c=>c.url==="/api/ask").at(-1).options.body),"model"),false);
});

test("回答标明本次实际模型，原文检索和旧历史显示兼容", async () => {
  const {ids, context, result} = await setup();
  result.selected_model="deepseek-v4-pro";result.model_calls=1;result.usage={model:"deepseek-v4-pro"};
  context.modelResult=result;
  vm.runInContext("renderResult('第一轮',modelResult)",context);
  assert.equal(ids.get("results").children[0].querySelector(".result-model").textContent,"模型：DeepSeek Pro");
  result.model_calls=0;
  vm.runInContext("renderResult('只查原文',modelResult)",context);
  assert.equal(ids.get("results").children[1].querySelector(".result-model"),undefined);
});

test("讲解重点与上下文开关提交到接口，只查原文禁用讲解选项", async () => {
  const {ids, calls, asUser} = await setup();
  asUser();
  ids.get("question").value = "RAG 实战步骤";
  ids.get("style-select").value = "practice";
  ids.get("use-history").checked = false;
  await ids.get("ask-form").trigger("submit");
  const request = JSON.parse(calls.find(call => call.url === "/api/ask").options.body);
  assert.equal(request.explanation_style, "practice");
  assert.equal(request.use_history, false);
  ids.get("mode-select").value = "retrieve";
  await ids.get("mode-select").trigger("change");
  assert.equal(ids.get("style-select").disabled, true);
});

test("继续学习按钮只准备问题，保留现有草稿，不自动调用模型", async () => {
  const {ids, context, result, calls} = await setup();
  result.answer = {claims:[{text:"工作机制", evidence_id:"E1", quote:"危险文本必须作为文字显示"}], missing_information:""};
  result.context_turns = 1;
  context.followResult = result;
  vm.runInContext("renderResult('RAG 和 Memory 的区别', followResult)", context);
  const actions = ids.get("results").children[0].querySelector(".followup-actions");
  assert.equal(actions.children.length, 2);
  const before = calls.length;
  await actions.children[1].trigger("click");
  assert.match(ids.get("question").value, /RAG 和 Memory/);
  assert.match(ids.get("question").value, /失败/);
  assert.equal(ids.get("style-select").value, "auto");
  assert.equal(ids.get("use-history").checked, true);
  assert.equal(calls.length, before);
  ids.get("question").value = "正在编写的私人问题";
  await actions.children[0].trigger("click");
  assert.equal(ids.get("question").value, "正在编写的私人问题");
});

test("新版段落多来源、代码缩进与表格安全显示，引用只打开本轮", async () => {
  const {ids, context, result, calls} = await setup();
  result.answer = {schema_version:2,status:"answered",missing_information:"",blocks:[
    {type:"paragraph",text:"<img src=x onerror=alert(1)>作为普通文字",references:[{evidence_id:"E1",quote:"危险文本必须作为文字显示"},{evidence_id:"E2",quote:"第二份证据里的逐字摘录内容"}]},
    {type:"code",origin:"source",language:"python",code:"def f():\n    return '<script>'",references:[{evidence_id:"E1",quote:"危险文本必须作为文字显示"}]},
    {type:"table",columns:["对象","机制"],rows:[{cells:["工具","<script>保留文字</script>"],references:[{evidence_id:"E2",quote:"第二份证据里的逐字摘录内容"}]}]},
  ]};
  result.evidence.push({...result.evidence[0],evidence_id:"E2",context_text:"第二份证据里的逐字摘录内容"});
  result.followups=[{label:"检查工具结果",question:"工具返回结果后怎样核对？"},{label:"检查记忆范围",question:"怎样隔离用户记忆？"},{label:"应截断",question:"不显示"}];
  context.newResult=result;vm.runInContext("renderResult('工具和记忆',newResult)",context);
  const article=ids.get("results").children[0];
  assert.equal(article.querySelector("code").textContent,"def f():\n    return '<script>'");
  assert.equal(article.querySelector("img"),undefined);assert.equal(article.querySelector("script"),undefined);
  assert.equal(article.querySelector("tbody").children[0].children[1].textContent,"<script>保留文字</script>");
  const paragraph=article.querySelector(".claim");await paragraph.children[2].trigger("click");
  const panel=article.querySelector(".answer-sources");assert.equal(panel.open,true);assert.equal(panel.children[2].open,true);
  assert.equal(panel.children[2].querySelector(".quote").textContent,"第二份证据里的逐字摘录内容");
  const actions=article.querySelector(".followup-actions");assert.equal(actions.children.length,2);const before=calls.length;
  await actions.children[0].trigger("click");assert.equal(ids.get("question").value,"工具返回结果后怎样核对？");assert.equal(calls.length,before);
});

test("缺少追问主题时保留问题，提示恢复且不展示虚构回答", async () => {
  const {ids, asUser, result} = await setup();
  asUser();
  result.status = "CONTEXT_REQUIRED"; result.evidence = [];
  ids.get("question").value = "继续讲";
  await ids.get("ask-form").trigger("submit");
  assert.equal(ids.get("question").value, "继续讲");
  assert.match(ids.get("results").textContent, /请写明/);
  assert.equal(ids.get("use-history").disabled, false);
  assert.equal(ids.get("style-select").disabled, false);
});

test("原文标题去除展示标记但不改写证据正文或执行标签", async () => {
  const {ids, context, result} = await setup();
  result.evidence[0].section = '章节 / <strong>4.4 **Memory** 与 [RAG](./rag.md)</strong>';
  context.headingResult = result;
  vm.runInContext("renderResult('记忆', headingResult)", context);
  const evidence = ids.get("results").children[0].querySelector(".evidence");
  assert.equal(evidence.querySelector("summary").textContent, '[E1] Hello-Agents · 4.4 Memory 与 RAG');
  assert.equal(evidence.querySelector("pre").textContent, result.evidence[0].context_text);
});

test("长输入按 Unicode 字符计数，超过一万字时保留内容且不发请求", async () => {
  const {ids, calls, asUser} = await setup();
  asUser();
  ids.get("question").value = "😀".repeat(10000);
  await ids.get("question").trigger("input");
  assert.equal(ids.get("question-count").textContent, "10000 / 10000");
  ids.get("question").value += "字";
  await ids.get("question").trigger("input");
  const before = calls.length;
  await ids.get("ask-form").trigger("submit");
  assert.equal(calls.length, before);
  assert.match(ids.get("notice").textContent, /10000/);
  assert.equal(Array.from(ids.get("question").value).length, 10001);
});

test("长回答完整显示分节和换行，长问题可展开，旧回答无需标题", async () => {
  const {ids, context, result} = await setup();
  const longText = "机制说明。\n实践步骤。\n".repeat(70);
  result.answer = {claims: Array.from({length: 7}, (_, i) => ({heading: i < 3 ? "工作机制" : "实践边界", text: longText,
    evidence_id: "E1", quote: "危险文本必须作为文字显示"})), missing_information: ""};
  context.longResult = result;
  context.longQuestion = "完整背景。".repeat(200);
  vm.runInContext("renderResult(longQuestion, longResult)", context);
  const exchange = ids.get("results").children[0];
  const body = exchange.querySelector(".answer-body");
  assert.equal(body.children.filter(item => item.className === "answer-heading").length, 2);
  assert.equal(body.children.filter(item => item.className === "claim").length, 7);
  assert.equal(exchange.querySelector(".full-question").querySelector("pre").textContent, context.longQuestion);
  body.children.filter(item => item.className === "claim").forEach(item => {
    assert.equal(item.querySelector(".claim-text").textContent, longText);
    assert.equal(item.querySelector(".claim-excerpt"), undefined);
  });
  delete result.answer.claims[0].heading;
  vm.runInContext("renderResult('旧问题', longResult)", context);
  assert.equal(ids.get("results").children.length, 2);
});

test("新讨论标题截取不破坏 Unicode 字符", async () => {
  const {ids, calls, context, asUser} = await setup({fetchHook: async (url, options) =>
    url === "/api/chats" && options.method === "POST" ? {ok:true,json:async()=>({id:"unicode-chat"})} : undefined});
  asUser();
  vm.runInContext("currentChat = null", context);
  ids.get("question").value = "字".repeat(39) + "😀RAG";
  await ids.get("ask-form").trigger("submit");
  const posted = calls.find(call => call.url === "/api/chats" && call.options.method === "POST");
  assert.equal(JSON.parse(posted.options.body).title, "字".repeat(39) + "😀");
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
  assert.equal(ids.get("question-count").textContent, `${suggestions[0].dataset.question.length} / 10000`);
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
  assert.equal(ids.get("question-count").textContent, "0 / 10000");
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
  const reference = article => article.querySelector(".claim").children.find(e => e.tagName === "button");
  const evidence = article => article.querySelector(".evidence");
  assert.notEqual(evidence(first).id, evidence(second).id);
  assert.equal(reference(second).getAttribute("aria-controls"), evidence(second).id);
  await reference(second).trigger("click");
  assert.equal(evidence(second).open, true);
  assert.equal(second.querySelector(".answer-sources").open, true);
  assert.equal(evidence(second).querySelector(".quote").textContent, result.answer.claims[0].quote);
  assert.equal(evidence(first).open, undefined);
  assert.equal(evidence(second).children[0].focused, true);
  await reference(first).trigger("click");
  assert.equal(evidence(first).open, true);
  assert.equal(evidence(first).children[0].scrolled, true);
  assert.equal(evidence(first).children[0].scrollOptions.block, "start");
});

test("默认自动篇幅，旧服务回退深入，正文列表与原文折叠保持安全", async () => {
  const {ids, context, result} = await setup();
  assert.equal(ids.get("style-select").value, "auto");
  result.answer = {format:"steps", claims:[
    {text:"<script>步骤一仍是文字</script>", evidence_id:"E1", quote:"危险文本必须作为文字显示"},
    {text:"检查执行结果。", evidence_id:"E1", quote:"危险文本必须作为文字显示"},
  ], missing_information:""};
  context.fixture = result;
  vm.runInContext('renderResult("操作", fixture)', context);
  const article = ids.get("results").children[0];
  const list = article.querySelector("ol");
  assert.equal(list.children.length, 2);
  assert.equal(list.children[0].tagName, "li");
  assert.equal(list.children[0].querySelector(".claim-text").textContent, result.answer.claims[0].text);
  assert.equal(article.querySelector(".answer-sources").open, undefined);
  assert.equal(article.querySelector(".quote").hidden, true);
  await list.children[1].querySelector("button").trigger("click");
  assert.equal(article.querySelector(".answer-sources").open, true);
  assert.equal(article.querySelector(".quote").hidden, false);
  result.answer.format = "bullets";
  vm.runInContext('renderResult("比较", fixture)', context);
  assert.equal(ids.get("results").children[1].querySelector("ul").children.length, 2);
  vm.runInContext('renderModels({model:"legacy-model"})', context);
  assert.equal(ids.get("style-select").value, "deep");
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

test("Notebook 显示实际单元位置，资料统计区分文件、单元和片段", async () => {
  const fixture = {chunks:41, source_files:5, notebook_cells:12, models:[], books:[
    {book:"Hello-Agents",display_name:"Hello-Agents",documents:2,source_files:5,notebook_cells:12,chunks:41,
      license:"TEST",license_url:"https://example.test/license",chapters:[]},
  ]};
  const {ids,context,result} = await setup({fetchHook:async url => url === "/api/library" ? {ok:true,json:async()=>fixture} : null});
  assert.match(ids.get("library-coverage").textContent,/5 个文件.*12 个 Notebook 教学单元.*41 个检索片段/);
  result.evidence[0].source_locator={kind:"notebook_cell",cell_index:7,start_line:2,end_line:6};
  result.evidence[0].line_url="https://github.com/example/course/blob/"+"a".repeat(40)+"/lesson.ipynb";
  context.fixture=result;
  vm.runInContext('renderResult("解释 Notebook", fixture)',context);
  const article=ids.get("results").children[0];
  assert.match(article.textContent,/单元 7.*2.*6/);
  function links(element) { return [...(element.tagName === "a" ? [element] : []),...element.children.flatMap(links)]; }
  const notebook=links(article).find(item=>item.href && item.href.endsWith("lesson.ipynb"));
  assert.ok(notebook); assert.ok(!notebook.href.includes("#L"));
});
