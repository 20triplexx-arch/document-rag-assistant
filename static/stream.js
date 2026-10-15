"use strict";
// Decode UTF-8 incrementally: a Chinese character and an SSE line can cross reads.
async function readAnswerStream(response, onEvent) {
  if (!response.ok) {
    let detail;
    try { detail = (await response.json()).detail; } catch { /* fixed message below */ }
    throw new Error(detail || "提问未能开始，请检查登录状态和剩余额度。");
  }
  if (!response.body) throw new Error("浏览器未能读取回答，请刷新讨论查看结果。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", {fatal:true});
  let pending = "", data = [], finalResult = null;
  function line(value) {
    if (value.endsWith("\r")) value = value.slice(0, -1);
    if (value.startsWith("data:")) data.push(value.slice(5).replace(/^ /, ""));
    if (value !== "" || !data.length) return;
    const event = JSON.parse(data.join("\n")); data = [];
    if (finalResult) throw new Error("回答流在完成后返回了额外内容。");
    if (!["progress", "evidence", "block", "result", "error"].includes(event.type)) throw new Error("回答流格式异常。");
    if (event.type === "error") throw new Error(event.detail || "本次处理未完成，请刷新讨论查看结果。");
    if (event.type === "result") finalResult = event.result;
    onEvent(event);
  }
  try {
    while (true) {
      const {value, done} = await reader.read();
      pending += done ? decoder.decode() : decoder.decode(value, {stream:true});
      if (pending.length > 2 * 1024 * 1024) throw new Error("回答流超过容量限制。");
      let position;
      while ((position = pending.indexOf("\n")) >= 0) {
        line(pending.slice(0, position)); pending = pending.slice(position + 1);
      }
      if (done) break;
    }
    if (pending || data.length || !finalResult) throw new Error("回答连接已中断，请刷新讨论查看最终结果。");
    return finalResult;
  } finally {
    // Cancelling this reader never submits a second generation request.
    try { await reader.cancel(); } catch { /* already closed */ }
    reader.releaseLock();
  }
}
