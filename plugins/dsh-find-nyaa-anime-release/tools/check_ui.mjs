import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { mkdir } from 'node:fs/promises';

const req = process.env.PLAYWRIGHT_NODE_MODULES ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = req('playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
const base = process.env.UI_URL || 'http://127.0.0.1:4319';
const output = new URL('../.preview/', import.meta.url);
await mkdir(output, { recursive: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1360, height: 900 } });
  page.setDefaultTimeout(12000);
  const ready = () => page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled);
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(base); await page.getByRole('heading', { name: '动漫搜索与自动追番' }).waitFor();
  assert.equal(await page.getByRole('tab', { name: /追番收件箱/ }).getAttribute('aria-selected'), 'true');
  assert.equal(await page.getByRole('tab', { name: /Bangumi 番单/ }).getAttribute('aria-selected'), 'false');
  await page.getByRole('button', { name: '刷新番单' }).waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled);
  await page.screenshot({ path: new URL('desktop.png', output).pathname.replace(/^\/([A-Z]:)/, '$1'), fullPage: true });

  const active = page.locator('.anime-record').filter({hasText:'葬送的芙莉莲'});
  await active.locator('.anime-inbox-work').click();
  await active.locator('.anime-more-actions summary').click();
  await active.getByRole('button', { name: '现在查找一次', exact: true }).click();
  await page.getByText('本次查找已排队，原有定时安排不变').waitFor();
  assert.equal(await page.getByRole('dialog').count(), 0);
  await page.getByRole('button', { name: '调整资源要求' }).click();
  await page.getByRole('dialog', { name: '资源要求' }).waitFor();
  await page.getByLabel('必须有中文字幕').check();
  await page.getByRole('button', { name: '保存资源要求' }).click(); await ready();

  await page.getByRole('tab', { name: /Bangumi 番单/ }).click();
  await page.getByLabel('搜索番单').fill('frieren');
  assert.equal(await page.locator('.anime-row').count(), 1);
  await page.getByRole('tab', { name: /追番收件箱/ }).click();
  assert.equal(await page.getByLabel('搜索番单').inputValue(), '');
  await page.getByRole('tab', { name: /Bangumi 番单/ }).click();
  assert.equal(await page.getByLabel('搜索番单').inputValue(), 'frieren');
  await page.getByLabel('搜索番单').fill('');
  await page.locator('.anime-filter-row select').first().selectOption({ label: '剧场版' });
  assert.equal(await page.locator('.anime-row').count(), 1);
  await page.locator('.anime-filter-row select').first().selectOption('all');
  await page.getByRole('button', { name: /降序/ }).click();
  assert.equal(await page.getByRole('button', { name: /升序/ }).count(), 1);
  await page.locator('.anime-row').first().click();
  assert.ok(await page.locator('.anime-detail').count());
  await page.screenshot({ path: new URL('bangumi-desktop.png', output).pathname.replace(/^\/([A-Z]:)/, '$1'), fullPage: true });

  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('button', { name: '连接 Bangumi' }).click();
  await page.getByRole('dialog', { name: '连接 Bangumi' }).waitFor();
  assert.equal(await page.getByRole('dialog', { name: '连接 Bangumi' }).getByLabel('Access Token').getAttribute('type'), 'password');
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await page.getByRole('button', { name: '插件设置', exact: true }).click();
  await page.getByRole('button', { name: '配置 qBittorrent' }).click();
  await page.getByRole('dialog', { name: '配置 qBittorrent' }).waitFor();
  await page.getByRole('button', { name: '取消' }).click();

  for (const width of [1360, 800, 390, 320]) {
    await page.setViewportSize({ width, height: 900 }); await page.goto(`${base}?state=bangumi`); await page.locator('.anime-inbox-row').first().waitFor(); await ready();
    await page.getByRole('tab', { name: /Bangumi 番单/ }).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `page overflow at ${width}`);
    assert.equal(await page.locator('.anime-panel').evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `panel overflow at ${width}`);
    assert.equal(await page.locator('.anime-scroll').evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true, `scroll area overflow at ${width}`);
    if (width === 390) await page.screenshot({ path: new URL('mobile.png', output).pathname.replace(/^\/([A-Z]:)/, '$1'), fullPage: true });
  }
  await page.setViewportSize({ width: 1360, height: 900 }); await page.goto(`${base}?theme=dark`); await page.locator('.anime-inbox-row').first().waitFor(); await ready();
  await page.screenshot({ path: new URL('dark.png', output).pathname.replace(/^\/([A-Z]:)/, '$1'), fullPage: true });

  await page.goto(`${base}?state=empty`); await page.getByText('还没有 DSH 追番计划').waitFor();
  await page.getByRole('button', { name: '添加追番', exact: true }).click();
  await page.getByLabel('作品名', { exact: true }).fill('示例新计划');
  assert.equal(await page.getByLabel('合格后自动提交 qBittorrent').isChecked(), false);
  await page.getByRole('button', { name: '保存计划' }).click();
  await page.getByText('示例新计划', { exact: true }).waitFor();
  await page.goto(`${base}?state=offline`); await page.locator('.anime-inbox-row').first().waitFor();
  assert.equal(await page.getByRole('alert').count(), 0);
  await page.getByRole('tab', { name: /Bangumi 番单/ }).click();
  await page.getByRole('alert').waitFor();
  await page.goto(`${base}?state=error`); await page.getByRole('alert').waitFor(); assert.match(await page.getByRole('alert').innerText(), /无法读取/);
  assert.deepEqual(errors, []);
  console.log('UI checks passed: tabs, search, type filter, sorting, details, config dialogs, empty/error states and 4 viewports.');
} finally { await browser.close(); }
