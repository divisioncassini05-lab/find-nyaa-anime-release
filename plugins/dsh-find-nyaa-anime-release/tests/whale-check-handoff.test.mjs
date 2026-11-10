import test from 'node:test';
import assert from 'node:assert/strict';
import { WhaleAmbientTimeline } from '../client/whale-ambient-timeline.mjs';
import { WhaleCheckingController } from '../client/whale-checking.mjs';
import { WhaleCheckHandoff } from '../client/whale-check-handoff.mjs';
import { makeProfile } from '../client/whale-checking-fish.mjs';

const durations = { idle: Array(16).fill(200), receive: Array(16).fill(140),
  reading: Array(16).fill(200), return: [...Array(15).fill(150), 130] };
const actions = {
  'idle-feet': { mode: 'idle', durations: [90, 110, 200] },
  'reading-think': { mode: 'reading', durations: [150, 170, 230] },
};
const geometry = { width: 1200, height: 900, left: 820, top: 80,
  characterWidth: 150, viewTop: 0, viewBottom: 740 };
const clip = ms => ({ frames: Array.from({ length: 16 }, (_, i) => i), durations: Array(16).fill(ms / 16) });
function create() {
  const timeline = new WhaleAmbientTimeline(durations, actions, { random: () => .5 });
  const checking = new WhaleCheckingController({ seed: 17, clips: {
    idle: clip(3200), book: clip(3200), enter: clip(2400), guide: clip(3200), exit: clip(2880),
    success: clip(2560), attention: clip(4200), birth: clip(2560), swim: clip(3200), water: clip(3200),
  }, metadata: { clips: Object.fromEntries(['checking-enter', 'checking-loop', 'checking-exit'].map(key =>
    [key, { palm_anchors: Array(16).fill({ x: 327, y: 273 }) }])) } });
  return { timeline, checking, handoff: new WhaleCheckHandoff(timeline, checking) };
}
function advance(handoff, duration, options = {}) {
  let consumed = 0;
  while (duration > 0) {
    const step = Math.min(100, duration);
    consumed += handoff.advance(step, { ...geometry, ...options });
    duration -= step;
  }
  return consumed;
}
function assertParked(timeline) {
  assert.equal(timeline.parent, 'idle'); assert.equal(timeline.action, null);
  assert.equal(timeline.base.elapsed, 0); assert.equal(timeline.base.frame, 0);
  assert.equal(timeline.requested, 'idle');
}

test('reading finishes its current cycle and complete return before entering at idle', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('reading'); t.advance(3200 + 2240 + 650);
  h.start(); assert.equal(t.blocked, true); assert.equal(t.requested, 'idle');
  assert.equal(h.pending, true); assert.equal(h.active, false);
  advance(h, 2549); assert.equal(t.parent, 'reading'); assert.equal(c.active, false);
  advance(h, 1); assert.equal(t.parent, 'return'); assert.equal(t.base.elapsed, 0);
  advance(h, 2379); assert.equal(t.parent, 'return'); assert.equal(c.active, false);
  advance(h, 1); assertParked(t); assert.equal(c.state, 'enter'); assert.equal(c.actor.started, c.clock);
});

test('an in-flight receive is never skipped or reversed on a checking request', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('reading'); t.advance(3200 + 450);
  h.start(); advance(h, 1789); assert.equal(t.parent, 'receive'); assert.equal(c.active, false);
  advance(h, 1); assert.equal(t.parent, 'reading'); assert.equal(t.base.elapsed, 0);
  advance(h, 3199); assert.equal(t.parent, 'reading'); assert.equal(c.active, false);
  advance(h, 1); assert.equal(t.parent, 'return');
  advance(h, 2380); assertParked(t); assert.equal(c.state, 'enter');
});

test('even frame zero mid-idle waits for the next complete loop, ignoring a caller gate', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.advance(75); assert.equal(t.frame, 0); h.start();
  h.advance(0, { ...geometry, idleReady: true }); assert.equal(c.active, false);
  advance(h, 3124, { idleReady: true }); assert.equal(c.active, false);
  advance(h, 1); assertParked(t); assert.equal(c.state, 'enter');
});

