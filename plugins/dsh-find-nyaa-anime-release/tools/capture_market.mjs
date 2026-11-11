import { createRequire } from 'node:module';
import http from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { build } = require('esbuild');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(root, 'assets/readme/market');
await mkdir(output, {recursive:true});
await build({absWorkingDir:root, entryPoints:['client/preview.jsx'], outfile:'.preview/market.js', bundle:true,
  minify:true, target:'es2022', format:'iife', jsx:'transform', legalComments:'none',
  loader:{'.css':'text','.webp':'dataurl','.png':'dataurl','.gif':'dataurl'}, define:{'process.env.NODE_ENV':'"production"'}});
const html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dsh-find-anime | Offline demo</title><style>html,body,#root{height:100%;margin:0}body{font-family:system-ui,sans-serif}*{box-sizing:border-box}.preview-label{height:32px;padding:7px 20px;background:#f1f4f3;color:#526259;font-size:12px}.preview-content{height:calc(100% - 32px)}html[data-theme="dark"]{--dsw-alias-bg-base:#202322;--dsw-alias-bg-secondary:#292e2b;--dsw-alias-label-primary:#e8ede9;--dsw-alias-label-secondary:#a4aea7;--dsw-alias-border-primary:#3e4741}</style><div id="root"></div><script src="/app.js"></script></html>';
const bundle = await readFile(path.join(root,'.preview/market.js'));
const server = http.createServer((req,res)=>{
  const pathname = new URL(req.url,'http://localhost').pathname;
  if(pathname === '/') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(html);}
  else if(pathname === '/app.js') {res.setHeader('Content-Type','text/javascript');res.end(bundle);}
  else {res.writeHead(404);res.end();}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
const errors=[];
try {
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})});
  const context=await browser.newContext({viewport:{width:1440,height:1120},deviceScaleFactor:1,locale:'zh-CN',timezoneId:'Asia/Shanghai'});
  await context.route('**/*', route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  const base=`http://127.0.0.1:${server.address().port}/?state=market`;
  const shot=async name=>{await page.screenshot({path:path.join(output,name),animations:'disabled'});};
  await page.goto(base,{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'晴空列车详情',exact:true}).waitFor();
  await page.waitForTimeout(1800);
  await shot('01-inbox-day.png');
  await page.getByRole('button',{name:'晴空列车详情',exact:true}).click();
  await page.locator('.anime-inbox-record.is-selected').screenshot({path:path.join(output,'02-result.png'),animations:'disabled'});
  await page.getByRole('button',{name:'添加追番',exact:true}).first().click();
  await page.getByLabel('作品名',{exact:true}).fill('晴空列车');
  await page.locator('.anime-schedule-fields select').selectOption('weekly');
  await page.getByLabel('必须有中文字幕',{exact:true}).check();
  await page.setViewportSize({width:1440,height:1400});
  await page.getByRole('dialog').screenshot({path:path.join(output,'03-plan.png'),animations:'disabled'});
  await page.getByRole('button',{name:'关闭',exact:true}).click();
  await page.setViewportSize({width:1440,height:1120});
  await page.getByRole('tab',{name:/Bangumi 番单/}).click();
  await page.getByText('星际邮差',{exact:true}).waitFor();
  await shot('04-bangumi.png');
  await page.goto(base+'&theme=dark',{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'晴空列车详情',exact:true}).waitFor();
  await page.waitForTimeout(1800);
  await page.evaluate(()=>window.scrollTo(0,0));
  await shot('05-inbox-night.png');
  await writeFile(path.join(output,'capture-report.json'),JSON.stringify({viewport:{width:1440,height:1120},source:'client/Panel.jsx',fixture:'client/market-fixture.mjs',externalNetwork:false,errors},null,2)+'\n');
  if(errors.length) throw new Error(errors.join('\n'));
  console.log('Captured five offline UI screenshots: '+output);
} finally {
  await browser?.close();
  await new Promise(resolve=>server.close(resolve));
}
