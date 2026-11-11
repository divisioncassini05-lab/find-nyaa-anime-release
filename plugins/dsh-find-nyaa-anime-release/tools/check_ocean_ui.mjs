import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const req = process.env.PLAYWRIGHT_NODE_MODULES ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = req('playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
const base = process.env.UI_URL || 'http://127.0.0.1:4319';
const output = new URL('../.preview/', import.meta.url);
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
  await page.addInitScript(() => { Math.random = () => .1; });
  page.on('pageerror', (error) => errors.push(error.message));
  const ready = async () => { await page.locator('.anime-panel').waitFor(); await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled); };
  const shot = async (name) => page.screenshot({ path: fileURLToPath(new URL(name, output)), fullPage: true });
  const running = async (value) => page.waitForFunction((v) => document.querySelector('.anime-ocean')?.dataset.running === String(v), value);
  const backgroundGeometry = async (theme) => page.locator(`.anime-water-${theme}`).evaluateAll((imgs) => imgs.map((img) => {
    const b = img.getBoundingClientRect();
    const parent = img.parentElement.getBoundingClientRect();
    return { x:b.x-parent.x, y:b.y-parent.y, width:b.width, height:b.height,
      panelHeight:parent.height, sourceWidth:img.naturalWidth, sourceHeight:img.naturalHeight,
      mask:getComputedStyle(img).maskImage };
  }));
  await page.goto(base); await ready(); await running(true);
  assert.equal(await page.locator('.anime-ocean').getAttribute('aria-hidden'), 'true');
  assert.equal(await page.locator('.anime-ocean').evaluate((e) => getComputedStyle(e).pointerEvents), 'none');
  await page.waitForFunction(() => [...document.querySelectorAll('.anime-ocean img')].every((i) => i.complete && i.naturalWidth > 0));
  assert.equal(await page.locator('.anime-ocean img').evaluateAll((imgs) => imgs.length === 9 && imgs.every((i) => i.src.startsWith('data:image/webp'))), true);
  assert.equal(await page.locator('.anime-day-fauna:visible').count(), 1);
  assert.equal(await page.locator('.anime-night-fauna:visible').count(), 0);
  const dayPass = page.locator('.anime-day-fauna .anime-fauna-pass');
  assert.ok(Number(await dayPass.getAttribute('data-count')) <= 3);
  const startPosition = await dayPass.boundingBox();
  await page.waitForTimeout(1000);
  assert.ok((await dayPass.boundingBox()).x - startPosition.x > 25, 'swimming must be visible, not a few pixels per minute');
  assert.equal(await page.locator('.anime-night-fauna .anime-fauna-pass').evaluate((e) => getComputedStyle(e).animationPlayState), 'paused');
  // A completed pass rotates the pool; child fin/pulse animations must not do so.
  await dayPass.locator('.anime-fauna-body').evaluate((e) => e.dispatchEvent(new AnimationEvent('animationend', { bubbles: true, animationName: 'anime-fish-stroke' })));
  assert.equal(await dayPass.getAttribute('data-cycle'), '0');
  await page.evaluate(() => { Math.random = () => .9; });
  await dayPass.evaluate((e) => e.getAnimations().find((a) => a.animationName === 'anime-fauna-pass').finish());
  await page.waitForFunction(() => document.querySelector('.anime-day-fauna .anime-fauna-pass').dataset.cycle === '1');
  assert.equal(await dayPass.getAttribute('data-variant'), 'seahorse-gold');
  assert.equal(await page.locator('.anime-day-fauna .anime-fauna-pass').count(), 1);
  const lightGeometry = await backgroundGeometry('light');
  assert.equal(lightGeometry[0].y, 0, 'water surface stays at the top');
  assert.ok(Math.abs(lightGeometry[1].y + lightGeometry[1].height - lightGeometry[1].panelHeight) < 1, 'seabed stays at the bottom');
  lightGeometry.forEach((g) => {
    assert.equal(g.sourceWidth, 1536); assert.equal(g.sourceHeight, 1024);
    assert.ok(Math.abs(g.width / g.height - 1.5) < .001, 'background artwork cannot stretch');
    assert.notEqual(g.mask, 'none', 'edge artwork fades into quiet central water');
  });
  assert.equal(await page.locator('.anime-bubble-trail:visible').count(), 1);
  assert.ok(Number(await page.locator('.anime-bubble-trail').evaluate((e) => getComputedStyle(e).opacity)) <= .5);
  assert.ok(Number(await page.locator('.anime-current-traces').evaluate((e) => getComputedStyle(e).opacity)) <= .1);
  const before = await page.locator('.anime-inbox-row').first().boundingBox();
  const transform = await page.locator('.anime-water-lighting').evaluate((e) => getComputedStyle(e).transform);
  await page.waitForTimeout(300);
  assert.notEqual(await page.locator('.anime-water-lighting').evaluate((e) => getComputedStyle(e).transform), transform);
  assert.deepEqual(await page.locator('.anime-inbox-row').first().boundingBox(), before, 'decoration cannot shift content');
  const columns = await page.locator('.anime-inbox-row').evaluateAll((rows) => rows.map((r) => [...r.children].map((c) => c.getBoundingClientRect().x)));
  columns.slice(1).forEach((row) => assert.deepEqual(row, columns[0], 'columns align between rows'));
  await shot('ocean-desktop-light.png');
  await page.screenshot({ path: fileURLToPath(new URL('ribbon-day.png', output)), clip: { x: 0, y: 36, width: 1440, height: 300 } });
  const pet = await page.locator('.anime-whale').boundingBox();
  const heading = await page.locator('.anime-heading').boundingBox();
  const metrics = await page.locator('.anime-metrics').boundingBox();
  assert.ok(pet.y >= heading.y + heading.height, 'seated mascot clears header controls');
  assert.ok(pet.y + pet.height < metrics.y, 'dangling feet clear metrics');
  assert.equal(await page.locator('.anime-current').getAttribute('aria-hidden'), null);
  assert.equal(await page.locator('.anime-current').evaluate((e) => getComputedStyle(e).pointerEvents), 'none');

  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await shot('ocean-settings.png');
  await page.getByRole('switch', { name: '背景动态', exact: true }).uncheck(); await running(false);
  for (const selector of ['.anime-bubble-trail', '.anime-fauna-body', '.anime-current-traces']) {
    assert.equal(await page.locator(selector).first().evaluate((e) => getComputedStyle(e).animationPlayState), 'paused');
  }
  assert.equal(await dayPass.evaluate((e) => getComputedStyle(e).animationName), 'none');
  assert.ok(Number(await dayPass.evaluate((e) => getComputedStyle(e).opacity)) > 0, 'static mode keeps a visible animal');
  await page.reload(); await ready(); await running(false);
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  assert.equal(await page.getByRole('switch', { name: '背景动态' }).isChecked(), false);
  await page.getByRole('switch', { name: '背景动态' }).check(); await running(true);
  await page.keyboard.press('Escape');
  await page.emulateMedia({ reducedMotion: 'reduce' }); await running(false);
  for (const selector of ['.anime-bubble-trail', '.anime-fauna-pass', '.anime-fauna-body', '.anime-current-traces']) {
    assert.equal(await page.locator(selector).first().evaluate((e) => getComputedStyle(e).animationName), 'none');
  }
  await page.emulateMedia({ reducedMotion: 'no-preference' }); await running(true);
  // Simulate host tab hiding without altering the production lifecycle code.
  await page.locator('.preview-content').evaluate((e) => { e.style.display = 'none'; }); await running(false);
  await page.locator('.preview-content').evaluate((e) => { e.style.display = ''; }); await running(true);
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); }); await running(false);
  await page.evaluate(() => { delete document.hidden; document.dispatchEvent(new Event('visibilitychange')); }); await running(true);

  const hostStyle = await page.locator('.preview-label').evaluate((e) => ({ color: getComputedStyle(e).color, background: getComputedStyle(e).backgroundColor, height: e.offsetHeight }));
  const dayVariant = await dayPass.getAttribute('data-variant');
  await page.evaluate(() => document.body.setAttribute('data-ds-dark-theme', ''));
  await page.waitForFunction(() => getComputedStyle(document.querySelector('button[aria-label="插件设置"]')).backgroundColor === 'rgba(33, 59, 68, 0.93)');
  assert.equal(await page.locator('.anime-water-light:visible').count(), 0);
  assert.equal(await page.locator('.anime-water-dark:visible').count(), 2);
  assert.equal(await page.locator('.anime-day-fauna:visible').count(), 0);
  assert.equal(await page.locator('.anime-night-fauna:visible').count(), 1);
  assert.equal(await page.locator('.anime-night-fauna .anime-fauna-pass').getAttribute('data-species'), 'lanternfish');
  assert.equal(await dayPass.evaluate((e) => getComputedStyle(e).animationPlayState), 'paused');
  assert.equal(await page.locator('.anime-night-fauna .anime-fauna-pass').evaluate((e) => getComputedStyle(e).animationPlayState), 'running');
  assert.deepEqual(await backgroundGeometry('dark'), lightGeometry, 'themes share the exact terrain framing');
  assert.equal(await page.locator('.anime-panel').evaluate((e) => getComputedStyle(e).backgroundColor), 'rgb(16, 31, 36)');
  assert.equal(await page.getByRole('button', { name: '插件设置', exact: true }).evaluate((e) => getComputedStyle(e).backgroundColor), 'rgba(33, 59, 68, 0.93)');
  assert.deepEqual(await page.locator('.preview-label').evaluate((e) => ({ color: getComputedStyle(e).color, background: getComputedStyle(e).backgroundColor, height: e.offsetHeight })), hostStyle, 'plugin theme must not restyle host');
  await shot('ocean-desktop-dark.png');
  await page.screenshot({ path: fileURLToPath(new URL('ribbon-night.png', output)), clip: { x: 0, y: 36, width: 1440, height: 300 } });
  await page.evaluate(() => document.body.removeAttribute('data-ds-dark-theme'));
  await page.waitForTimeout(200);
  assert.equal(await dayPass.getAttribute('data-variant'), dayVariant, 'theme changes preserve the chosen group');

  await page.locator('.anime-inbox-work').first().focus(); await page.keyboard.press('Enter');
  assert.equal(await page.locator('.anime-inbox-work').first().getAttribute('aria-expanded'), 'true');
  await shot('ocean-detail.png');
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('button', { name: '连接 Bangumi', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await shot('ocean-bangumi-config.png');
  await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('dialog').count(), 0);

  for (const width of [1920, 1024, 800, 390, 320]) {
    await page.setViewportSize({ width, height: 960 });
    await page.goto(base); await ready();
    // Stress wrapping with a title long enough to span several lines on mobile.
    await page.locator('.anime-work strong').first().evaluate((e) => { e.textContent = '一个很长的作品名称：The Long Chronicle of an Underwater Journey / 新篇章'; });
    assert.equal(await page.locator('.anime-scroll').evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, `overflow at ${width}`);
    assert.equal(await page.locator('.anime-bubble-trail:visible').count(), 1);
    const bubbleClip = await page.locator('.anime-bubble-trail').evaluate((e) => getComputedStyle(e).clipPath);
    assert.equal(bubbleClip === 'none', width > 600, 'narrow windows crop the trail to its lower three bubbles');
    const day = await backgroundGeometry('light');
    assert.equal(day[0].y, 0);
    assert.ok(Math.abs(day[1].y + day[1].height - day[1].panelHeight) < 1);
    assert.ok(day.every((g) => Math.abs(g.width / g.height - 1.5) < .001));
    await page.evaluate(() => document.body.setAttribute('data-ds-dark-theme', ''));
    await page.waitForTimeout(200);
    assert.deepEqual(await backgroundGeometry('dark'), day, `terrain framing at ${width}`);
    if (width === 390 || width === 1920) await shot(`ocean-${width}-dark.png`);
    await page.evaluate(() => document.body.removeAttribute('data-ds-dark-theme'));
    await page.waitForTimeout(200);
    if (width === 1920) await shot('ocean-wide-light.png');
    const actions = await page.locator('.anime-heading-actions button').evaluateAll((items) => items.map((e) => e.getBoundingClientRect().y));
    assert.equal(actions.length, 3);
    assert.ok(actions.every((y) => y === actions[0]), 'header tools stay on one row');
    await page.getByRole('button', { name: '插件设置', exact: true }).click();
    await page.getByRole('button', { name: '配置 qBittorrent', exact: true }).click();
    const modal = page.getByRole('dialog'); await modal.waitFor();
    assert.equal(await modal.evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true);
    const box = await modal.boundingBox(); assert.ok(box.x >= 0 && box.x + box.width <= width + 1);
    await page.keyboard.press('Escape');
    if (width === 390) await shot('ocean-mobile.png');
  }
  await page.setViewportSize({ width: 1440, height: 1040 });
  for (const state of ['empty', 'error']) { await page.goto(`${base}?state=${state}`); await ready(); await shot(`ocean-${state}.png`); }
  for (const [random, name, count] of [[.01, 'fish-silver', 3], [.4, 'fish-jade', 3], [.6, 'clownfish-orange', 1], [.995, 'whale-easter-egg', 1]]) {
    const sample = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
    await sample.addInitScript((value) => { Math.random = () => value; }, random);
    await sample.goto(base);
    await sample.locator('.anime-day-fauna').waitFor();
    assert.equal(await sample.locator('.anime-day-fauna .anime-fauna-pass').getAttribute('data-variant'), name);
    assert.equal(await sample.locator('.anime-day-fauna .anime-fauna-pass').getAttribute('data-count'), String(count));
    assert.equal(await sample.locator('.anime-day-fauna img').count(), 1, 'variants replace, never accumulate');
    await sample.close();
  }
  for (const [random, name] of [[.7, 'jelly-solmissus'], [.8, 'jelly-atolla'], [.89, 'jelly-pandea'], [.95, 'jelly-crossota'], [.99, 'jelly-phantom']]) {
    const sample = await browser.newPage({ viewport: { width: 1440, height: 1040 } });
    await sample.addInitScript((value) => { Math.random = () => value; }, random);
    await sample.goto(`${base}?theme=dark`);
    await sample.locator('.anime-night-fauna').waitFor();
    await sample.waitForFunction(() => [...document.querySelectorAll('.anime-ocean img')].every((i) => i.complete && i.naturalWidth > 0));
    assert.equal(await sample.locator('.anime-night-fauna .anime-fauna-pass').getAttribute('data-species'), name);
    assert.equal(await sample.locator('.anime-jellyfish-body:visible').count(), 1, 'one jellyfish, never five at once');
    const glow = await sample.locator('.anime-jellyfish-glow').evaluate((e) => {
      const s = getComputedStyle(e); return { opacity:Number(s.opacity), filter:s.filter, mask:s.maskImage, running:s.animationPlayState };
    });
    assert.ok(glow.opacity >= .28 && glow.opacity <= .44);
    assert.notEqual(glow.filter, 'none'); assert.notEqual(glow.mask, 'none'); assert.equal(glow.running, 'running');
    await sample.screenshot({ path: fileURLToPath(new URL(`${name}-preview.png`, output)), clip: { x: 0, y: 36, width: 1440, height: 300 } });
    await sample.close();
  }
  assert.deepEqual(errors, []);
  console.log('Ocean UI checks passed: embedded overlays, sparse day/night fauna, reusable jellyfish light, unchanged terrain, static/moving layouts, persisted motion, reduced motion, hidden lifecycle, host isolation and narrow dialogs.');
} finally { await browser.close(); }
