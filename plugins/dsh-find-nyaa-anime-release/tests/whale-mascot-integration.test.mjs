import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';
import { closeWhaleClips } from '../client/whale-timeline.mjs';
import { WhaleAmbientTimeline, clipFrame } from '../client/whale-ambient-timeline.mjs';
import { WhaleCheckingController } from '../client/whale-checking.mjs';
import { WhaleCheckHandoff } from '../client/whale-check-handoff.mjs';
import { ReadingRetreatHandoff } from '../client/whale-reading-handoff.mjs';

const source = await readFile(new URL('../client/WhaleMascot.jsx', import.meta.url), 'utf8');
const { code } = await transform(source, { loader: 'jsx', format: 'cjs' });
const metadata = JSON.parse(await readFile(new URL('../assets/ocean/whale/checking/manifest.json', import.meta.url), 'utf8'));
const ambient = JSON.parse(await readFile(new URL('../assets/ocean/whale/ambient/manifest.json', import.meta.url), 'utf8'));
const clip = (ms, count = 16) => ({ durations: Array(count).fill(ms / count),
  frames: Array.from({ length: count }, () => ({ close() {} })) });
const defer = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const settle = () => new Promise(resolve => setImmediate(resolve));

// Only hooks, canvas drawing and scheduling are faked. Run the actual component,
// signal handler, loading continuation, timeline and checking controller together.
function mount() {
  const baseLoad = defer(), checkingLoad = defer(), retreatLoad=defer(), raf = new Map(), hooks = [];
  let cursor = 0, effects = [], rafId = 0, now = 0, checkingOptions;
  let props = { running: true, visible: true, check: { checking: false } };
  const harness = { hasGeometry: true, loads: 0, retreatLoads:0 };
  const context = () => Object.fromEntries(['clearRect', 'drawImage', 'save', 'restore', 'translate',
    'rotate', 'scale', 'setTransform', 'beginPath', 'ellipse', 'fill'].map(name => [name, () => {}]));
  const panel = { append() {}, getBoundingClientRect: () => ({ left: 0, top: 0, width: 1200, height: 900 }) };
  function element() {
    const ctx = context();
    return { dataset: {}, setAttribute() {}, remove() {}, getContext: () => ctx, closest: () => panel,
      getBoundingClientRect: () => ({ left: 820, top: 80, width: harness.hasGeometry ? 150 : 0, height: 150 }) };
  }
  const react = {
    createElement(type, attributes, ...children) { return { type, props: attributes || {}, children }; },
    useRef(value) { const i = cursor++; return (hooks[i] ??= { current: value }); },
    useState(value) {
      const i = cursor++; hooks[i] ??= { value };
      return [hooks[i].value, next => { hooks[i].value = next; }];
    },
    useEffect(effect, deps) {
      const i = cursor++, previous = hooks[i];
      if (!previous || deps.some((value, n) => !Object.is(value, previous.deps[n]))) {
        const entry = hooks[i] = { deps, cleanup: previous?.cleanup };
        effects.push(() => { entry.cleanup?.(); entry.cleanup = effect(); });
      }
    },
  };
  const modules = {
    react,
    './whale-reading-handoff.mjs': {ReadingRetreatHandoff:class extends ReadingRetreatHandoff {
      constructor(...args){super(...args);harness.retreat=this;}
    }},
    './whale-reading-retreat.mjs': {prepareReadingRetreat:()=>{harness.retreatLoads++;return retreatLoad.promise;}},
    './whale-timeline.mjs': { closeWhaleClips, decodeWhaleClips: () => baseLoad.promise },
    './whale-ambient-timeline.mjs': { clipFrame, WhaleAmbientTimeline: class extends WhaleAmbientTimeline {
      constructor(...args) { super(...args); harness.timeline = this; }
    } },
    './whale-check-handoff.mjs': { WhaleCheckHandoff: class extends WhaleCheckHandoff {
      constructor(...args) { super(...args); harness.handoff = this; }
    } },
    './whale-native-liquid.mjs': { createNativeLiquid: () => ({ load: async () => {}, draw() {}, dispose() {} }) },
    './whale-checking-assets.mjs': { prepareWhaleChecking(options) {
      checkingOptions = options; harness.loads++; return checkingLoad.promise;
    } },
  };
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports,
    require(id) {
      if (id in modules) return modules[id];
      if (id.endsWith('/manifest.json')) return ambient;
      if (/\.(gif|png)$/.test(id)) return id;
      throw new Error('Unexpected component dependency: ' + id);
    },
    document: { createElement: element }, window: { devicePixelRatio: 1, innerHeight: 900 },
    requestAnimationFrame(fn) { raf.set(++rafId, fn); return rafId; },
    cancelAnimationFrame(id) { raf.delete(id); }, clearTimeout() {}, setTimeout() { return 1; },
  });
  function attachRefs(node) {
    if (!node || typeof node !== 'object') return;
    if (node.props.ref && !node.props.ref.current) node.props.ref.current = element();
    for (const child of node.children) attachRefs(child);
  }
  harness.render = changes => {
    props = { ...props, ...changes }; cursor = 0; effects = [];
    const tree=module.exports.WhaleMascot(props);
    attachRefs(tree);
    function findClick(node){if(!node||typeof node!=='object')return;
      if(node.props.onClick)harness.click=node.props.onClick;
      for(const child of node.children)findClick(child);
    }
    findClick(tree);
    for (const effect of effects) effect();
  };
  harness.signal = (checking, result = null) => harness.render({ check: { checking, result } });
  harness.baseReady = async () => {
    baseLoad.resolve({ idle: clip(3200), book: clip(3200), receive: clip(2240), reading: clip(3200), return: clip(2380) });
    await settle();
  };
  harness.checkingReady = async () => {
    assert.ok(checkingOptions, 'checking decode was requested');
    const clips = { idle: checkingOptions.idle, book: checkingOptions.book,
      ...Object.fromEntries(Object.entries(metadata.assets).map(([key, asset]) => [key, clip(asset.duration_ms)])) };
    harness.checking = new WhaleCheckingController({ clips, metadata, seed: 17 });
    checkingLoad.resolve(harness.checking); await settle();
  };
  harness.retreatReady=async()=>{
    retreatLoad.resolve({durations:{reading:Array(16).fill(200),character:[...Array(16).fill(110),...Array(16).fill(140)],
      rise:Array(16).fill(120),hold:Array(16).fill(180),reveal:Array(16).fill(180),recover:Array(16).fill(220)},
      drawCharacter(){},drawMagic(){},dispose(){harness.retreatDisposed=true;}});
    await settle();
  };
  harness.tick = delta => {
    now += delta;
    const scheduled = [...raf]; raf.clear();
    assert.equal(scheduled.length, 1, 'one animation loop');
    scheduled[0][1](now);
  };
  harness.advance = duration => {
    while (duration > 0) { const step = Math.min(100, duration); harness.tick(step); duration -= step; }
  };
  harness.dispose = () => { for (const hook of hooks) hook?.cleanup?.(); };
  harness.render({});
  return harness;
}

