import { FishSchool, frameAt } from './whale-checking-fish.mjs';
import { CheckingCharacter } from './whale-checking-character.mjs';
import { drawDeparture, drawWaterGif } from './whale-checking-water.mjs';
import { closeWhaleClips, decodeWhaleClips } from './whale-timeline.mjs';

const RESULTS = new Set(['success', 'attention', 'no_update', 'cancelled']);
const OWNED_KEYS = ['enter', 'guide', 'exit', 'success', 'attention', 'birth', 'swim', 'water'];

// Shares the existing decoder and borrows idle/book; only newly decoded clips are owned.
export async function loadWhaleChecking({ sources, metadata, idle, book,
  cancelled = () => false, Decoder = globalThis.ImageDecoder, ...options }) {
  const expected = Object.fromEntries(OWNED_KEYS.map(key => [key, metadata.assets[key].frames]));
  const owned = await decodeWhaleClips(sources, cancelled, Decoder, expected);
  try {
    if (cancelled()) throw new Error('Whale unmounted');
    return new WhaleCheckingController({ ...options, metadata,
      clips: { ...owned, idle, book }, ownedClips: owned });
  } catch (error) { closeWhaleClips(owned); throw error; }
}

function drawSprite(ctx, item, clips) {
  if (item.mode === 'gather') return;
  const clip = item.mode === 'birth' ? clips.birth : clips.swim;
  const heading = Math.cos(item.angle);
  ctx.save();
  ctx.translate(item.x, item.y);
  ctx.rotate(item.angle - (heading < 0 ? Math.PI : 0));
  ctx.scale(heading >= 0 ? 1 : -1, 1);
  const dx = item.mode === 'swim' ? -7 : 0, dy = item.mode === 'swim' ? 11 : 0;
  ctx.drawImage(clip.frames[item.frame], (-256 + dx) * item.size / 512,
    (-270 + dy) * item.size / 512, item.size, item.size);
  ctx.restore();
}

// The host owns the RAF and idle gate: start only queues; update(..., {idleReady:true})
// acquires the character after reading/return/ambient has finished. Keep updating fish
// after canReturn; disposal alone releases them. update returns the accepted delta (<=100ms).
// Geometry is in fish-canvas CSS pixels: width/height, left/top/characterWidth, viewTop/viewBottom.
// drawFish uses the host's DPR transform. drawMagic owns a 768px surface, displayed at
// 1.5x the character width with -25% offsets so its (128,128) equals the character origin.
// drawCharacter borrows the external bookElapsed; it never advances or resets book time.
export class WhaleCheckingController {
  constructor({ clips, metadata, width = 1, height = 1, seed, ownedClips = null }) {
    for (const key of ['idle', 'book', ...OWNED_KEYS]) {
      const clip = clips?.[key];
      if (!clip?.frames?.length || clip.frames.length !== clip.durations?.length
        || clip.durations.some(ms => !Number.isFinite(ms) || ms <= 0)) {
        throw new Error('Invalid checking clip: ' + key);
      }
    }
    this.clips = clips;
    this.ownedClips = ownedClips;
    this.actor = new CheckingCharacter(clips, metadata);
    this.school = new FishSchool({ width, height, seed,
      birthDurations: clips.birth.durations, swimDurations: clips.swim.durations });
    this.clock = 0;
    this.nextBirth = 300;
    this.pending = false;
    this.pendingResult = null;
    this.checking = false;
    this.disposed = false;
    this.enabled = true;
    this.hidden = false;
    this.reducedMotion = false;
    this.running = true;
    this.visible = true;
    this.geometry = null;
    this.cel = this.actor.sample(0);
  }

  get active() { return !this.disposed && this.actor.state !== 'idle'; }
  get needsIdle() { return this.active || this.pending; }
  get canReturn() { return !this.needsIdle; }
  get state() { return this.actor.state; }
  get completed() { return this.actor.completed; }
  get lastResult() { return this.actor.lastResult; }

  start() {
    if (this.disposed || this.checking) return;
    this.checking = true;
    if (!this.pending) this.pendingResult = null;
    this.nextBirth = this.clock + 300;
    if (this.active) this.actor.setChecking(true, this.clock);
    else this.pending = true;
  }

  finish(result = 'cancelled') {
    if (!RESULTS.has(result)) throw new TypeError('Unknown checking result: ' + result);
    if (this.disposed) return;
    this.checking = false;
    if (this.pending) {
      // A fast result can arrive before the idle handoff. Retain it for one close.
      if (this.pendingResult === null) this.pendingResult = result;
      if (this.pendingResult === 'cancelled') this.pending = false;
      return;
    }
    this.actor.finishChecking(result, this.clock, this.formationEnd());
    this.cel = this.actor.sample(this.clock);
  }

  formationEnd() {
    return this.school.items.reduce((end, item) => item.mode === 'swim' ? end
      : Math.max(end, item.born + this.school.formationMs), this.clock);
  }

