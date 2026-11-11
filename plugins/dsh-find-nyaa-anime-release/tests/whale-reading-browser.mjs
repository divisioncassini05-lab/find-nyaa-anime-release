// Real component, native GIF decoder, bundled assets and canvas; no production QA hooks.
import assert from 'node:assert/strict';
import http from 'node:http';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const out=process.env.RETREAT_QA_OUT||path.join(root,'.preview','reading-retreat');await mkdir(out,{recursive:true});
const require=process.env.PLAYWRIGHT_NODE_MODULES
 ?createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES,'../package.json')):createRequire(import.meta.url);
const {chromium}=require('playwright');
const html=await readFile(path.join(root,'.preview/index.html'));
const js=await readFile(path.join(root,'.preview/app.js'));
const server=http.createServer((req,res)=>{
 const script=req.url==='/app.js';res.writeHead(200,{'Content-Type':script?'text/javascript':'text/html','Cache-Control':'no-store'});res.end(script?js:html);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true,channel:'msedge'});
const report={cases:[],errors:[],external:[]};
try{
 for(const width of [1440,390]){
  const page=await browser.newPage({viewport:{width,height:1040}});
  page.on('pageerror',e=>report.errors.push(e.message));
  page.on('request',r=>{if(!r.url().startsWith(`http://127.0.0.1:${server.address().port}`))report.external.push(r.url());});
  await page.addInitScript(()=>{
   const pending=new Map();let id=0,clock=0;
   window.requestAnimationFrame=callback=>{pending.set(++id,callback);return id;};
   window.cancelAnimationFrame=id=>pending.delete(id);
   window.__motionSamples=[];
   window.__motionStep=duration=>{
    do{
     const delta=Math.min(20,duration);clock+=delta;duration-=delta;
     const list=[...pending.values()];pending.clear();for(const callback of list)callback(clock);
     const c=document.querySelector('.anime-whale-canvas');
     if(c)window.__motionSamples.push({clock,stage:c.dataset.stage,phase:c.dataset.readingRetreat,
       clip:c.dataset.retreatClip,frame:Number(c.dataset.frame),elapsed:Number(c.dataset.elapsed)});
    }while(duration>0);
   };
  });
  await page.goto(`http://127.0.0.1:${server.address().port}`,{waitUntil:'networkidle'});
  try{
   // This test owns requestAnimationFrame; readiness must not wait on that parked clock.
   await page.waitForFunction(()=>document.querySelector('.anime-whale')?.dataset.playback==='decoded',null,{polling:50});
  }catch(error){
   await page.screenshot({path:path.join(out,`${width}-load-failure.png`)});
   const state=await page.evaluate(()=>({button:document.querySelector('.anime-whale')?.dataset,
     title:document.title,text:document.body.innerText.slice(0,700)}));
   await writeFile(path.join(out,`${width}-load-failure.json`),JSON.stringify(state,null,2));
   throw error;
  }
  const step=ms=>page.evaluate(ms=>window.__motionStep(ms),ms);
  const state=()=>page.locator('.anime-whale-canvas').evaluate(c=>({...c.dataset,
    phase:c.dataset.readingRetreat,clip:c.dataset.retreatClip}));
  const until=async(predicate,budget=20000)=>{
   for(let ms=0;ms<=budget;ms+=100){const s=await state();if(predicate(s))return s;await step(100);}
   throw Error('Motion boundary not reached: '+JSON.stringify(await state()));
  };
  await step(0);await until(s=>s.stage==='reading');
  const button=page.getByRole('button',{name:'轻轻碰一下小鲸鱼',exact:true});
  // The first two taps retain the reading parent instead of accidentally starting return.
  await button.click({force:true});await step(80);await button.click({force:true});await step(80);await button.click({force:true});
  for(let i=0;i<100;i++){
   await step(0);if((await state()).phase!=='loading')break;await page.waitForTimeout(50);
  }
  await until(s=>s.phase==='character',4000);
  await step(2000);await page.screenshot({path:path.join(out,`${width}-book-lift.png`)});
  const canvas=page.locator('.anime-whale-canvas');const box=await canvas.boundingBox();
  assert.equal(box.width,width===1440?150:132);assert.equal(box.height,box.width);
  await until(s=>s.phase==='covered',5000);await step(700);
  assert.equal((await state()).clip,'recover');
  await page.screenshot({path:path.join(out,`${width}-covered.png`)});
  const paused=await state();
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.querySelector('.anime-current')?.dataset.running==='false',null,{polling:50});
  await step(3000);assert.deepEqual(await state(),paused);
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  await page.waitForFunction(()=>document.querySelector('.anime-current')?.dataset.running==='true',null,{polling:50});
  await step(6000);assert.equal((await state()).phase,'covered');assert.equal((await state()).clip,'reading');
  await until(s=>s.phase==='reveal',2000);await step(1500);
  await page.screenshot({path:path.join(out,`${width}-reveal.png`)});
  await until(s=>s.phase==='idle',2000);assert.equal((await state()).stage,'reading');
  assert.equal((await state()).retreatCompleted,'1');
  const cleared=await page.locator('.anime-whale-magic').evaluate(c=>{
   const p=c.getContext('2d').getImageData(0,0,768,768).data;return p.every((x,i)=>i%4!==3||x===0);
  });assert.equal(cleared,true);
  const samples=await page.evaluate(()=>window.__motionSamples);
  assert.deepEqual([...new Set(samples.filter(s=>s.clip==='recover').map(s=>s.frame))].sort((a,b)=>a-b),Array.from({length:16},(_,i)=>i));
  const entry=samples.findIndex(s=>s.phase==='character');
  assert.equal(samples[entry-1].frame,0);assert.equal(samples[entry-1].clip,'reading');
  assert.equal(samples.filter(s=>s.phase==='character'&&s.frame===0).length>0,true);
  await writeFile(path.join(out,`${width}-samples.json`),JSON.stringify(samples));
  await page.evaluate(()=>document.body.setAttribute('data-ds-dark-theme',''));
  await page.screenshot({path:path.join(out,`${width}-restored-dark.png`)});
  report.cases.push({width,display:box.width,returnFrames:16,completed:1,paused:true,magicCleared:true,readingRestored:true});
  await page.close();
 }
 assert.deepEqual(report.errors,[]);assert.deepEqual(report.external,[]);report.status='passed';
}finally{
 await writeFile(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));
 await browser.close();await new Promise(resolve=>server.close(resolve));
}
console.log(JSON.stringify(report));
