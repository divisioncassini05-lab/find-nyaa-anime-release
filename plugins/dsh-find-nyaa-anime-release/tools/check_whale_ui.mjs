import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const req = process.env.PLAYWRIGHT_NODE_MODULES ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = req('playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
const base = process.env.UI_URL || 'http://127.0.0.1:4319';
const output = new URL('../.preview/', import.meta.url);
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
  page.setDefaultTimeout(10000);
  const errors = []; const requests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => requests.push(request.url()));
  const whale = page.getByRole('button', { name: '轻轻碰一下小鲸鱼', exact: true });
  const ready = async () => {
    await whale.waitFor();
    await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled);
    await page.waitForFunction(() => document.querySelector('.anime-whale')?.dataset.playback === 'decoded');
  };
  const running = async (value) => page.waitForFunction((v) => document.querySelector('.anime-current')?.dataset.running === String(v), value);
  const geometry = () => page.evaluate(() => {
    const box = (selector) => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, bottom: r.bottom, right: r.right }; };
    return { pet: box('.anime-whale-float'), seat: box('.anime-current-seat'), heading: box('.anime-heading'), metrics: box('.anime-metrics'), current: box('.anime-current') };
  });
  const assertSeated = async () => {
    const { pet, seat, heading, metrics, current } = await geometry();
    assert.ok(pet.y > heading.bottom + 4, 'mascot clears the header and tools');
    assert.ok(pet.bottom < metrics.y - 4, 'feet clear the statistics');
    assert.ok(pet.x >= current.x && pet.right <= current.right, 'mascot remains inside its own ribbon');
    assert.ok(Math.abs(pet.x + pet.width * .5 - seat.x) < .3, 'canvas shares the fixed ribbon anchor horizontally');
    assert.ok(Math.abs(pet.y + pet.height * .78125 - seat.y) < .3, 'reviewed 512px seat stays on the water');
    assert.equal(await page.locator('.anime-scroll').evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true);
  };
  await page.goto(base); await ready(); await running(true);
  assert.equal(await page.locator('.anime-current').getAttribute('aria-hidden'), null, 'interactive mascot must not be aria-hidden');
  assert.equal(await page.locator('.anime-current svg').evaluateAll((items) => items.every((e) => e.getAttribute('aria-hidden') === 'true')), true);
  await page.waitForFunction(() => document.querySelector('.anime-whale')?.dataset.playback === 'decoded');
  const image = page.locator('.anime-whale-canvas');
  const pixels = await image.evaluate((canvas) => {
    const context = canvas.getContext('2d');
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let transparent = 0; let opaque = 0;
    for (let i = 3; i < data.length; i += 4) { if (data[i] === 0) transparent++; if (data[i] > 200) opaque++; }
    return { width: canvas.width, height: canvas.height, transparent, opaque, area: data.length / 4,
      bundled: document.querySelector('.anime-whale-poster').src.startsWith('data:image/png') };
  });
  assert.deepEqual([pixels.width, pixels.height], [512, 512]);
  assert.ok(pixels.bundled && pixels.transparent > pixels.area * .15 && pixels.opaque > pixels.area * .15, 'sprite is nonblank and genuinely transparent, bundled without an external request');
  await assertSeated();
  const row = await page.locator('.anime-inbox-row').first().boundingBox();
  const frameBefore = await image.getAttribute('data-elapsed');
  await page.waitForTimeout(3300);
  assert.notEqual(await image.getAttribute('data-elapsed'), frameBefore, 'native clip frames advance');
  assert.deepEqual(await page.locator('.anime-inbox-row').first().boundingBox(), row, 'idle motion never shifts data');
  const requestCount = requests.length;
  await whale.click();
  await page.locator('.anime-whale-seat.is-greeting').waitFor({ state: 'attached' });
  assert.equal(await page.locator('.anime-whale-ripple').first().evaluate((e) => getComputedStyle(e).animationName), 'anime-whale-ripple');
  await page.waitForTimeout(260);
  await page.screenshot({ path: fileURLToPath(new URL('whale-interaction.png', output)), clip: { x: 0, y: 36, width: 1440, height: 380 } });
  await page.waitForFunction(() => !document.querySelector('.anime-whale-seat.is-greeting'));
  assert.equal(requests.length, requestCount, 'petting never calls services or loads assets');
  assert.deepEqual(await page.locator('.anime-inbox-row').first().boundingBox(), row);
  await whale.focus(); await page.keyboard.press('Enter');
  await page.locator('.anime-whale-seat.is-greeting').waitFor({ state: 'attached' });
  await page.waitForFunction(() => !document.querySelector('.anime-whale-seat.is-greeting'));
  await page.keyboard.press('Space'); await page.locator('.anime-whale-seat.is-greeting').waitFor({ state: 'attached' });
  assert.equal(await whale.getAttribute('draggable'), 'false');
  const p = await whale.boundingBox();
  await page.mouse.move(p.x + p.width * .4, p.y + p.height * .4); await page.mouse.down();
  await page.mouse.move(p.x - 100, p.y + 35, { steps: 8 }); await page.mouse.up();
  await assertSeated();
  await page.waitForFunction(() => !document.querySelector('.anime-whale-seat.is-greeting'));

  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('switch', { name: '背景动态', exact: true }).uncheck();
  await page.keyboard.press('Escape'); await running(false);
  const paused = await image.getAttribute('data-elapsed');
  await page.waitForTimeout(250);
  assert.equal(await image.getAttribute('data-elapsed'), paused, 'disabled motion preserves frame position');
  await whale.click();
  assert.equal(await page.locator('.anime-whale-ripple').first().evaluate((e) => getComputedStyle(e).animationName), 'none');
  assert.ok(Number(await page.locator('.anime-whale-ripple').first().evaluate((e) => getComputedStyle(e).opacity)) > 0, 'static mode keeps gentle click feedback');
  await page.reload(); await ready(); await running(false);
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('switch', { name: '背景动态', exact: true }).check(); await page.keyboard.press('Escape');
  await running(true);
  await page.emulateMedia({ reducedMotion: 'reduce' }); await running(false);
  const reduced = await image.getAttribute('data-elapsed');
  await page.waitForTimeout(250);
  assert.equal(await image.getAttribute('data-elapsed'), reduced, 'reduced motion freezes the same frame');
  await whale.click(); await page.locator('.anime-whale-seat.is-greeting').waitFor({ state: 'attached' });
  assert.equal(await page.locator('.anime-whale-float').evaluate((e) => getComputedStyle(e).animationName), 'none');
  await page.emulateMedia({ reducedMotion: 'no-preference' }); await running(true);
  await page.waitForTimeout(250);
  assert.notEqual(await image.getAttribute('data-elapsed'), reduced, 'resumed motion continues the retained clock');
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await running(false);
  await page.evaluate(() => { delete document.hidden; document.dispatchEvent(new Event('visibilitychange')); });
  await running(true);
  await page.locator('.preview-content').evaluate((e) => { e.style.display = 'none'; }); await running(false);
  await page.locator('.preview-content').evaluate((e) => { e.style.display = ''; }); await running(true);

  for (const dark of [false, true]) {
    await page.evaluate((value) => { if (value) document.body.setAttribute('data-ds-dark-theme', ''); else document.body.removeAttribute('data-ds-dark-theme'); }, dark);
    for (const width of [1440, 1024, 800, 390, 320]) {
      await page.setViewportSize({ width, height: 1040 }); await assertSeated();
      if ([1440, 390, 320].includes(width)) await page.screenshot({ path: fileURLToPath(new URL(`whale-${width}-${dark ? 'dark' : 'light'}.png`, output)), fullPage: true });
    }
  }
  await page.locator('.anime-scroll').evaluate((e) => { e.scrollTop = e.scrollHeight; }); await running(false);
  await page.locator('.anime-scroll').evaluate((e) => { e.scrollTop = 0; }); await running(true);
  for (const width of [1440, 390]) {
    await page.setViewportSize({width, height:1040}); await page.goto(base); await ready();
    await page.waitForFunction(() => document.querySelector('.anime-whale')?.dataset.playback === 'decoded');
    assert.equal((await image.boundingBox()).width, width === 1440 ? 150 : 132);
    await page.evaluate(() => {
      const canvas = document.querySelector('.anime-whale-canvas');
      window.__whaleReview = {stages:[canvas.dataset.stage], wraps:0};
      new MutationObserver(() => {
        const review = window.__whaleReview, stage = canvas.dataset.stage;
        if (stage !== review.stages.at(-1)) {
          if (review.stages.at(-1) === 'return' && stage === 'idle') review.wraps++;
          review.stages.push(stage);
        }
      }).observe(canvas, {attributes:true, attributeFilter:['data-stage']});
    });
    for (const stage of ['receive', 'reading', 'return', 'idle']) {
      await page.waitForFunction((value) => document.querySelector('.anime-whale-canvas').dataset.stage === value, stage, {timeout:20000});
      await page.screenshot({path:fileURLToPath(new URL(`whale-cycle-${width}-${stage}.png`, output)), fullPage:true});
    }
    await page.waitForFunction(() => window.__whaleReview.wraps >= 3, null, {timeout:45000});
    assert.deepEqual(await page.evaluate(() => window.__whaleReview.stages.slice(0,5)), ['idle','receive','reading','return','idle']);
    await assertSeated();
  }
  const fallback = await browser.newPage({viewport:{width:390, height:1040}});
  await fallback.addInitScript(() => { Object.defineProperty(window, 'ImageDecoder', {value:undefined, configurable:true}); });
  await fallback.goto(base);
  await fallback.waitForFunction(() => document.querySelector('.anime-whale')?.dataset.playback === 'poster');
  assert.equal(await fallback.locator('.anime-whale-poster').evaluate((e) => e.complete && e.naturalWidth === 512), true);
  await fallback.close();
  assert.deepEqual(errors, []);
  assert.equal(requests.some((url) => /https?:\/\/(?!127\.0\.0\.1|localhost)/.test(url)), false, 'no external mascot requests');
  console.log('Whale UI checks passed: four native clips, 3 real cycles per size, 150px/132px fixed geometry, alpha, pause/resume, latest safe requests, visibility, keyboard, light/dark and unsupported-decoder poster fallback.');
} finally { await browser.close(); }