test('a fractional boundary within one tick spends the remainder on the actor, not idle', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.advance(3176.5); const beforeBook = t.bookElapsed, beforeTotal = t.totalElapsed;
  h.start(); assert.equal(h.advance(100, geometry), 100);
  assertParked(t); assert.equal(c.clock - c.actor.started, 76.5);
  assert.equal(t.bookElapsed - beforeBook, 100); assert.equal(t.totalElapsed - beforeTotal, 100);
});

test('active idle ambient completes naturally then hands off without another idle cycle', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('idle'); t.scheduler.remaining = 0; t.advance(3200 + 57.5);
  assert.equal(t.action, 'idle-feet'); const beforeBook = t.bookElapsed;
  h.start(); assert.equal(t.action, 'idle-feet'); assert.equal(t.actionElapsed, 57.5);
  advance(h, 342.4); assert.equal(t.action, 'idle-feet'); assert.equal(c.active, false);
  advance(h, .1); assertParked(t); assert.equal(c.state, 'enter');
  assert.ok(Math.abs(t.bookElapsed - beforeBook - 342.5) < 1e-8);
});

test('active reading ambient completes, then its parent reading and return complete', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('reading'); t.advance(3200 + 2240);
  t.scheduler.remaining = 0; t.advance(3200 + 170);
  assert.equal(t.action, 'reading-think'); h.start();
  advance(h, 379); assert.equal(t.action, 'reading-think'); assert.equal(c.active, false);
  advance(h, 1); assert.equal(t.action, null); assert.equal(t.parent, 'reading'); assert.equal(c.active, false);
  advance(h, 3200); assert.equal(t.parent, 'return'); assert.equal(c.active, false);
  advance(h, 2380); assertParked(t); assert.equal(c.state, 'enter');
});

test('pending ambient is discarded while an existing action is never replaced', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('idle'); t.scheduler.remaining = 0; t.advance(200);
  assert.equal(t.pendingAction, 'idle-feet'); h.start(); assert.equal(t.pendingAction, null);
  advance(h, 3000); assertParked(t); assert.equal(c.state, 'enter');
});

test('fast success while waiting still plays only after reading-return-idle, with no fish burst', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('reading'); t.advance(3200 + 2240 + 500); h.start(); h.finish('success');
  advance(h, 5079); assert.equal(t.parent, 'return'); assert.equal(c.active, false);
  advance(h, 1); assertParked(t); assert.equal(c.actor.result, 'success');
  advance(h, 7920); assertParked(t); assert.equal(h.canReturn, true);
  assert.equal(c.completed, 1); assert.equal(c.lastResult, 'success'); assert.equal(c.school.nextId, 0);
  assert.equal(t.blocked, false);
});

test('fast cancellation still finishes the requested return without starting an actor', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.request('reading'); t.advance(3200 + 2240 + 500); h.start(); h.finish('cancelled');
  assert.equal(c.pending, false); assert.equal(h.canReturn, false);
  advance(h, 5080); assertParked(t); assert.equal(h.canReturn, true);
  assert.equal(c.completed, 0); assert.equal(c.state, 'idle'); assert.equal(t.blocked, false);
});

test('base body freezes throughout checking but external book and total time advance exactly once', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  h.start(); h.advance(0, geometry); const base = JSON.stringify(t.base);
  let elapsed = 0;
  for (let i = 0; i < 500; i++) {
    const step = i % 2 ? 16.5 : 8.25;
    assert.equal(h.advance(step, geometry), step); elapsed += step;
    assert.equal(JSON.stringify(t.base), base);
    assert.equal(t.bookElapsed, elapsed); assert.equal(t.totalElapsed, elapsed); assert.equal(c.clock, elapsed);
  }
  assert.equal(c.state, 'loop'); assert.ok(c.school.items.length > 0);
});

