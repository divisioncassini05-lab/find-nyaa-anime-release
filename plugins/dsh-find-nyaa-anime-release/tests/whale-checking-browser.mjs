// Isolated real-decoder/canvas QA, not a product entry point or demo control surface.
import assert from 'node:assert/strict';
import http from 'node:http';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = path.join(root, '.preview', 'checking');
await mkdir(path.join(output, 'temp'), { recursive: true });
process.env.TEMP = process.env.TMP = process.env.TMPDIR = path.join(output, 'temp');
const require = process.env.PLAYWRIGHT_NODE_MODULES
  ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = require('playwright');
const bundled = await build({ stdin: { contents: `
  import idle from './assets/ocean/whale/ambient/idle-character.gif';
  import book from './assets/ocean/whale/ambient/book-loop.gif';
  import {decodeWhaleClips, closeWhaleClips} from './client/whale-timeline.mjs';
  export {prepareWhaleChecking, checkingManifest} from './client/whale-checking-assets.mjs';
  export {WhaleCheckingController} from './client/whale-checking.mjs';
  export const shared=()=>decodeWhaleClips({idle,book},()=>false,globalThis.ImageDecoder,{idle:16,book:16});
  export const close=closeWhaleClips;
`, resolveDir: root }, bundle: true, write: false, format: 'esm', target: 'es2022', loader: { '.gif': 'dataurl' } });
const html = `<!doctype html><meta charset="utf-8"><style>
  html,body{margin:0;background:#f0f6f3;overflow:hidden}canvas{position:absolute;pointer-events:none}
  #fish{inset:0;z-index:0}#character{z-index:1}#magic{z-index:2}
  </style><canvas id="fish"></canvas><canvas id="character" width="512" height="512"></canvas><canvas id="magic" width="768" height="768"></canvas>`;
