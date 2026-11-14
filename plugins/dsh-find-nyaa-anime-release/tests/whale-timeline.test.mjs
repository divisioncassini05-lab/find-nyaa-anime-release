import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {WhaleTimeline, WHALE_STAGES, WHALE_AUTO_HOLD_MS, decodeWhaleClips} from '../client/whale-timeline.mjs';

const timing = {idle: Array(16).fill(200), receive: Array(16).fill(140),
  reading: Array(16).fill(200), return: [...Array(15).fill(150), 130]};

test('four stages wrap to the same idle start; no fifth module', () => {
  const clock = new WhaleTimeline(timing);
  const idle = Math.ceil(WHALE_AUTO_HOLD_MS.idle / 3200) * 3200;
  const reading = Math.ceil(WHALE_AUTO_HOLD_MS.reading / 3200) * 3200;
  clock.advance(idle - 1); assert.equal(clock.stage, 'idle');
  clock.advance(1); assert.equal(clock.stage, 'receive'); assert.equal(clock.frame, 0);
  clock.advance(2240); assert.equal(clock.stage, 'reading'); assert.equal(clock.frame, 0);
  clock.advance(reading - 1); assert.equal(clock.stage, 'reading');
  clock.advance(1); assert.equal(clock.stage, 'return');
  clock.advance(2380); assert.equal(clock.stage, 'idle'); assert.equal(clock.frame, 0);
  assert.equal(clock.elapsed, 0); assert.deepEqual(WHALE_STAGES, ['idle', 'receive', 'reading', 'return']);
  clock.advance((idle + reading + 2240 + 2380)*20); assert.equal(clock.stage, 'idle'); assert.equal(clock.frame, 0);
});

test('latest mode request waits at a safe boundary and cannot skip a handoff', () => {
  const clock = new WhaleTimeline(timing);
  clock.advance(100); clock.request('reading'); clock.request('idle'); clock.request('reading');
  assert.equal(clock.stage, 'idle'); assert.equal(clock.elapsed, 100);
  clock.advance(3100); assert.equal(clock.stage, 'receive');
  clock.advance(100); clock.request('idle');
  clock.advance(2140); assert.equal(clock.stage, 'reading');
  clock.advance(3200); assert.equal(clock.stage, 'return');
  clock.request('reading'); clock.advance(2380); assert.equal(clock.stage, 'idle');
  clock.advance(3200); assert.equal(clock.stage, 'receive');
});

test('idle and reading can each loop indefinitely without switching', () => {
  const clock = new WhaleTimeline(timing);
  clock.request('idle'); clock.advance(3200*50); assert.equal(clock.stage, 'idle');
  clock.request('reading'); clock.advance(3200+2240+3200*50); assert.equal(clock.stage, 'reading');
  assert.equal(clock.frame, 0);
  for (const invalid of [-1, NaN, Infinity]) assert.throws(() => clock.advance(invalid));
  assert.throws(() => clock.request('fifth'));
});

test('decoder absence uses the static fallback and never requests a network asset', async () => {
  await assert.rejects(decodeWhaleClips({}, () => false, null), /Static whale fallback/);
});

test('decoder cancellation closes partially decoded frames and the decoder', async () => {
  let cancelled = false, framesClosed = 0, decodersClosed = 0;
  class FakeDecoder {
    static async isTypeSupported() { return true; }
    tracks = {ready: Promise.resolve(), selectedTrack: {frameCount: 16}};
    async decode() {
      cancelled = true;
      return {image: {displayWidth: 512, displayHeight: 512, duration: 200000,
        close() { framesClosed++; }}};
    }
    close() { decodersClosed++; }
  }
  await assert.rejects(decodeWhaleClips({idle:'data:image/gif;base64,AA=='}, () => cancelled, FakeDecoder), /Invalid whale frame/);
  assert.equal(framesClosed, 1); assert.equal(decodersClosed, 1);
});

test('shipped clips and poster match the approved hashes with unchanged masters', async () => {
  const root = new URL('../assets/ocean/whale/', import.meta.url);
  const manifest = JSON.parse(await readFile(new URL('manifest.json', root), 'utf8'));
  assert.deepEqual(manifest.module_order, WHALE_STAGES);
  assert.equal(manifest.same_idle_on_wrap, true);
  for (const [name, expected] of Object.entries(manifest.sha256)) {
    const bytes = await readFile(new URL(name, root));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), expected);
    if (name.endsWith('.gif')) {
      assert.equal(bytes.subarray(0, 6).toString(), 'GIF89a');
      assert.equal(bytes.readUInt16LE(6), 512); assert.equal(bytes.readUInt16LE(8), 512);
    }
  }
  assert.equal(manifest.sha256['idle.gif'], '64de05299cf30426b1c8c09510b83d7107946c5b5bfb97e5e948e1567f63f4d3');
  assert.equal(manifest.sha256['reading.gif'], '2a9f46dd2930b2b0493ce49801d37394c6501e8fd873b3adf73f487232074cad');
});
