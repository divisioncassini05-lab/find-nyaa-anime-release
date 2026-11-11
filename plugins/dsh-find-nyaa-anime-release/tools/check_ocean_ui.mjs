import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const req = process.env.PLAYWRIGHT_NODE_MODULES ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = req('playwright');
const browser = await chromium.launch({ headless:true, ...(process.env.PLAYWRIGHT_CHANNEL ? {channel:process.env.PLAYWRIGHT_CHANNEL} : {}) });
const base = process.env.UI_URL || 'http://127.0.0.1:4319';
const output = new URL('../.preview/', import.meta.url);
const errors = [], views = [];
try {
  const page = await browser.newPage({viewport:{width:1440,height:1040}});
  page.on('pageerror', error => errors.push(error.message));
  const ready = async () => {
    await page.waitForFunction(() => document.querySelector('.anime-environment')?.dataset.state === 'ready');
    await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled);
    await page.waitForSelector('.anime-summoned-fish');
  };
  const shot = name => page.screenshot({path:fileURLToPath(new URL(name,output)),fullPage:true});
  const waitTheme = theme => page.waitForFunction(t => document.querySelector('.anime-environment')?.dataset.state === 'ready' && document.querySelector('.anime-environment')?.dataset.theme === t,theme);
  const pixels = selector => page.locator(selector).evaluate(c => c.toDataURL());
  async function assertFrozen() {
    await page.waitForTimeout(80);
    const before = await pixels('.anime-environment-water');
    const fish = await pixels('.anime-environment-fauna');
    const time = await page.locator('.anime-environment').getAttribute('data-time');
    await page.waitForTimeout(350);
    assert.equal(await pixels('.anime-environment-water'),before);
    assert.equal(await pixels('.anime-environment-fauna'),fish);
    assert.equal(await page.locator('.anime-environment').getAttribute('data-time'),time);
  }
  for (const width of [1440,780,390,320]) for (const theme of ['light','dark']) {
    await page.setViewportSize({width,height:1040});
    await page.goto(`${base}?theme=${theme}`); await ready();
    const geometry = await page.evaluate(() => {
      const ocean=document.querySelector('.anime-ocean'), env=document.querySelector('.anime-environment');
      const fish=document.querySelector('.anime-summoned-fish'), ui=document.querySelector('.anime-scroll');
      const parent=ocean.getBoundingClientRect();
      const images=[...ocean.querySelectorAll('.anime-water')].filter(i=>getComputedStyle(i).display!=='none');
      const layout=images.map(i=>{const r=i.getBoundingClientRect();return {x:r.x-parent.x,y:r.y-parent.y,width:r.width,height:r.height,source:[i.naturalWidth,i.naturalHeight],mask:getComputedStyle(i).maskImage};});
      const backdrop=[...ocean.querySelectorAll('img')].every(i=>i.complete&&i.naturalWidth>0&&i.src.startsWith('data:image/webp'));
      return {theme:env.dataset.theme,count:+env.dataset.count,inert:env.inert,aria:env.getAttribute('aria-hidden'),backdrop,layout,height:parent.height,
        isolated:getComputedStyle(ocean).isolation,zOcean:getComputedStyle(ocean).zIndex,zFish:getComputedStyle(fish).zIndex,zUI:getComputedStyle(ui).zIndex,
        after:Boolean(ocean.compareDocumentPosition(fish)&Node.DOCUMENT_POSITION_FOLLOWING),overflow:ui.scrollWidth>ui.clientWidth+1,
        pointers:[...env.querySelectorAll('canvas')].map(c=>getComputedStyle(c).pointerEvents)};
    });
    assert.equal(geometry.theme,theme==='dark'?'night':'day'); assert.ok(geometry.count>0);
    assert.ok(geometry.inert&&geometry.backdrop);assert.equal(geometry.aria,'true');
    assert.equal(geometry.isolated,'isolate');assert.equal(geometry.zOcean,'0');assert.equal(geometry.zFish,'0');assert.equal(geometry.zUI,'1');assert.ok(geometry.after);
    assert.equal(geometry.overflow,false);assert.deepEqual(geometry.pointers,['none','none']);
    assert.equal(geometry.layout.length,2);assert.equal(geometry.layout[0].y,0);
    assert.ok(Math.abs(geometry.layout[1].y+geometry.layout[1].height-geometry.height)<1);
    for(const painting of geometry.layout){assert.deepEqual(painting.source,[1536,1024]);assert.ok(Math.abs(painting.width/painting.height-1.5)<.001);assert.notEqual(painting.mask,'none');}
    for(const selector of ['.anime-environment-water','.anime-environment-fauna']){
      const first=await pixels(selector);
      const count=await page.locator(selector).evaluate(c=>{const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i])n++;return n;});
      assert.ok(count>200);await page.waitForTimeout(400);assert.notEqual(await pixels(selector),first);
    }
    await shot(`ocean-${width}-${theme}.png`);views.push({width,theme,count:geometry.count});
    await page.getByRole('button',{name:'插件设置',exact:true}).click();
    await page.getByRole('button',{name:'配置 qBittorrent',exact:true}).click();
    const box=await page.getByRole('dialog').boundingBox();assert.ok(box.x>=0&&box.x+box.width<=width+1);
    await page.keyboard.press('Escape');
  }
  await page.setViewportSize({width:1440,height:1040});await page.goto(base);await ready();
  const before=await page.locator('.anime-inbox-row').first().boundingBox();await page.waitForTimeout(500);
  assert.deepEqual(await page.locator('.anime-inbox-row').first().boundingBox(),before);
  const host=await page.locator('.preview-label').evaluate(e=>({color:getComputedStyle(e).color,height:e.offsetHeight}));
  await page.evaluate(()=>document.body.setAttribute('data-ds-dark-theme',''));await waitTheme('night');
  assert.deepEqual(await page.locator('.preview-label').evaluate(e=>({color:getComputedStyle(e).color,height:e.offsetHeight})),host);
  await page.evaluate(()=>document.body.removeAttribute('data-ds-dark-theme'));await waitTheme('day');
  await page.getByRole('button',{name:'插件设置',exact:true}).click();
  await page.getByRole('switch',{name:'背景动态'}).uncheck();await assertFrozen();
  await page.reload();await ready();await assertFrozen();
  await page.getByRole('button',{name:'插件设置',exact:true}).click();
  assert.equal(await page.getByRole('switch',{name:'背景动态'}).isChecked(),false);
  await page.getByRole('switch',{name:'背景动态'}).check();await page.keyboard.press('Escape');
  await page.emulateMedia({reducedMotion:'reduce'});await assertFrozen();
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'));});await assertFrozen();
  await page.evaluate(()=>{delete document.hidden;document.dispatchEvent(new Event('visibilitychange'));});
  const resume=await pixels('.anime-environment-fauna');await page.waitForTimeout(400);assert.notEqual(await pixels('.anime-environment-fauna'),resume);
  await page.locator('.anime-inbox-work').first().focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('.anime-inbox-work').first().getAttribute('aria-expanded'),'true');
  await shot('ocean-detail.png');
  for(const state of ['empty','error']){await page.goto(`${base}?state=${state}`);await ready();await shot(`ocean-${state}.png`);}
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',views,checks:['native water/fish pixels move','terrain unchanged','environment below summoned fish, actor and UI','motion pause persists','hidden and reduced motion freeze','theme isolation','responsive dialogs and unchanged layout'],errors,real_profile_used:false,cloud_writes:false}));
} finally { await browser.close(); }
