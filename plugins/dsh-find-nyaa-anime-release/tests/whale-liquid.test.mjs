import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {buildContext, loadAction, draw, releaseAction, disposeContext,
  createLiquidPlayer, liquidFrame, inkDepthPose, palmDepthPose, projectLiquid} from '../client/whale-liquid-depth.mjs';

const root = new URL('../assets/ocean/whale/ambient/', import.meta.url);
const json = async file => JSON.parse(await readFile(new URL(file, root), 'utf8'));
const manifest = await json('manifest.json'), arm = await json('arm-manifest.json'), palms = await json('palm-motion.json');
const trace = manifest.actions['reading-trace'];
const expectedHolds = [160,140,160,180,900,400,110,110,110,110,110,110,110,110,110,110,110,110,110,110,110,140,140,230];

function clip(spec) {
  return {sha256: spec.sha256, durations: [...spec.durations], frames: spec.durations.map(() => ({width: 512, height: 512,
    close() { throw new Error('The host owns decoded frames'); }}))};
}

function assets(id = 'reading-trace') {
  return {character: clip(manifest.actions[id]), liquid: clip(manifest.liquid.effects[id]),
    landmarks: structuredClone(arm.landmarks), palms: structuredClone(palms)};
}

function canvasFactory() {
  const canvases = [];
  const createCanvas = () => {
    const calls = [], ctx = new Proxy({calls,
      getImageData: (x, y, w, h) => ({data: new Uint8ClampedArray(w * h * 4)}),
      createRadialGradient: () => ({addColorStop() {}}),
    }, {get(target, key) { return key in target ? target[key] : (...args) => calls.push([key, ...args]); }});
    const canvas = {width: 0, height: 0, getContext: () => ctx};
    canvases.push(canvas);
    return canvas;
  };
  return {canvases, createCanvas};
}

test('accepted trace and native water bytes match the published metadata', async () => {
  assert.equal(trace.sha256, '401ecada2d6cec385bbc7bdd8ff635d72706536a1c6d207abc06fb203fa1061d');
  for (const spec of [trace, ...Object.values(manifest.liquid.effects)]) {
    const bytes = await readFile(new URL(spec.file, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), spec.sha256);
    assert.equal(bytes.readUInt16LE(6), 512); assert.equal(bytes.readUInt16LE(8), 512);
    assert.equal(spec.durations.length, spec.frames);
    assert.equal(spec.durations.reduce((a, b) => a + b, 0), spec.duration_ms);
  }
  assert.deepEqual(trace.durations, expectedHolds);
  assert.equal(trace.duration_ms, 4100); assert.equal(trace.frames, 24);
  assert.deepEqual(arm.action.durations, trace.durations);
  assert.equal(arm.action.sha256, trace.sha256);
  assert.equal(arm.landmarks.gif_sha256, trace.sha256);
  assert.deepEqual(arm.landmarks.durations, trace.durations);
  assert.equal(arm.landmarks.tips.length, 24); assert.equal(arm.landmarks.covers.length, 24);
  assert.equal(arm.landmarks.start, 500); assert.equal(arm.landmarks.end, 2050);
  assert.deepEqual(palms.durations, manifest.actions['idle-droplet'].durations);
  assert.equal(palms.gif_sha256, manifest.actions['idle-droplet'].sha256);
});

test('exact nonuniform frame boundaries include both long fingertip holds', () => {
  let time = 0;
  for (const [i, hold] of expectedHolds.entries()) {
    assert.equal(liquidFrame(expectedHolds, time), i);
    assert.equal(liquidFrame(expectedHolds, time + hold - .001), i);
    time += hold;
  }
  assert.equal(liquidFrame(expectedHolds, 4099), 23);
});

test('ink follows new tips, maps the full native texture and ends before arm recovery', () => {
  for (const time of [-1, 0, 499, 2050, 4100, NaN, Infinity]) assert.equal(inkDepthPose(time, arm.landmarks), null);
  const early = inkDepthPose(650, arm.landmarks), late = inkDepthPose(1900, arm.landmarks);
  assert.ok(early.time < late.time && late.time < 2240);
  assert.equal(early.y, arm.landmarks.tips[4][1] + 4);
  assert.deepEqual(inkDepthPose(1900, arm.landmarks), late);
});

