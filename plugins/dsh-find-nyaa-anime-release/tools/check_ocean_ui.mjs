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
  page.on('pageerror', (error) => errors.push(error.message));
  const ready = async () => { await page.locator('.anime-panel').waitFor(); await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled); };
  const shot = async (name) => page.screenshot({ path: fileURLToPath(new URL(name, output)), fullPage: true });
  const running = async (value) => page.waitForFunction((v) => document.querySelector('.anime-ocean')?.dataset.running === String(v), value);
  await page.goto(base); await ready(); await running(true);
  assert.equal(await page.locator('.anime-ocean').getAttribute('aria-hidden'), 'true');
  assert.equal(await page.locator('.anime-ocean').evaluate((e) => getComputedStyle(e).pointerEvents), 'none');
  assert.equal(await page.locator('.anime-ocean img').evaluateAll((imgs) => imgs.length === 3 && imgs.every((i) => i.complete && i.naturalWidth > 0 && i.src.startsWith('data:image/webp'))), true);
  assert.equal(await page.locator('.anime-bubble:visible').count(), 6);
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
  assert.equal(await page.locator('.anime-bubble').first().evaluate((e) => getComputedStyle(e).animationPlayState), 'paused');
  await page.reload(); await ready(); await running(false);
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  assert.equal(await page.getByRole('switch', { name: '背景动态' }).isChecked(), false);
  await page.getByRole('switch', { name: '背景动态' }).check(); await running(true);
  await page.keyboard.press('Escape');
  await page.emulateMedia({ reducedMotion: 'reduce' }); await running(false);
  assert.equal(await page.locator('.anime-bubble').first().evaluate((e) => getComputedStyle(e).animationName), 'none');
  await page.emulateMedia({ reducedMotion: 'no-preference' }); await running(true);
  // Simulate host tab hiding without altering the production lifecycle code.
  await page.locator('.preview-content').evaluate((e) => { e.style.display = 'none'; }); await running(false);
  await page.locator('.preview-content').evaluate((e) => { e.style.display = ''; }); await running(true);
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, value: true }); document.dispatchEvent(new Event('visibilitychange')); }); await running(false);
  await page.evaluate(() => { delete document.hidden; document.dispatchEvent(new Event('visibilitychange')); }); await running(true);

  const hostStyle = await page.locator('.preview-label').evaluate((e) => ({ color: getComputedStyle(e).color, background: getComputedStyle(e).backgroundColor, height: e.offsetHeight }));
  await page.evaluate(() => document.body.setAttribute('data-ds-dark-theme', ''));
  await page.waitForTimeout(200);
  assert.equal(await page.locator('.anime-water-light').isVisible(), false);
  assert.equal(await page.locator('.anime-water-dark').isVisible(), true);
  assert.equal(await page.locator('.anime-panel').evaluate((e) => getComputedStyle(e).backgroundColor), 'rgb(16, 31, 36)');
  assert.equal(await page.getByRole('button', { name: '插件设置', exact: true }).evaluate((e) => getComputedStyle(e).backgroundColor), 'rgba(33, 59, 68, 0.93)');
  assert.deepEqual(await page.locator('.preview-label').evaluate((e) => ({ color: getComputedStyle(e).color, background: getComputedStyle(e).backgroundColor, height: e.offsetHeight })), hostStyle, 'plugin theme must not restyle host');
  await shot('ocean-desktop-dark.png');
  await page.screenshot({ path: fileURLToPath(new URL('ribbon-night.png', output)), clip: { x: 0, y: 36, width: 1440, height: 300 } });
  await page.evaluate(() => document.body.removeAttribute('data-ds-dark-theme'));
  await page.waitForTimeout(200);

  await page.locator('.anime-inbox-work').first().focus(); await page.keyboard.press('Enter');
  assert.equal(await page.locator('.anime-inbox-work').first().getAttribute('aria-expanded'), 'true');
  await shot('ocean-detail.png');
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('button', { name: '连接 Bangumi', exact: true }).click();
  await page.getByRole('dialog').waitFor();
  await shot('ocean-bangumi-config.png');
  await page.keyboard.press('Escape');
  assert.equal(await page.getByRole('dialog').count(), 0);

  for (const width of [1024, 800, 390, 320]) {
    await page.setViewportSize({ width, height: 960 });
    await page.goto(base); await ready();
    // Stress wrapping with a title long enough to span several lines on mobile.
    await page.locator('.anime-work strong').first().evaluate((e) => { e.textContent = '一个很长的作品名称：The Long Chronicle of an Underwater Journey / 新篇章'; });
    assert.equal(await page.locator('.anime-scroll').evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, `overflow at ${width}`);
    assert.equal(await page.locator('.anime-bubble:visible').count(), width <= 600 ? 3 : 6);
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
  assert.deepEqual(errors, []);
  console.log('Ocean UI checks passed: embedded assets, columns, static/moving layouts, persisted motion, reduced motion, hidden lifecycle, native dark theme, host isolation, keyboard and narrow dialogs.');
} finally { await browser.close(); }
