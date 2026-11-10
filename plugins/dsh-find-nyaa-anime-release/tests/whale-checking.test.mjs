import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { WhaleCheckingController, loadWhaleChecking } from '../client/whale-checking.mjs';
import { makeProfile, fishClearance, frameAt } from '../client/whale-checking-fish.mjs';

const root = new URL('../assets/ocean/whale/checking/', import.meta.url);
const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
const geometry = { width: 1200, height: 1800, left: 820, top: 80,
  characterWidth: 150, viewTop: 0, viewBottom: 740, idleReady: true };
const closed = [];
function clip(id, duration) {
  return { durations: Array(16).fill(duration / 16), frames: Array.from({ length: 16 }, (_, i) =>
    ({ id, i, close() { closed.push(id); } })) };
}
function clips() {
  return { idle: clip('idle', 3200), book: clip('book', 3200),
    ...Object.fromEntries(Object.entries(manifest.assets).map(([id, asset]) => [id, clip(id, asset.duration_ms)])) };
}
const create = () => new WhaleCheckingController({ clips: clips(), metadata: manifest, seed: 17 });
function advance(c, ms, extra = {}) {
  while (ms > 0) { const step = Math.min(100, ms); c.update(step, { ...geometry, ...extra }); ms -= step; }
}
function context() {
  const calls = [];
  return { calls, save() {}, restore() {}, clearRect(...a) { calls.push(['clear', ...a]); },
    drawImage(...a) { calls.push(['image', ...a]); }, setTransform(...a) { calls.push(['transform', ...a]); },
    translate() {}, rotate() {}, scale() {}, beginPath() {}, ellipse() {}, fill() {} };
}

test('checking waits for explicit stable idle and does not take a reading/ambient canvas', () => {
  const c = create(); c.start();
  assert.equal(c.pending, true); assert.equal(c.active, false); assert.equal(c.canReturn, false);
  advance(c, 5000, { idleReady: false });
  assert.equal(c.state, 'idle'); assert.equal(c.school.nextId, 0);
  assert.equal(c.drawCharacter(context(), 5000), false);
  c.update(0, geometry);
  assert.equal(c.pending, false); assert.equal(c.active, true); assert.equal(c.state, 'enter');
  advance(c, 2399); assert.equal(c.school.nextId, 0);
  advance(c, 1); assert.equal(c.state, 'loop'); assert.equal(c.school.nextId, 1);
});

test('all four results drain, exit and return; feedback is one-shot and residents survive', () => {
  for (const result of manifest.ending.results) {
    const c = create(); c.start(); c.update(0, geometry); advance(c, 6300);
    const resident = c.school.items[0];
    resident.profile = makeProfile(() => .999); resident.leaveAt = c.clock + 900000;
    const count = c.school.nextId; c.finish(result);
    c.finish(result); const end = c.actor.drainUntil;
    advance(c, 100); c.finish('cancelled'); assert.equal(c.actor.drainUntil, end);
    const states = new Set();
    while (c.active && c.clock < 22000) { advance(c, 100); states.add(c.state); }
    assert.equal(c.state, 'idle'); assert.equal(c.canReturn, true); assert.equal(c.completed, 1);
    assert.equal(c.lastResult, result); assert.equal(c.school.nextId, count);
    assert.equal(states.has('feedback'), ['success', 'attention'].includes(result));
    assert.ok(states.has('exit')); assert.ok(c.school.items.includes(resident));
    const before = { x: resident.x, y: resident.y, frame: resident.frame };
    advance(c, 500); assert.notDeepEqual({ x: resident.x, y: resident.y, frame: resident.frame }, before);
  }
});

test('fast finish before the idle handoff is retained; pre-entry cancel can drop the request', () => {
  const c = create(); c.start(); c.finish('success'); c.finish('attention');
  advance(c, 4000, { idleReady: false }); assert.equal(c.pending, true);
  c.update(0, geometry); assert.equal(c.actor.result, 'success');
  advance(c, 9000); assert.equal(c.lastResult, 'success'); assert.equal(c.completed, 1);
  assert.equal(c.school.nextId, 0); assert.equal(c.canReturn, true);
  c.start(); c.finish(); assert.equal(c.pending, false); assert.equal(c.canReturn, true);
});