test('palm curves have perspective narrowing, front/back depth and bounded cycles', () => {
  let near = false, far = false;
  for (let time = 220; time < 4700; time += 30) {
    const pose = palmDepthPose(palms, time);
    near ||= pose.depth < 0; far ||= pose.depth > 0;
    assert.ok(pose.alpha >= 0 && pose.alpha <= 1);
    assert.ok(pose.time >= 0 && pose.time < 2240);
  }
  assert.ok(near && far);
  const pose = palmDepthPose(palms, 1900);
  const widthAt = y => {
    const left = projectLiquid(0, y, pose), right = projectLiquid(512, y, pose);
    return Math.hypot(right[0] - left[0], right[1] - left[1]);
  };
  assert.ok(widthAt(40) - widthAt(472) > 3);
  for (const time of [-1, 219, 4700, 8000, NaN]) assert.equal(palmDepthPose(palms, time), null);
});

test('one lazy mask cache is replaced and released without closing host frames', () => {
  const {canvases, createCanvas} = canvasFactory(), state = buildContext({createCanvas});
  const old = loadAction(state, 'reading-trace', assets());
  assert.equal(old.masks.length, 24); assert.equal(canvases.length, 26);
  const next = loadAction(state, 'idle-droplet', assets('idle-droplet'));
  assert.equal(next.masks.length, 16);
  assert.ok(old.masks.every(canvas => canvas.width === 0 && canvas.height === 0));
  releaseAction(state); assert.equal(state.action, null);
  assert.ok(next.masks.every(canvas => canvas.width === 0));
  disposeContext(state); disposeContext(state);
  assert.ok(canvases.every(canvas => canvas.width === 0));
  assert.throws(() => loadAction(state, 'reading-trace', assets()), /disposed/);
});

test('bad timing, stale cover counts, missing metadata and mismatched hashes fail before mask allocation', () => {
  const {canvases, createCanvas} = canvasFactory(), state = buildContext({createCanvas});
  const mutations = [
    a => { a.landmarks = null; },
    a => { a.landmarks.covers.pop(); },
    a => { a.landmarks.durations[4] = 150; },
    a => { a.landmarks.tips[0] = [NaN, 3]; },
    a => { a.landmarks.end = 6000; },
    a => { a.character.sha256 = '0'.repeat(64); },
    a => { a.character.frames[0].width = 256; },
    a => { a.liquid.durations[0] = 80; },
  ];
  for (const mutate of mutations) {
    const value = assets(); mutate(value);
    assert.throws(() => loadAction(state, 'reading-trace', value));
  }
  assert.throws(() => loadAction(state, 'reading-think', assets()), /Unknown/);
  assert.equal(canvases.length, 2); disposeContext(state);
});

test('mask creation failure cleans partial masks and retains a usable prior action', () => {
  const factory = canvasFactory(), state = buildContext({createCanvas: factory.createCanvas});
  const previous = loadAction(state, 'idle-droplet', assets('idle-droplet'));
  let created = 0;
  state.createCanvas = () => { if (++created === 3) throw new Error('Canvas failure'); return factory.createCanvas(); };
  assert.throws(() => loadAction(state, 'reading-trace', assets()), /Canvas failure/);
  assert.equal(state.action, previous);
  assert.ok(factory.canvases.slice(-2).every(canvas => canvas.width === 0));
  disposeContext(state);
});

