// Temporary local preview only. Never opens a personal browser profile.
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.RAG_PLAYWRIGHT_MODULE||'C:/Users/zxc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
async function main(){
  const out=path.resolve(__dirname,'../output/qa-overhaul-20261015-v2');
  const browser=await chromium.launch({executablePath:process.env.RAG_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  const context=await browser.newContext();const page=await context.newPage();const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto('http://127.0.0.1:8872/');
    await page.evaluate(async()=>{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'overhaul-preview',password:'overhaul-preview-pass'})});if(!r.ok)throw new Error('Preview login failed');});
    await page.reload();await page.locator('#chat-list .chat-open').first().waitFor();
    const checks=[];
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:900});
      if(width===390)await page.locator('#history-toggle').click();
      await page.locator('#chat-list .chat-open').first().click();
      await page.locator('.answer-sources').waitFor();
      await page.locator('.answer-sources > summary').click();
      await page.locator('.answer-sources details > summary').first().click();
      const link=page.locator('.answer-sources a').filter({hasText:/单元/}).first();
      await link.waitFor();const href=await link.getAttribute('href');
      if(!href.endsWith('.ipynb')||href.includes('#L'))throw new Error('Notebook link used virtual GitHub line');
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw new Error('Page overflow '+width);
      await page.screenshot({path:path.join(out,`notebook-${width}.png`),fullPage:true});
      await page.locator('#library-button').click();
      const coverage=await page.locator('#library-coverage').textContent();
      if(!coverage.includes('2164')||!coverage.includes('871'))throw new Error('Missing ingestion counts');
      await page.locator('#close-library').click();
      checks.push({width,notebookLabel:await link.textContent(),href,coverage,horizontalOverflow:false});
    }
    if(errors.length)throw new Error(errors.join('\n'));
    const result={checks,pageErrors:errors,modelCalls:0,accountDatabase:'temporary preview only'};
    fs.writeFileSync(path.join(out,'ui-browser-checks.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  } finally {await context.close();await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