test('restart waits behind the committed outcome before and after acquisition', () => {
  for (const acquire of [false, true]) {
    const c = create(); c.start(); if (acquire) c.update(0, geometry);
    c.finish('success'); c.start(); c.update(0, geometry);
    advance(c, 7920);
    assert.equal(c.completed, 1); assert.equal(c.lastResult, 'success'); assert.equal(c.state, 'enter');
    c.finish('cancelled'); advance(c, 9000); assert.equal(c.completed, 2); assert.equal(c.canReturn, true);
  }
});

test('pause, hidden and reduced motion retain both clocks and no catch-up burst occurs', () => {
  for (const flag of ['running', 'hidden', 'reducedMotion']) {
    const c = create(); c.start(); c.update(0, geometry); advance(c, 6800);
    const now = c.clock, items = JSON.stringify(c.school.items), cel = c.cel;
    c.update(60000, { ...geometry, [flag]: flag !== 'running' });
    assert.equal(c.clock, now); assert.equal(c.cel, cel); assert.equal(JSON.stringify(c.school.items), items);
    const count = c.school.nextId;
    c.update(60000, { ...geometry, [flag]: flag === 'running' });
    assert.equal(c.clock, now + 100); assert.equal(c.school.nextId, count);
  }
});

test('offscreen character suppresses new formation while existing fish continue', () => {
  const c = create(); c.start(); c.update(0, geometry); advance(c, 7000);
  const fish = c.school.items[0], before = fish.x, count = c.school.nextId;
  advance(c, 1500, { visible: false });
  assert.equal(c.school.nextId, count); assert.notEqual(fish.x, before);
  c.update(0, { ...geometry, visible: true });
  advance(c, 299); assert.equal(c.school.nextId, count);
  advance(c, 1); assert.equal(c.school.nextId, count + 1);
});

test('book phase belongs to the host and draw calls do not advance any clock', () => {
  const c = create(); c.start(); c.update(0, geometry); advance(c, 1200);
  const ctx = context(), now = c.clock;
  c.drawCharacter(ctx, 5230);
  assert.equal(ctx.calls.at(-1)[1], c.clips.book.frames[frameAt(c.clips.book.durations, 5230)]);
  c.drawCharacter(ctx, 5230); assert.equal(c.clock, now);
  assert.throws(() => c.drawCharacter(ctx), /book clock/);
});

test('fish transfer between foreground and panel layers without scaling or duplicating sprites', () => {
  const c = create(); c.start(); c.update(0, geometry); advance(c, 4000);
  const fish = context(), magic = context(); c.drawFish(fish); c.drawMagic(magic);
  assert.equal(fish.calls.filter(a => a[0] === 'image').length, 0);
  assert.equal(magic.calls.filter(a => a[0] === 'image').length, 2);
  advance(c, 2100); const item = c.school.items[0]; item.x = 200; item.y = 160;
  fish.calls.length = magic.calls.length = 0; c.drawFish(fish); c.drawMagic(magic);
  const images = fish.calls.filter(a => a[0] === 'image');
  assert.equal(images.length, 1); assert.equal(images[0][1].id, 'swim');
  assert.equal(images[0][4], 54); assert.equal(images[0][5], 54);
  assert.equal(magic.calls.filter(a => a[0] === 'image' && a[1].id === 'swim').length, 0);
});

test('a formation releases at the raised palm even when the same update starts the exit', () => {
  const c = create(); c.start(); c.update(0, geometry); advance(c, 2500); c.finish('no_update');
  advance(c, 3300);
  const item = c.school.items[0], anchor = c.anchor();
  advance(c, 60); assert.equal(c.state, 'exit'); assert.equal(item.mode, 'swim');
  assert.ok(Math.abs(item.y - anchor.y) < 1); assert.equal(item.size, 54);
});