test('draw uses caller time without clearing the target or erasing character pixels', () => {
  const {createCanvas} = canvasFactory(), state = buildContext({createCanvas}), ctx = createCanvas().getContext('2d');
  assert.equal(draw(state, ctx, 'reading-trace', 1000), false);
  loadAction(state, 'reading-trace', assets());
  assert.equal(draw(state, ctx, 'reading-trace', 1000, 4), true);
  assert.deepEqual(ctx.calls.map(call => call[0]), ['drawImage']);
  assert.throws(() => draw(state, ctx, 'reading-trace', 1000, 20), /clock mismatch/);
  for (const time of [-1, 499, 2050, 4100, NaN]) assert.equal(draw(state, ctx, 'reading-trace', time), false);
  assert.equal(draw(state, ctx, 'idle-droplet', 1000), false);
  disposeContext(state); assert.equal(draw(state, ctx, 'reading-trace', 1000), false);
});

test('public metadata excludes preview flags, request logs and machine paths', async () => {
  const raw = await readFile(new URL('arm-manifest.json', root), 'utf8');
  const text = raw + JSON.stringify(manifest.liquid);
  assert.doesNotMatch(text, /[A-Z]:[\\/]|\/Users\/|\/home\/|localhost|127\.0\.0\.1|req_[a-f0-9]|request_id|api[_-]?key|pending_user|review_url|isolated_preview/i);
  for (const spec of Object.values(manifest.liquid.effects)) await readFile(new URL(spec.motion, root));
});

function ownedWater(id) {
  const liquid = clip(manifest.liquid.effects[id]), closed = [];
  liquid.frames.forEach((frame, i) => { frame.close = () => closed.push(i); });
  return {decoded: {[id]: liquid}, closed};
}

function playerHarness(decode) {
  const factory = canvasFactory();
  return {...factory, options: {createCanvas: factory.createCanvas, decode,
    sources: {'reading-trace': 'ink-url', 'idle-droplet': 'palm-url'}, manifest, landmarks: arm.landmarks, palms}};
}

test('host adapter loads water, releases on every dry ambient ID and owns no character frames', async () => {
  const ink = ownedWater('reading-trace'), calls = [];
  const harness = playerHarness(async (urls, cancelled, decoder, expected) => {
    calls.push({urls, expected}); assert.equal(cancelled(), false); return ink.decoded;
  });
  const player = createLiquidPlayer(harness.options), ctx = harness.createCanvas().getContext('2d');
  await player.load('reading-trace', assets().character);
  assert.deepEqual(calls, [{urls: {'reading-trace': 'ink-url'}, expected: {'reading-trace': 16}}]);
  assert.equal(player.draw(ctx, 'reading-trace', 1200, 4), true);
  for (const id of ['idle-feet', 'idle-sleeve', 'reading-think', null, 'toString']) {
    await player.load(id, {});
    assert.equal(player.draw(ctx, 'reading-trace', 1200, 4), false);
  }
  assert.equal(calls.length, 1); assert.equal(ink.closed.length, 16);
  player.dispose(); player.dispose();
  assert.equal(ink.closed.length, 16);
  assert.ok(harness.canvases.filter(c => c !== harness.canvases[2]).every(c => c.width === 0));
});

test('successful replacement closes previous water, failed preparation preserves it', async () => {
  const ink = ownedWater('reading-trace'), invalid = ownedWater('idle-droplet'), water = ownedWater('idle-droplet');
  invalid.decoded['idle-droplet'].durations[0] = 80;
  const pending = [ink.decoded, invalid.decoded, new Error('Decoder failed'), water.decoded];
  const harness = playerHarness(async () => { const next = pending.shift(); if (next instanceof Error) throw next; return next; });
  const player = createLiquidPlayer(harness.options), ctx = harness.createCanvas().getContext('2d');
  await player.load('reading-trace', assets().character);
  await assert.rejects(player.load('idle-droplet', assets('idle-droplet').character), /timing/);
  assert.equal(invalid.closed.length, 16); assert.equal(ink.closed.length, 0);
  assert.equal(player.draw(ctx, 'reading-trace', 1200, 4), true);
  await assert.rejects(player.load('idle-droplet', assets('idle-droplet').character), /Decoder failed/);
  assert.equal(ink.closed.length, 0);
  await player.load('idle-droplet', assets('idle-droplet').character);
  assert.equal(ink.closed.length, 16); assert.equal(water.closed.length, 0);
  assert.equal(player.draw(ctx, 'idle-droplet', 1900), true);
  player.dispose(); assert.equal(water.closed.length, 16);
});