  setGeometry(value) {
    const { width, height, left, top, characterWidth, viewTop = 0, viewBottom = height } = value;
    if (![width, height, left, top, characterWidth, viewTop, viewBottom].every(Number.isFinite)
      || width <= 0 || height <= 0 || characterWidth <= 0 || viewTop < 0
      || viewBottom < viewTop || viewBottom > height) throw new TypeError('Invalid checking geometry');
    if (width !== this.school.width || height !== this.school.height) this.school.resize(width, height);
    this.school.setViewport(viewTop, viewBottom);
    this.geometry = { width, height, left, top, characterWidth, viewTop, viewBottom };
  }

  anchor() {
    const { left, top, characterWidth } = this.geometry;
    const scale = characterWidth / 512, palm = this.cel.palm;
    return { x: left + (palm.x + 65) * scale, y: top + (palm.y - 46) * scale,
      size: characterWidth * .36, left, top, width: characterWidth, scale };
  }

  update(delta, geometry = {}) {
    if (!Number.isFinite(delta) || delta < 0) throw new TypeError('Invalid checking clock');
    if (this.disposed) return 0;
    if (geometry.width !== undefined) this.setGeometry(geometry);
    this.enabled = geometry.running ?? this.enabled;
    this.hidden = geometry.hidden ?? this.hidden;
    this.reducedMotion = geometry.reducedMotion ?? this.reducedMotion;
    const running = this.enabled && !this.hidden && !this.reducedMotion;
    const visible = geometry.visible ?? this.visible;
    if (visible !== this.visible || running !== this.running) this.nextBirth = this.clock + 300;
    this.running = Boolean(running);
    this.visible = Boolean(visible);
    if (!this.running || !this.geometry) return 0;
    if (this.pending && geometry.idleReady) {
      this.pending = false;
      this.actor.setChecking(true, this.clock);
      if (this.pendingResult !== null) {
        this.actor.finishChecking(this.pendingResult, this.clock, this.formationEnd());
        this.pendingResult = null;
        if (this.checking) this.actor.setChecking(true, this.clock);
      }
      this.cel = this.actor.sample(this.clock);
    }
    // Match the reviewed player's suspension guard. Never replay a hidden-time burst.
    const step = Math.min(100, delta), previousAnchor = this.anchor();
    this.clock += step;
    // Release at the raised palm before sampling the exit's lowering hand.
    this.school.update(this.clock, previousAnchor);
    this.cel = this.actor.sample(this.clock);
    const anchor = this.anchor();
    if (this.checking && this.cel.canSummon && this.visible && this.clock >= this.nextBirth) {
      this.school.spawn(this.clock, anchor, anchor.size);
      this.nextBirth = this.clock + this.school.formationMs + 240;
    }
    for (const item of this.school.items) {
      if (item.mode !== 'swim') this.school.formation(item, this.clock, anchor);
    }
    return step;
  }

  aboveCharacter(item) {
    const { left, top, characterWidth: width } = this.geometry;
    return item.mode !== 'swim' || (item.x + item.size / 2 >= left && item.x - item.size / 2 <= left + width
      && item.y + item.size / 2 >= top && item.y - item.size / 2 <= top + width);
  }

  drawCharacter(context, bookElapsed) {
    if (!this.active || !context) return false;
    if (!Number.isFinite(bookElapsed) || bookElapsed < 0) throw new TypeError('External book clock required');
    context.clearRect(0, 0, 512, 512);
    context.drawImage(this.cel.image, 0, 0);
    context.drawImage(this.clips.book.frames[frameAt(this.clips.book.durations, bookElapsed)], 0, 0);
    return true;
  }

  drawFish(context) {
    if (this.disposed || !context || !this.geometry) return;
    context.clearRect(0, 0, this.geometry.width, this.geometry.height);
    for (const item of this.school.items) {
      if (this.aboveCharacter(item)) continue;
      drawSprite(context, item, this.clips);
      drawDeparture(context, item, this.clock);
    }
  }

  drawMagic(context) {
    if (this.disposed || !context || !this.geometry) return;
    const anchor = this.anchor();
    context.save();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, 768, 768);
    for (const item of this.school.items) {
      if (item.mode !== 'swim') {
        context.setTransform(1, 0, 0, 1, 128, 128);
        drawWaterGif(context, this.clips.water, this.clock - item.born, this.school.formationMs);
      }
      if (this.aboveCharacter(item)) {
        context.setTransform(1 / anchor.scale, 0, 0, 1 / anchor.scale,
          128 - anchor.left / anchor.scale, 128 - anchor.top / anchor.scale);
        drawSprite(context, item, this.clips);
        if (item.mode === 'swim') drawDeparture(context, item, this.clock);
      }
    }
    context.restore();
  }

  draw({ character, fish, magic, bookElapsed }) {
    const active = this.drawCharacter(character, bookElapsed);
    this.drawFish(fish);
    this.drawMagic(magic);
    return active;
  }

  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.pending = false;
    this.checking = false;
    this.school.items = [];
    closeWhaleClips(this.ownedClips);
    this.ownedClips = null;
    this.clips = null;
    this.actor.clips = null;
    this.cel = null;
  }
}