test('controller applies the full-sprite 70% visible-depth rule and contraction preserves phase', () => {
  const c = create(); c.start(); c.update(0, geometry); advance(c, 14000);
  const fish = c.school.items[0], frame = fish.frame, size = fish.size;
  c.update(0, { ...geometry, viewBottom: 220, visible: false });
  assert.equal(c.school.waterBottom, 154);
  for (const f of c.school.items.filter(f => f.mode === 'swim')) assert.ok(f.y + fishClearance(f.size) <= 154 + 1e-8);
  assert.equal(fish.frame, frame); assert.equal(fish.size, size);
});

test('invalid clocks, geometry and outcomes do not enter an unbounded update', () => {
  const c = create();
  for (const delta of [-1, NaN, Infinity]) assert.throws(() => c.update(delta, geometry));
  assert.throws(() => c.update(0, { ...geometry, characterWidth: 0 }));
  assert.throws(() => c.finish('unknown')); assert.equal(c.pending, false);
});

test('decode ownership closes exactly the eight new clips; shared idle/book stay usable', async () => {
  let framesClosed = 0, decodersClosed = 0;
  class Decoder {
    static async isTypeSupported() { return true; }
    tracks = { ready: Promise.resolve(), selectedTrack: { frameCount: 16 } };
    async decode() { return { image: { displayWidth: 512, displayHeight: 512, duration: 200000,
      close() { framesClosed++; } } }; }
    close() { decodersClosed++; }
  }
  closed.length = 0;
  const borrowed = clips(), sources = Object.fromEntries(Object.keys(manifest.assets).map(key => [key, 'data:image/gif;base64,AA==']));
  const c = await loadWhaleChecking({ sources, metadata: manifest, idle: borrowed.idle, book: borrowed.book, Decoder });
  assert.equal(decodersClosed, 8); assert.equal(framesClosed, 0);
  c.dispose(); c.dispose(); assert.equal(framesClosed, 128); assert.deepEqual(closed, []);
  c.start(); assert.equal(c.update(10, geometry), 0); assert.equal(c.canReturn, true);
  await assert.rejects(loadWhaleChecking({ sources, metadata: manifest, idle: null, book: borrowed.book, Decoder }));
  assert.equal(framesClosed, 256);
  await assert.rejects(loadWhaleChecking({ sources, metadata: manifest, idle: borrowed.idle,
    book: borrowed.book, Decoder, cancelled: () => true }), /unmounted/);
  assert.equal(framesClosed, 256);
});

test('asset selection matches the served current revisions and shared masters byte-for-byte', async () => {
  for (const [id, asset] of Object.entries({ ...manifest.assets, ...manifest.shared })) {
    const bytes = await readFile(new URL(asset.file, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), asset.sha256, id);
    assert.equal(bytes.subarray(0, 6).toString(), 'GIF89a');
    assert.equal(bytes.readUInt16LE(6), 512); assert.equal(bytes.readUInt16LE(8), 512);
  }
  assert.equal(manifest.assets.enter.source, 'arm-refinement-04/delivery/checking-enter.gif');
  assert.equal(manifest.assets.guide.source, 'arm-refinement-04/delivery/checking-loop.gif');
  assert.equal(manifest.assets.exit.source, 'exit-review-01/delivery/checking-exit.gif');
  assert.equal(manifest.fish.max_depth_ratio, .7);
  assert.equal(manifest.provenance.fish_motion_sha256, '69be130a60f0e109913e88eb6ce11240f488baeec0d9080077c78ec02335cc77');
  const motion = await readFile(new URL('../client/whale-checking-fish.mjs', import.meta.url), 'utf8');
  assert.equal(createHash('sha256').update(motion.replace(/\r\n/g, '\n')).digest('hex'), manifest.provenance.fish_motion_sha256);
});

test('production modules have no demo hooks, DOM ownership or background-fish dependency', async () => {
  for (const name of ['whale-checking', 'whale-checking-assets', 'whale-checking-character', 'whale-checking-fish', 'whale-checking-water']) {
    const source = await readFile(new URL('../client/' + name + '.mjs', import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(window|document|requestAnimationFrame|setInterval|IntersectionObserver|ResizeObserver)\b/);
    assert.doesNotMatch(source, /oceanFauna|OceanScene|checkingPreview|drawGathering/);
  }
});
