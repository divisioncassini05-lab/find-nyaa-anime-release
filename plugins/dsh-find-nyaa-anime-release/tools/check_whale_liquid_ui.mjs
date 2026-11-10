import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const require = process.env.PLAYWRIGHT_NODE_MODULES
  ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const {chromium} = require('playwright');
const root = new URL('../', import.meta.url), out = new URL('.preview/liquid/', root);
const reference = process.env.WHALE_LIQUID_REFERENCE;
const files = new Map();
for (const file of ['whale-liquid-depth.mjs', 'whale-liquid-mask.mjs', 'whale-timeline.mjs']) files.set('/client/' + file, new URL('client/' + file, root));
for (const file of ['manifest.json', 'arm-manifest.json', 'palm-motion.json', 'reading-trace.gif', 'idle-droplet.gif', 'ink-study.gif', 'palm-study.gif']) {
  files.set('/ambient/' + file, new URL('assets/ocean/whale/ambient/' + file, root));
}
if (reference) for (const file of ['liquid-depth-player.mjs', 'liquid-study-player.mjs', 'droplet-motion.mjs']) {
  files.set('/reference/' + file, path.join(reference, file));
}
const html = `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Whale liquid verification</title><style>
body{margin:24px;background:#f4fafb;color:#173a45;font:14px system-ui}body.dark{background:#17282e;color:#edf7f9}
canvas{display:block}#actual{width:150px;height:150px}#detail{width:min(512px,100%);aspect-ratio:1;height:auto}
@media(max-width:600px){#actual{width:132px;height:132px}}h1{font-size:18px}
</style><h1 id="label"></h1><canvas id="actual" width="512" height="512"></canvas><canvas id="detail" width="512" height="512"></canvas>`;
const types = {'.mjs': 'text/javascript', '.json': 'application/json', '.gif': 'image/gif'};
const server = createServer(async (req, res) => {
  const route = new URL(req.url, 'http://localhost').pathname;
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405).end(); return; }
  if (route === '/') { res.writeHead(200, {'Content-Type': 'text/html'}).end(req.method === 'HEAD' ? undefined : html); return; }
  const file = files.get(route);
  if (!file) { res.writeHead(404).end(); return; }
  try {
    const bytes = await readFile(file);
    res.writeHead(200, {'Content-Type': types[path.extname(route)], 'Cache-Control': 'no-store'});
    res.end(req.method === 'HEAD' ? undefined : bytes);
  } catch { res.writeHead(404).end(); }
});
let browser;
try {
  await mkdir(out, {recursive: true});
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? {channel: process.env.PLAYWRIGHT_CHANNEL} : {})});
  const page = await browser.newPage({viewport: {width: 1440, height: 1040}}), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const result = await page.evaluate(async compare => {
    // Pin the raster backend: repeated readbacks otherwise demote only one of
    // the compared canvases from GPU to CPU, changing triangle edge coverage.
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function(type, options) {
      return getContext.call(this, type, type === '2d' ? {...options, willReadFrequently: true} : options);
    };
    const api = await import('/client/whale-liquid-depth.mjs');
    const get = async file => { const response = await fetch('/ambient/' + file); if (!response.ok) throw new Error(file); return response; };
    const manifest = await (await get('manifest.json')).json(), arm = await (await get('arm-manifest.json')).json();
    const palms = await (await get('palm-motion.json')).json(), clips = {}, effects = {};
    const check = (ok, message) => { if (!ok) throw new Error(message); };
    async function decode(spec) {
      const data = await (await get(spec.file)).arrayBuffer();
      const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(x => x.toString(16).padStart(2, '0')).join('');
      check(sha === spec.sha256, 'Browser asset hash mismatch');
      const decoder = new ImageDecoder({type: 'image/gif', data}), frames = [], durations = [];
      try {
        await decoder.tracks.ready;
        check(decoder.tracks.selectedTrack.frameCount === spec.frames, 'Decoded frame count mismatch');
        for (let i = 0; i < spec.frames; i++) {
          const {image} = await decoder.decode({frameIndex: i, completeFramesOnly: true}); frames.push(image);
          durations.push(image.duration / 1000);
          check(image.displayWidth === 512 && image.displayHeight === 512, 'Decoded size mismatch');
        }
        check(JSON.stringify(durations) === JSON.stringify(spec.durations), 'Decoded holds mismatch');
        return {frames, durations, sha256: sha};
      } catch (error) { frames.forEach(frame => frame.close()); throw error; }
      finally { decoder.close(); }
    }
    const canvas = () => { const c = document.createElement('canvas'); c.width = c.height = 512; return c; };
    const pixels = c => c.getContext('2d').getImageData(0, 0, 512, 512).data;
    const same = (a, b) => a.every((value, i) => value === b[i]);
    const layer = canvas(), original = canvas(), composite = document.getElementById('actual'), detail = document.getElementById('detail');
    const state = api.buildContext(), samples = [];
    let refApi, refState;
    for (const id of ['reading-trace', 'idle-droplet']) {
      clips[id] = await decode(manifest.actions[id]); effects[id] = await decode(manifest.liquid.effects[id]);
    }
    if (compare) {
      refApi = await import('/reference/liquid-depth-player.mjs');
      refState = refApi.buildDepthContext(clips, arm.landmarks);
    }
    function load(id) { api.loadAction(state, id, {character: clips[id], liquid: effects[id], landmarks: arm.landmarks, palms}); }
    function render(id, ms) {
      if (state.action?.id !== id) load(id);
      const frame = api.liquidFrame(clips[id].durations, ms), ctx = layer.getContext('2d'); ctx.clearRect(0, 0, 512, 512);
      api.draw(state, ctx, id, ms, frame);
      const c = composite.getContext('2d'); c.clearRect(0, 0, 512, 512); c.drawImage(clips[id].frames[frame], 0, 0); c.drawImage(layer, 0, 0);
      const d = detail.getContext('2d'); d.clearRect(0, 0, 512, 512); d.drawImage(composite, 0, 0);
      document.getElementById('label').textContent = id + ' / ' + ms + 'ms';
      return frame;
    }
    for (const id of ['reading-trace', 'idle-droplet']) {
      load(id);
      if (compare) {
        const masks = id === 'reading-trace' ? refState.trace : refState.palms;
        check(state.action.masks.every((mask, i) => same(pixels(mask), pixels(masks[i]))), 'Reference masks changed');
      }
      const total = clips[id].durations.reduce((a, b) => a + b, 0), times = new Set([0, 499, 500, 650, 1200, 1500, 1900, 2049, 2050, 4699, 4700]);
      let start = 0;
      for (const hold of clips[id].durations) { times.add(start); times.add(start + hold / 2); times.add(start + hold - 1); start += hold; }
      for (let ms = 0; ms < total; ms += 80) times.add(ms);
      for (const ms of [...times].filter(t => t < total).sort((a, b) => a - b)) {
        const frame = render(id, ms), data = pixels(layer);
        const mask = id === 'reading-trace' ? pixels(state.action.masks[frame]) : null;
        let visible = 0, blue = 0, black = 0, overlap = 0;
        for (let i = 0; i < data.length; i += 4) if (data[i + 3] > 40) {
          visible++;
          if (data[i + 2] > data[i] + 10 && data[i + 1] > data[i] + 10) blue++;
          if (Math.max(data[i], data[i + 1], data[i + 2]) < 105) black++;
          if (mask && mask[i + 3] === 255) overlap++;
        }
        check(overlap === 0, 'Ink drawn over cover or fingertip');
        let maxReferenceError = 0;
        if (compare) {
          const ctx = original.getContext('2d'); ctx.clearRect(0, 0, 512, 512);
          if (id === 'reading-trace') refApi.drawDepthInk(ctx, effects[id], refState, ms, frame, arm.landmarks);
          else refApi.drawDepthPalm(ctx, effects[id], palms, refState, ms);
          const expected = pixels(original);
          let alphaError = 0, premultipliedError = 0, changed = 0;
          for (let i = 0; i < data.length; i += 4) {
            alphaError = Math.max(alphaError, Math.abs(data[i + 3] - expected[i + 3]));
            for (let c = 0; c < 4; c++) {
              const error = Math.abs(data[i + c] - expected[i + c]);
              maxReferenceError = Math.max(maxReferenceError, error);
              if (error) changed++;
              if (c < 3) premultipliedError = Math.max(premultipliedError, Math.abs(data[i + c] * data[i + 3] / 255 - expected[i + c] * expected[i + 3] / 255));
            }
          }
          check(maxReferenceError === 0, `Reference pixels changed: ${id} ${ms} (${JSON.stringify({maxReferenceError, alphaError, premultipliedError, changed})})`);
        }
        samples.push({id, ms, visible, blue, black, overlap, maxReferenceError});
      }
      render(id, 1500); const frozen = pixels(layer); render(id, 1500);
      check(same(frozen, pixels(layer)), 'Same clock changed pixels');
      render(id, 1580); check(!same(frozen, pixels(layer)), 'Animated texture stayed still');
      const ctx = original.getContext('2d'); ctx.fillStyle = '#a8c7d2'; ctx.fillRect(0, 0, 512, 512);
      api.draw(state, ctx, id, 1500);
      check(pixels(original).every((value, i) => i % 4 !== 3 || value === 255), 'Caller canvas was erased');
      render(id, Math.min(total - 1, id === 'reading-trace' ? 2050 : 4700));
      check(pixels(layer).every((value, i) => i % 4 !== 3 || value === 0), 'Effect remained after its active interval');
    }
    check(samples.some(s => s.id === 'reading-trace' && s.blue > 2), 'No blue ink phase');
    check(samples.some(s => s.id === 'reading-trace' && s.black > 2), 'No black ink phase');
    check(samples.some(s => s.id === 'idle-droplet' && s.visible > 10), 'Palm effect blank');
    window.liquidCheck = {render, async freeze() {
      render('reading-trace', 1200); const before = pixels(layer);
      await new Promise(resolve => setTimeout(resolve, 120));
      check(same(before, pixels(layer)), 'Liquid owns an unexpected clock');
    }, close() {
      api.disposeContext(state);
      for (const clip of [...Object.values(clips), ...Object.values(effects)]) clip.frames.forEach(frame => frame.close());
    }};
    return {samples, referenceCompared: compare, decoded: Object.fromEntries(Object.entries(clips).map(([id, clip]) => [id, clip.durations]))};
  }, Boolean(reference));
  const screenshots = [];
  for (const width of [1440, 390]) for (const dark of [false, true]) for (const id of ['reading-trace', 'idle-droplet']) {
    await page.setViewportSize({width, height: 1040});
    const box = await page.evaluate(({id, dark}) => {
      document.body.classList.toggle('dark', dark); window.liquidCheck.render(id, id === 'reading-trace' ? 1200 : 1900);
      const rect = document.getElementById('actual').getBoundingClientRect();
      return {width: rect.width, height: rect.height, overflow: document.documentElement.scrollWidth > innerWidth};
    }, {id, dark});
    assert.equal(box.width, width === 1440 ? 150 : 132); assert.equal(box.height, box.width); assert.equal(box.overflow, false);
    const name = `${width}-${dark ? 'dark' : 'light'}-${id}.png`;
    await page.screenshot({path: fileURLToPath(new URL(name, out)), fullPage: true}); screenshots.push(name);
  }
  await page.evaluate(() => window.liquidCheck.freeze());
  await page.evaluate(() => window.liquidCheck.close());
  assert.deepEqual(errors, []);
  await writeFile(new URL('report.json', out), JSON.stringify({...result, screenshots, errors}, null, 2));
  console.log(`Liquid verification passed: ${result.samples.length} samples, exact GIF holds, ink occlusion, blue/black phases, native motion, cleanup, 8 screenshots${reference ? ', exact reference pixels' : ''}.`);
} finally {
  await browser?.close();
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