test('first decode retains committed success, then starts the latest request after feedback', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady();
  h.signal(true); h.signal(false, 'success'); h.signal(true);
  assert.equal(h.loads, 1); await h.checkingReady(); h.tick(0);
  assert.equal(h.checking.actor.result, 'success'); assert.equal(h.checking.actor.wanted, true);
  h.advance(5360); assert.equal(h.checking.state, 'feedback');
  assert.equal(h.checking.completed, 0); assert.equal(h.checking.school.nextId, 0);
  h.advance(2559); assert.equal(h.checking.state, 'feedback');
  h.advance(1); assert.equal(h.checking.completed, 1); assert.equal(h.checking.lastResult, 'success');
  assert.equal(h.checking.state, 'enter'); assert.equal(h.timeline.base.elapsed, 0);
  assert.equal(h.timeline.bookElapsed, 7920); assert.equal(h.timeline.totalElapsed, 7920);
  h.advance(2400); assert.equal(h.checking.state, 'loop'); assert.equal(h.checking.school.nextId, 1);
});

test('signals received during base decode also retain success before a queued restart', async t => {
  const h = mount(); t.after(h.dispose);
  h.signal(true); h.signal(false, 'success'); h.signal(true);
  assert.equal(h.loads, 0); await h.baseReady(); assert.equal(h.loads, 1);
  await h.checkingReady(); h.tick(0); h.advance(7920);
  assert.equal(h.checking.lastResult, 'success'); assert.equal(h.checking.completed, 1);
  assert.equal(h.checking.state, 'enter'); assert.equal(h.timeline.blocked, true);
});

test('later stop cancels a queued restart without replacing the first committed result', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady();
  h.signal(true); h.signal(false, 'success'); h.signal(true); h.signal(false, 'attention');
  await h.checkingReady(); h.tick(0); h.advance(7920);
  assert.equal(h.checking.lastResult, 'success'); assert.equal(h.checking.completed, 1);
  assert.equal(h.checking.state, 'idle'); assert.equal(h.timeline.blocked, false);
  assert.equal(h.checking.school.nextId, 0);
  h.signal(true); h.tick(0); assert.equal(h.checking.actor.result, null);
  assert.equal(h.checking.state, 'enter'); assert.equal(h.loads, 1);
});

test('preload cancel followed by restart does not manufacture an obsolete result gesture', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady();
  h.signal(true); h.signal(false, 'cancelled'); h.signal(true);
  await h.checkingReady(); h.tick(0); h.advance(2400);
  assert.equal(h.checking.state, 'loop'); assert.equal(h.checking.actor.ending, false);
  assert.equal(h.checking.completed, 0); assert.equal(h.checking.school.nextId, 1);
});