test('unmount during decoding closes late water frames and does not resurrect masks', async () => {
  const ink = ownedWater('reading-trace'); let resolve, stale;
  const harness = playerHarness((urls, cancelled) => { stale = cancelled; return new Promise(done => { resolve = done; }); });
  const player = createLiquidPlayer(harness.options);
  const loading = player.load('reading-trace', assets().character);
  player.dispose(); assert.equal(stale(), true);
  resolve(ink.decoded); await assert.rejects(loading, /cancelled/);
  assert.equal(ink.closed.length, 16);
  assert.ok(harness.canvases.every(c => c.width === 0));
  assert.equal(player.draw(null, 'reading-trace', 1200), false);
  await assert.rejects(player.load('idle-sleeve', {}), /cancelled/);
});

test('external cancellation is checked after async decoding and before drawing', async () => {
  const ink = ownedWater('reading-trace'); let resolve, cancelled = false;
  const harness = playerHarness(() => new Promise(done => { resolve = done; }));
  const player = createLiquidPlayer({...harness.options, cancelled: () => cancelled});
  const loading = player.load('reading-trace', assets().character);
  cancelled = true; resolve(ink.decoded);
  await assert.rejects(loading, /cancelled/); assert.equal(ink.closed.length, 16);
  assert.equal(player.draw(null, 'reading-trace', 1200), false); player.dispose();
});

test('dry action supersedes pending water without restoring an evicted cache', async () => {
  const ink = ownedWater('reading-trace'); let resolve;
  const harness = playerHarness(() => new Promise(done => { resolve = done; }));
  const player = createLiquidPlayer(harness.options);
  const loading = player.load('reading-trace', assets().character);
  await player.load('idle-feet', {}); resolve(ink.decoded);
  await assert.rejects(loading, /cancelled/); assert.equal(ink.closed.length, 16);
  assert.equal(player.draw(null, 'reading-trace', 1200), false); player.dispose();
});

test('out-of-order water loads keep the latest successful action', async () => {
  const ink = ownedWater('reading-trace'), water = ownedWater('idle-droplet'), pending = [];
  const harness = playerHarness(() => new Promise(resolve => pending.push(resolve)));
  const player = createLiquidPlayer(harness.options), ctx = harness.createCanvas().getContext('2d');
  const first = player.load('reading-trace', assets().character), second = player.load('idle-droplet', assets('idle-droplet').character);
  pending[1](water.decoded); await second;
  pending[0](ink.decoded); await assert.rejects(first, /cancelled/);
  assert.equal(ink.closed.length, 16); assert.equal(water.closed.length, 0);
  assert.equal(player.draw(ctx, 'idle-droplet', 1900), true); player.dispose();
  assert.equal(water.closed.length, 16);
});

test('public createNativeLiquid entry bundles in memory and matches the exact host API', async () => {
  const {build} = await import('esbuild');
  const result = await build({entryPoints: [fileURLToPath(new URL('../client/whale-native-liquid.mjs', import.meta.url))],
    bundle: true, write: false, format: 'esm', platform: 'browser', loader: {'.gif': 'dataurl'}});
  const module = await import('data:text/javascript;base64,' + Buffer.from(result.outputFiles[0].contents).toString('base64'));
  const ink = ownedWater('reading-trace'), harness = playerHarness(async urls => {
    assert.ok(urls['reading-trace'].startsWith('data:image/gif;base64,')); return ink.decoded;
  });
  const player = module.createNativeLiquid({cancelled: () => false, decode: harness.options.decode, createCanvas: harness.createCanvas});
  assert.deepEqual(Object.keys(player).sort(), ['dispose', 'draw', 'load']);
  const character = assets().character; delete character.sha256;
  await player.load('reading-trace', character);
  assert.equal(player.draw(harness.createCanvas().getContext('2d'), 'reading-trace', 1200, 4), true);
  await player.load('reading-think', {}); assert.equal(ink.closed.length, 16);
  player.dispose();
});
