// Real browser checks against scripts/lab_preview.py; no production account access.
const fs=require('fs');
const path=require('path');
const runtime=process.env.RAG_PLAYWRIGHT_MODULE||'C:/Users/zxc/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright';
const {chromium}=require(runtime);
async function main(){
 const browser=await chromium.launch({executablePath:process.env.RAG_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const errors=[];
 const output=path.resolve(__dirname,'../output');fs.mkdirSync(output,{recursive:true});
 const context=await browser.newContext();
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8767/');
 await page.evaluate(async()=>{await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'lab-preview',password:'lab-preview-pass'})});});
 await page.goto('http://127.0.0.1:8767/diagnostics');
 await page.locator('#runs tr').filter({has:page.locator('button')}).first().waitFor();
 const checks=[];
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:900});
  await page.locator('#runs button').first().click();
  await page.locator('#question-detail h2').waitFor();
  await page.screenshot({path:path.join(output,`diagnostics-${width}-2026-10-12.png`),fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  if(overflow)throw new Error(`Horizontal document overflow at ${width}`);
  checks.push(`layout-${width}`);
 }
 await page.setViewportSize({width:1280,height:900});
 await page.locator('#runs tr input').nth(1).check();await page.locator('#runs tr input').nth(2).check();
 await page.locator('#compare').click();await page.locator('#comparison-content p').waitFor();
 if(!(await page.locator('#comparison-content').textContent()).includes('配对样本'))throw new Error('Comparison did not load');checks.push('compare');
 await page.locator('.create>summary').click();
 await page.selectOption('#dataset','agent-learning-v2');await page.selectOption('#split','calibration');
 await page.locator('#review-dataset').click();await page.locator('#dataset-content details').first().waitFor();
 if(await page.locator('#dataset-content details').count()!==20)throw new Error('Calibration split should show 20 questions');checks.push('draft-dataset');
 const pending=page.locator('#dataset-content details').filter({has:page.locator('textarea')}).first();
 await pending.locator('summary').click();
 await pending.locator('textarea').fill('离线浏览器测试记录；只改变临时预览库。');
 await pending.locator('form button').click();
 await page.getByText('复核已保存，已有实验快照保持原状。').first().waitFor();checks.push('dataset-review');
 const payload=await page.evaluate(async()=>{const me=await(await fetch('/api/me')).json();return await(await fetch('/api/lab/runs',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf},body:JSON.stringify({name:'浏览器离线测试',request_key:crypto.randomUUID(),dataset:'agent-learning-v1',split:'dev'})})).json();});
 if(!payload.id)throw new Error('Create run failed');checks.push('create');
 if(errors.length)throw new Error(errors.join('\n'));
 fs.writeFileSync(path.join(output,'diagnostics-browser-checks.json'),JSON.stringify({checks,pageErrors:errors,realModelCalls:0},null,2));
 console.log(JSON.stringify({checks,pageErrors:errors}));
 await context.close();await browser.close();
}
main().catch(e=>{console.error(e);process.exitCode=1;});
