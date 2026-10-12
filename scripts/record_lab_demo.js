// Reproducible screen recording of the isolated preview, using actual public results.
const path=require('path');const fs=require('fs');
process.env.PLAYWRIGHT_BROWSERS_PATH=path.resolve(__dirname,'../output/playwright');
const {chromium}=require(process.env.RAG_PLAYWRIGHT_MODULE||'C:/Users/zxc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
async function main(){
 const out=path.resolve(__dirname,'../output/lab-demo');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.RAG_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const auth=await browser.newContext();const login=await auth.newPage();
 await login.goto('http://127.0.0.1:8767/');
 await login.evaluate(()=>fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'lab-preview',password:'lab-preview-pass'})}));
 const context=await browser.newContext({viewport:{width:1280,height:900},storageState:await auth.storageState(),recordVideo:{dir:out,size:{width:1280,height:900}}});
 const page=await context.newPage();await page.goto('http://127.0.0.1:8767/diagnostics');
 await page.locator('#runs button').first().waitFor();await page.waitForTimeout(1800);
 await page.getByRole('button',{name:'baseline',exact:true}).click();
 await page.locator('#question-detail h2').waitFor();
 const q=page.locator('#questions button').filter({hasText:'C21'});if(await q.count())await q.first().click();
 await page.locator('#question-detail').scrollIntoViewIfNeeded();await page.waitForTimeout(2600);
 const evidence=page.locator('#question-detail .evidence summary').first();if(await evidence.count())await evidence.click();await page.waitForTimeout(2600);
 await page.getByRole('button',{name:'引用真实，结论待核查 · 离线构造样例',exact:true}).click();
 await page.getByRole('heading',{name:'声明诊断与人工复核'}).scrollIntoViewIfNeeded();await page.waitForTimeout(3200);
 await page.locator('#runs tr').filter({has:page.getByRole('button',{name:'baseline',exact:true})}).locator('input').check();
 await page.locator('#runs tr').filter({has:page.getByRole('button',{name:'body-only',exact:true})}).locator('input').check();
 await page.locator('#compare').click();await page.locator('#comparison-content p').waitFor();await page.waitForTimeout(3200);
 const video=page.video();await context.close();await video.saveAs(path.join(out,'rag-quality-diagnostic-demo.webm'));
 await auth.close();await browser.close();console.log(path.join(out,'rag-quality-diagnostic-demo.webm'));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