test('geometry loss never advances a body owned by the handoff, including its final idle frame', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady();
  h.signal(true); await h.checkingReady(); h.tick(0); h.advance(6500);
  h.signal(false, 'no_update');
  const before = [h.timeline.base.elapsed, h.timeline.bookElapsed, h.timeline.totalElapsed,
    h.checking.clock, h.checking.state, JSON.stringify(h.checking.school.items)];
  h.hasGeometry = false; h.tick(60000); h.tick(16);
  assert.deepEqual([h.timeline.base.elapsed, h.timeline.bookElapsed, h.timeline.totalElapsed,
    h.checking.clock, h.checking.state, JSON.stringify(h.checking.school.items)], before);
  h.hasGeometry = true; h.tick(16);
  assert.equal(h.timeline.base.elapsed, 0); assert.equal(h.timeline.bookElapsed, before[1] + 16);
  assert.equal(h.checking.clock, before[3] + 16);
  for (let i = 0; i < 150 && h.handoff.needsIdle; i++) h.tick(100);
  assert.equal(h.handoff.canReturn, true); assert.equal(h.timeline.base.elapsed, 0);
  assert.equal(h.timeline.parent, 'idle'); assert.equal(h.timeline.requested, 'idle');
});

test('geometry loss during pending reading handoff cannot bypass the complete return', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady(); h.tick(0);
  h.timeline.request('reading'); h.advance(5840);
  assert.equal(h.timeline.parent, 'reading'); assert.equal(h.timeline.base.elapsed, 400);
  h.signal(true); await h.checkingReady(); h.hasGeometry = false;
  const book = h.timeline.bookElapsed; h.advance(1000);
  assert.equal(h.timeline.base.elapsed, 400); assert.equal(h.timeline.bookElapsed, book);
  assert.equal(h.checking.active, false);
  h.hasGeometry = true; h.advance(2800);
  assert.equal(h.timeline.parent, 'return'); assert.equal(h.checking.active, false);
  h.advance(2380); assert.equal(h.timeline.parent, 'idle'); assert.equal(h.timeline.base.elapsed, 0);
  assert.equal(h.checking.state, 'enter');
});

test('inactive offscreen path still updates resident fish without advancing book or body', async t => {
  const h = mount(); t.after(h.dispose); await h.baseReady();
  h.signal(true); await h.checkingReady(); h.tick(0); h.advance(6500); h.signal(false, 'no_update');
  for (let i = 0; i < 150 && h.handoff.needsIdle; i++) h.tick(100);
  assert.equal(h.handoff.canReturn, true); assert.ok(h.checking.school.items.length);
  const before = [h.timeline.base.elapsed, h.timeline.bookElapsed, h.timeline.totalElapsed];
  const clock = h.checking.clock, fish = JSON.stringify(h.checking.school.items);
  h.render({ visible: false }); h.advance(500);
  assert.deepEqual([h.timeline.base.elapsed, h.timeline.bookElapsed, h.timeline.totalElapsed], before);
  assert.equal(h.checking.clock, clock + 500); assert.notEqual(JSON.stringify(h.checking.school.items), fish);
});

test('reading triple-click loads one branch and queued checking waits for reveal and the full original return',async t=>{
 const h=mount();t.after(h.dispose);await h.baseReady();h.tick(0);h.timeline.request('reading');h.advance(6100);
 assert.equal(h.timeline.parent,'reading');h.click();h.advance(80);h.click();h.advance(80);h.click();
 assert.equal(h.retreatLoads,1);await h.retreatReady();h.advance(3000);
 assert.equal(h.retreat.actor.stage,'character');const book=h.timeline.bookElapsed;
 h.signal(true);h.signal(false,'success');assert.equal(h.loads,0);assert.equal(h.retreat.busy,true);
 for(let i=0;i<180&&h.retreat.busy;i++)h.tick(100);
 assert.equal(h.retreat.completed,1);assert.equal(h.loads,1);assert.ok(h.timeline.bookElapsed>book);
 await h.checkingReady();h.advance(1);assert.equal(h.checking.active,false);
 assert.equal(h.timeline.parent,'reading');h.advance(5600);
 assert.equal(h.timeline.parent,'idle');assert.equal(h.checking.active,true);assert.equal(h.checking.actor.result,'success');
});
test('late retreat decode after unmount closes assets instead of resurrecting the character',async()=>{
 const h=mount();await h.baseReady();h.tick(0);h.timeline.request('reading');h.advance(6100);
 h.click();h.advance(80);h.click();h.advance(80);h.click();assert.equal(h.retreatLoads,1);
 h.dispose();await h.retreatReady();assert.equal(h.retreatDisposed,true);
});