const server = http.createServer((req, res) => {
  res.setHeader('Content-Type', req.url === '/entry.js' ? 'text/javascript' : 'text/html');
  res.end(req.url === '/entry.js' ? bundled.outputFiles[0].text : html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
const report = { cases: [], errors: [] };
try {
  browser = await chromium.launch({ headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge' });
  for (const [width, height, size, dpr] of [[1440, 1040, 150, 1], [390, 844, 132, 2], [320, 844, 132, 1]]) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: dpr });
    page.on('pageerror', e => report.errors.push(e.message));
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.evaluate(async ({ width, height, size, dpr }) => {
      const module = await import('/entry.js'), shared = await module.shared();
      const owner = await module.prepareWhaleChecking({ ...shared, seed: 17 });
      const geometry = { width, height, left: width - size - 18, top: 80,
        characterWidth: size, viewTop: 0, viewBottom: Math.min(740, height), idleReady: true };
      const character = document.querySelector('#character'), fish = document.querySelector('#fish'), magic = document.querySelector('#magic');
      Object.assign(character.style, { left: geometry.left + 'px', top: '80px', width: size + 'px', height: size + 'px' });
      Object.assign(magic.style, { left: geometry.left - size / 4 + 'px', top: 80 - size / 4 + 'px', width: size * 1.5 + 'px', height: size * 1.5 + 'px' });
      fish.width = width * dpr; fish.height = height * dpr;
      Object.assign(fish.style, { width: width + 'px', height: height + 'px' });
      const contexts = { character: character.getContext('2d'), fish: fish.getContext('2d'), magic: magic.getContext('2d') };
      contexts.fish.setTransform(dpr, 0, 0, dpr, 0, 0);
      const review = globalThis.review = { module, shared, owner, c: owner, geometry, contexts, bookElapsed: 1234 };
      review.draw = () => review.c.draw({ ...contexts, bookElapsed: review.bookElapsed });
      review.advance = (duration, options = {}) => {
        while (duration > 0) {
          const step = Math.min(100, duration);
          review.bookElapsed += review.c.update(step, { ...geometry, ...options });
          duration -= step;
        }
        review.draw();
      };
      review.pixels = id => {
        const canvas = document.getElementById(id), ctx = canvas.getContext('2d');
        const bytes = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        let count = 0, bottom = 0;
        for (let i = 3; i < bytes.length; i += 4) if (bytes[i]) { count++; bottom = Math.floor(i / 4 / canvas.width); }
        return { count, bottom: bottom / (id === 'fish' ? dpr : 1) };
      };
      owner.start(); owner.update(0, geometry); review.advance(4000);
    }, { width, height, size, dpr });
    const formation = await page.evaluate(() => ({ character: review.pixels('character'), magic: review.pixels('magic'),
      timing: Object.fromEntries(Object.entries(review.owner.clips).map(([id, c]) => [id, c.durations.reduce((a, b) => a + b, 0)])) }));
    assert.ok(formation.character.count > 25000); assert.ok(formation.magic.count > 1000);
    assert.equal(formation.timing.enter, 2400); assert.equal(formation.timing.guide, 3200);
    assert.equal(formation.timing.exit, 2880); assert.equal(formation.timing.attention, 4200);
    assert.equal(formation.timing.water, 3200); assert.equal(formation.timing.birth, 2560);
    await page.screenshot({ path: path.join(output, `${width}-formation.png`) });
    await page.evaluate(() => review.advance(13000));
    const swimming = await page.evaluate(() => ({ pixels: review.pixels('fish'), count: review.c.school.items.length,
      waterBottom: review.c.school.waterBottom, x: review.c.school.items[0].x }));
    assert.ok(swimming.pixels.count > 20); assert.ok(swimming.pixels.bottom <= swimming.waterBottom + 1);
    const before = await page.locator('#fish').evaluate(c => c.toDataURL());
    await page.evaluate(() => review.advance(201));
    assert.notEqual(await page.locator('#fish').evaluate(c => c.toDataURL()), before);
    await page.screenshot({ path: path.join(output, `${width}-swimming.png`) });
    const pause = await page.evaluate(() => {
      const before = { clock: review.c.clock, book: review.bookElapsed, pixel: document.querySelector('#fish').toDataURL() };
      review.advance(5000, { running: false });
      return { clock: review.c.clock === before.clock, book: review.bookElapsed === before.book,
        pixel: document.querySelector('#fish').toDataURL() === before.pixel };
    });
    assert.deepEqual(pause, { clock: true, book: true, pixel: true });
    const outcomes = await page.evaluate(() => {
      const values = [];
      for (const result of ['success', 'attention', 'no_update', 'cancelled']) {
        const c = new review.module.WhaleCheckingController({ clips: review.owner.clips, metadata: review.module.checkingManifest, seed: 17 });
        review.c = c; c.start(); c.update(0, review.geometry); review.advance(6500); c.finish(result);
        const states = new Set(), born = c.school.nextId;
        for (let i = 0; i < 180 && c.active; i++) { review.advance(100); states.add(c.state); }
        values.push({ result, lastResult: c.lastResult, completed: c.completed, canReturn: c.canReturn,
          noBirths: c.school.nextId === born, feedback: states.has('feedback') });
        c.dispose();
      }
      return values;
    });
    for (const value of outcomes) {
      assert.equal(value.lastResult, value.result); assert.equal(value.completed, 1);
      assert.ok(value.canReturn && value.noBirths);
      assert.equal(value.feedback, ['success', 'attention'].includes(value.result));
    }
    report.cases.push({ width, height, dpr, formation, swimming, pause, outcomes });
    await page.evaluate(() => { review.owner.dispose(); review.module.close(review.shared); });
    await page.close();
  }
  assert.deepEqual(report.errors, []);
  report.status = 'passed';
  await writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2) + '\n');
  console.log('Checking browser QA passed: actual GIF decode, native timings, 3 viewports, DPR2, nonblank/moving pixels, layers, pause and all outcomes.');
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
