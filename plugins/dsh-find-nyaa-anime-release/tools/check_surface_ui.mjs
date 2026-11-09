import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const req = process.env.PLAYWRIGHT_NODE_MODULES ? createRequire(path.join(process.env.PLAYWRIGHT_NODE_MODULES, '../package.json')) : createRequire(import.meta.url);
const { chromium } = req('playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) });
const base = process.env.UI_URL || 'http://127.0.0.1:4319';
const output = new URL('../.preview/', import.meta.url);
const luminance = (hex) => {
  const full = hex.length === 4 ? `#${[...hex.slice(1)].map((c) => c + c).join('')}` : hex;
  const rgb = [1, 3, 5].map((i) => parseInt(full.slice(i, i + 2), 16) / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
};
const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05) / (Math.min(luminance(a), luminance(b)) + 0.05);
try {
  for (const theme of ['light', 'dark']) {
    for (const width of [1440, 800, 390, 320]) {
      const page = await browser.newPage({ viewport: { width, height: 1040 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(`${base}?theme=${theme}`);
      await page.locator('.anime-inbox-row').first().waitFor();
      await page.waitForFunction(() => !document.querySelector('button[aria-label="刷新番单"]')?.disabled);
      const tokens = await page.locator('.anime-panel').evaluate((e) => {
        const style = getComputedStyle(e);
        return Object.fromEntries(['fg', 'muted', 'modal', 'input', 'accent', 'soft', 'on-accent', 'lilac'].map((key) => [key, style.getPropertyValue(`--ap-${key}`).trim()]));
      });
      for (const [fg, bg] of [['fg', 'input'], ['muted', 'modal'], ['accent', 'soft'], ['on-accent', 'accent'], ['lilac', 'modal']]) {
        assert.ok(contrast(tokens[fg], tokens[bg]) >= 4.5, `${theme}: ${fg} / ${bg} must retain readable contrast`);
      }
      const checkDialog = async (name) => {
        const modal = page.getByRole('dialog');
        assert.equal(await modal.evaluate((e) => e.scrollWidth <= e.clientWidth + 1), true, `${name} overflow ${width}/${theme}`);
        const bounds = await modal.boundingBox();
        assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
        const clipped = await modal.locator('input, select, button').evaluateAll((nodes) => nodes.filter((e) => {
          if (!e.getClientRects().length) return false;
          const box = e.getBoundingClientRect(), root = e.closest('[role=dialog]').getBoundingClientRect();
          return box.x < root.x - 1 || box.right > root.right + 1;
        }).map((e) => e.getAttribute('aria-label') || e.textContent || e.type));
        assert.deepEqual(clipped, [], `${name}: controls stay inside dialog`);
        if (width === 1440 || (width === 390 && theme === 'light')) {
          await modal.evaluate((e) => { e.scrollTop = 0; });
          await page.screenshot({ path: fileURLToPath(new URL(`surface-${name}-${width}-${theme}.png`, output)) });
        }
      };
      await page.getByRole('button', { name: '添加追番', exact: true }).click();
      await page.getByLabel('作品名', { exact: true }).fill('示例作品 / A Long Underwater Chronicle');
      await page.getByRole('combobox', { name: '执行方式', exact: true }).selectOption('weekly');
      await page.getByRole('checkbox', { name: '周一', exact: true }).uncheck();
      await page.getByRole('checkbox', { name: '周五', exact: true }).check();
      await checkDialog('plan');
      await page.keyboard.press('Escape');
      for (const [name, title] of [['bangumi', '连接 Bangumi'], ['qb', '配置 qBittorrent']]) {
        await page.getByRole('button', { name: '插件设置', exact: true }).click();
        await page.getByRole('button', { name: title, exact: true }).click();
        await checkDialog(name);
        await page.keyboard.press('Escape');
      }
      assert.deepEqual(errors, []);
      await page.close();
    }
  }
  console.log('Surface UI passed: 2 themes x 4 viewports, grouped forms, weekly checkbox hitboxes, modal bounds and 4.5:1 text contrast. No real account writes.');
} finally { await browser.close(); }
