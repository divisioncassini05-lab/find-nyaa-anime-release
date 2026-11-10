import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {writeFile} from 'node:fs/promises';
const req=process.env.PLAYWRIGHT_NODE_MODULES?createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES,'../package.json')):createRequire(import.meta.url);
const {chromium}=req('playwright');
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
const expected=['idle-feet','idle-droplet','idle-sleeve','reading-trace','reading-think'];
const report=[];
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1040}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{let s=42;Math.random=()=>{s=(1664525*s+1013904223)>>>0;return s/4294967296;};});
  await page.goto(process.env.UI_URL||'http://127.0.0.1:4319');
  await page.waitForFunction(()=>document.querySelector('.anime-whale')?.dataset.playback==='decoded',null,{timeout:60000});
  await page.clock.install();
  const seen=new Set(),sequence=[];
  for(let i=0;i<700&&seen.size<5;i++){
   await page.clock.fastForward(1000);
   // Native decoder promises use the browser task queue, not simulated time.
   await new Promise(r=>setTimeout(r,20));
   const state=await page.locator('.anime-whale-canvas').evaluate(c=>({stage:c.dataset.stage,elapsed:Number(c.dataset.elapsed),book:Number(c.dataset.bookElapsed),width:c.getBoundingClientRect().width}));
   assert.equal(state.width,width===1440?150:132);assert.equal(state.book,state.elapsed);
   if(sequence.at(-1)!==state.stage)sequence.push(state.stage);
   if(expected.includes(state.stage)&&!seen.has(state.stage)){
    seen.add(state.stage);
    await page.screenshot({path:fileURLToPath(new URL(`../.preview/ambient-${width}-${state.stage}.png`,import.meta.url)),fullPage:true});
   }
  }
  assert.deepEqual([...seen].sort(),[...expected].sort(),'all five modules actually play in the built component');
  await page.emulateMedia({reducedMotion:'reduce'});
  await new Promise(r=>setTimeout(r,100));
  const frozen=await page.locator('.anime-whale-canvas').getAttribute('data-elapsed');
  await page.clock.fastForward(60000);
  assert.equal(await page.locator('.anime-whale-canvas').getAttribute('data-elapsed'),frozen);
  await page.emulateMedia({reducedMotion:'no-preference'});
  await new Promise(r=>setTimeout(r,100));await page.clock.fastForward(1000);
  assert.notEqual(await page.locator('.anime-whale-canvas').getAttribute('data-elapsed'),frozen);
  assert.deepEqual(errors,[]);report.push({width,seen:[...seen],sequence,errors});await page.close();
 }
 await writeFile(new URL('../.preview/ambient-browser-report.json',import.meta.url),JSON.stringify(report,null,2));
 console.log('Built ambient UI passed: all five lazy-decoded actions at 150px/132px, continuous book clock, reduced-motion freeze and resume, no browser errors.');
}finally{await browser.close();}