test('exit resumes the same idle, keeps requested idle and continues resident fish independently', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  h.start(); h.advance(0, geometry); advance(h, 6500);
  const resident = c.school.items[0]; resident.profile = makeProfile(() => .999); resident.leaveAt = c.clock + 900000;
  const count = c.school.nextId; h.finish('attention');
  while (h.active && c.clock < 30000) h.advance(100, geometry);
  assertParked(t); assert.equal(h.canReturn, true); assert.equal(c.completed, 1); assert.equal(c.lastResult, 'attention');
  const beforeX = resident.x, beforeBook = t.bookElapsed, beforeTotal = t.totalElapsed;
  advance(h, 1000); assert.equal(t.parent, 'idle'); assert.equal(t.base.elapsed, 1000);
  assert.equal(t.bookElapsed - beforeBook, 1000); assert.equal(t.totalElapsed - beforeTotal, 1000);
  assert.ok(c.school.items.includes(resident)); assert.notEqual(resident.x, beforeX); assert.equal(c.school.nextId, count);
  advance(h, 6400); assert.equal(t.parent, 'idle'); assert.equal(t.requested, 'idle');
});

test('one 100ms cap covers both sides of a handoff and inactive resident updates', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.advance(3180); const book = t.bookElapsed;
  h.start(); assert.equal(h.advance(60000, geometry), 100);
  assertParked(t); assert.equal(c.clock, 100); assert.equal(c.clock - c.actor.started, 80);
  assert.equal(t.bookElapsed, book + 100);
  const other = create(); assert.equal(other.handoff.advance(60000, geometry), 100);
  assert.equal(other.timeline.bookElapsed, 100); assert.equal(other.checking.clock, 100);
});

test('pause, hidden and reduced freeze all clocks before and during acquisition', () => {
  for (const active of [false, true]) for (const flag of ['running', 'hidden', 'reducedMotion', 'timeline']) {
    const { timeline: t, checking: c, handoff: h } = create();
    if (!active) t.advance(400);
    h.start(); h.advance(0, geometry); if (active) advance(h, 6500);
    const before = [t.bookElapsed, t.totalElapsed, t.base.elapsed, c.clock, c.state];
    if (flag === 'timeline') t.setRunning(false);
    const options = flag === 'timeline' ? {} : { [flag]: flag !== 'running' };
    assert.equal(h.advance(60000, { ...geometry, ...options }), 0);
    assert.deepEqual([t.bookElapsed, t.totalElapsed, t.base.elapsed, c.clock, c.state], before);
    if (flag === 'timeline') t.setRunning(true);
    assert.equal(h.advance(100, { ...geometry, running: true, hidden: false, reducedMotion: false }), 100);
    assert.equal(t.bookElapsed, before[0] + 100); assert.equal(c.clock, before[3] + 100);
  }
});

test('restart queues behind committed feedback without unblocking ambient or resetting book', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  h.start(); h.advance(0, geometry); advance(h, 3000); h.finish('success');
  const feedbackEnd = Math.max(c.actor.settleAt, c.actor.drainUntil) + 2880 + 80 + 2560;
  advance(h, 3000); h.start(); advance(h, feedbackEnd - c.clock);
  assertParked(t); assert.equal(c.state, 'enter'); assert.equal(c.completed, 1);
  assert.equal(t.blocked, true); assert.equal(t.bookElapsed, feedbackEnd); assert.equal(t.totalElapsed, feedbackEnd);
  h.finish('cancelled'); advance(h, 5360); assertParked(t); assert.equal(t.blocked, false);
  assert.equal(h.canReturn, true); assert.equal(c.completed, 2);
});

test('an existing ambient blocker is restored, and invalid deltas have no effects', () => {
  const { timeline: t, checking: c, handoff: h } = create();
  t.setBlocked(true); h.start(); h.advance(0, geometry); h.finish('no_update'); advance(h, 5360);
  assert.equal(t.blocked, true); assert.equal(h.canReturn, true);
  const before = [t.bookElapsed, t.totalElapsed, c.clock];
  for (const value of [NaN, Infinity, -1]) assert.throws(() => h.advance(value, geometry), /clock/);
  assert.deepEqual([t.bookElapsed, t.totalElapsed, c.clock], before);
});
