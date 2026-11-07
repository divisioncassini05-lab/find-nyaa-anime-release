import { build } from 'esbuild';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const options = { absWorkingDir: root, bundle: true, minify: true, target: 'es2022', jsx: 'transform',
  legalComments: 'linked', loader: { '.css': 'text' }, define: { 'process.env.NODE_ENV': '"production"' } };
// DSH consumes factory registrations and supplies its own shared React instance.
await build({ ...options, entryPoints: ['client/index.jsx'], outfile: 'lib/client.js', format: 'cjs', external: ['react', 'react-dom'],
  banner: { js: 'window.__ModuleLoader__.load({id:"dsh-find-nyaa-anime-release",factory:(require)=>{var module={exports:{}};var exports=module.exports;' },
  footer: { js: 'return module.exports;}});' } });
await build({ ...options, entryPoints: ['client/preview.jsx'], outfile: '.preview/app.js', format: 'iife' });
await mkdir(new URL('../.preview/', import.meta.url), { recursive: true });
await writeFile(new URL('../.preview/index.html', import.meta.url), '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>动漫追番 · UI 预览</title><style>html,body,#root{height:100%;margin:0}body{font-family:system-ui,sans-serif}*{box-sizing:border-box}.preview-label{height:36px;padding:8px 18px;background:#f1f4f3;color:#526259;font-size:12px;border-bottom:1px solid #dce4df}.preview-content{height:calc(100% - 36px)}.preview-draft{position:fixed;inset:12%;z-index:10;background:white;color:#222;border:1px solid #aaa;padding:24px;box-shadow:0 16px 80px #0003;overflow:auto}.preview-draft textarea{width:100%;height:240px;margin:16px 0;padding:10px}.preview-draft button{padding:8px 16px}html[data-theme="dark"]{--dsw-alias-bg-base:#202322;--dsw-alias-bg-secondary:#292e2b;--dsw-alias-label-primary:#e8ede9;--dsw-alias-label-secondary:#a4aea7;--dsw-alias-border-primary:#3e4741}</style><div id="root"></div><script src="/app.js"></script></html>', 'utf8');
console.log('Built native DSH client and isolated preview. Preview contains example data only.');
