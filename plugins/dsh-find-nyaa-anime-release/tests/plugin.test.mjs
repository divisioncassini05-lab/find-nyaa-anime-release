import assert from 'node:assert/strict';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import * as plugin from '../index.js';

const root = fileURLToPath(new URL('../', import.meta.url));

test('native bundle has complete metadata and no install-time side effects', async () => {
  const pkg = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
  assert.equal(pkg.dsh.bundle.patch, './cordis.patch.yml');
  assert.ok(pkg.engines.dsh.includes('0.2.2-rc.1'));
  assert.equal(pkg.dsh.engines, undefined);
  for (const hook of ['preinstall', 'install', 'postinstall', 'prepare']) assert.equal(pkg.scripts[hook], undefined);
  assert.equal(pkg.dependencies, undefined);
  for (const file of ['index.js', 'cordis.patch.yml', 'icon.svg', 'LICENSE', 'locale/en.json', 'locale/zh.json',
    'skills/find-nyaa-anime-release/scripts/watch.py', 'skills/find-nyaa-anime-release/scripts/package_release.py',
    'skills/find-nyaa-anime-release/scripts/dsh_host.py']) {
    assert.ok((await stat(path.join(root, file))).isFile());
  }
  for (const locale of ['en', 'zh']) {
    const { meta } = JSON.parse(await readFile(path.join(root, 'locale', `${locale}.json`), 'utf8'));
    const detailPath = path.resolve(root, meta.detail);
    assert.ok(!path.relative(root, detailPath).startsWith('..'));
    const detail = await readFile(detailPath, 'utf8');
    for (const [, image] of detail.matchAll(/!\[[^\]]*\]\(([^)]+)\)/g)) {
      if (/^https?:/.test(image)) continue;
      const imagePath = path.resolve(path.dirname(detailPath), image);
      assert.ok((await stat(imagePath)).isFile(), image);
      assert.ok(pkg.files.some((entry) => imagePath.startsWith(path.resolve(root, entry) + path.sep)));
    }
    assert.ok(pkg.files.includes(meta.detail));
  }
});

test('provider discovers without reading full instructions and loads absolute resources', async () => {
  let provider;
  plugin.apply({ skills: { registerProvider: (make) => { provider = make(); } } });
  assert.deepEqual(plugin.inject, ['skills']);
  const [entry] = await provider.list();
  assert.equal(entry.name, 'find-nyaa-anime-release');
  assert.ok(path.isAbsolute(entry.resourceBase.path));
  assert.equal(entry.content, undefined);
  assert.equal(entry.invocation.modelInvocable, true);
  const loaded = await provider.get(entry);
  assert.ok(loaded.content.includes('dsh_doctor.py'));
  assert.ok(!loaded.content.startsWith('---'));
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(provider.get(entry, { signal: controller.signal }), { name: 'AbortError' });
});

test('real Cordis registry loads and disposes the installed skill', {
  skip: !process.env.DSH_TEST_NODE_MODULES,
}, async () => {
  const req = createRequire(path.join(path.resolve(process.env.DSH_TEST_NODE_MODULES), '../package.json'));
  const { Context } = await import(pathToFileURL(req.resolve('@deepseek-ai/cordis')).href);
  const { SkillRegistry } = await import(pathToFileURL(req.resolve('@deepseek-ai/dsh-skill')).href);
  const ctx = new Context();
  try {
    await ctx.plugin(SkillRegistry);
    const fork = ctx.plugin(plugin);
    await fork;
    const list = await ctx.skills.list();
    assert.ok(list.some((item) => item.name === plugin.name));
    const loaded = await ctx.skills.get(plugin.name);
    assert.ok(loaded.content.includes('dsh_doctor.py'));
    await fork.dispose();
    assert.ok(!(await ctx.skills.list()).some((item) => item.name === plugin.name));
  } finally {
    await ctx.fiber.dispose();
  }
});

test('bundle metadata and generated market index pass official format checks', {
  skip: !process.env.DSH_TEST_NODE_MODULES,
}, async () => {
  const req = createRequire(path.join(path.resolve(process.env.DSH_TEST_NODE_MODULES), '../package.json'));
  const { parseMarketIndex, marketInstallTarget } = await import(pathToFileURL(req.resolve('@deepseek-ai/dsh-plugin-market-index')).href);
  const pkg = JSON.parse(await readFile(path.join(root, 'package.json'), 'utf8'));
  const patch = req('yaml').parse(await readFile(path.join(root, 'cordis.patch.yml'), 'utf8'));
  assert.equal(patch[0].insert[0].name, pkg.name);
  assert.equal(patch[0].insert[0].id, plugin.name);
  assert.equal(req('semver').satisfies('0.2.2-rc.1', pkg.engines.dsh), true);
  assert.equal(req('semver').satisfies('0.3.0', pkg.engines.dsh), false);
  const result = spawnSync(process.env.PYTHON || 'python', ['-c',
    'import json; from tools.make_market_index import make_index; print(json.dumps(make_index("https://example.org/test-only/repository", "0123456789abcdef0123456789abcdef01234567", "plugins/nyaa", 1794000000)))'],
  { cwd: root, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
  const index = parseMarketIndex(JSON.parse(result.stdout), 'https://example.org/test-only/index.json');
  const entry = index.plugins[0];
  assert.equal(entry.name, pkg.name);
  assert.equal(entry.versions[0].version, pkg.version);
  assert.equal(marketInstallTarget(entry.name, entry.versions[0]).spec,
    'git+https://example.org/test-only/repository.git#0123456789abcdef0123456789abcdef01234567&path:/plugins/nyaa');
});
