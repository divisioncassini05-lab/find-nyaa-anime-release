import {buildLiquidMasks, createLiquidCanvas, liquidCanvas, polygon, releaseCanvases} from './whale-liquid-mask.mjs';
import {decodeWhaleClips, closeWhaleClips} from './whale-timeline.mjs';

const clamp = value => Math.max(0, Math.min(1, value));
const ease = value => { const t = clamp(value); return t * t * t * (10 + t * (-15 + 6 * t)); };
const mix = (a, b, t) => a + (b - a) * t;
const point = (a, b, t) => a.map((value, i) => mix(value, b[i], t));
const sum = values => values.reduce((a, b) => a + b, 0);

export function liquidFrame(durations, time) {
  let i = 0;
  while (i < durations.length - 1 && time >= durations[i]) time -= durations[i++];
  return i;
}

function validTiming(durations, frames) {
  return Array.isArray(durations) && durations.length === frames && frames > 0
    && durations.every(value => Number.isFinite(value) && value > 0);
}

function validPoint(value) {
  return Array.isArray(value) && value.length === 2 && value.every(Number.isFinite);
}

function validateAction(id, {character, liquid, landmarks, palms}) {
  if (!['reading-trace', 'idle-droplet'].includes(id)) throw new Error('Unknown liquid action');
  for (const clip of [character, liquid]) {
    if (!clip?.frames || !validTiming(clip.durations, clip.frames.length)) throw new Error('Invalid liquid clip timing');
    if (clip.frames.some(frame => (frame.displayWidth ?? frame.width) !== 512
      || (frame.displayHeight ?? frame.height) !== 512)) throw new Error('Invalid liquid canvas size');
  }
  const motion = id === 'reading-trace' ? landmarks : palms;
  if (!motion || !validTiming(motion.durations, character.frames.length)
    || motion.durations.some((value, i) => value !== character.durations[i])) {
    throw new Error('Liquid landmarks do not match decoded timing');
  }
  if (!/^[a-f0-9]{64}$/.test(motion.gif_sha256 || '')
    || (character.sha256 && character.sha256 !== motion.gif_sha256)) throw new Error('Liquid landmark hash mismatch');
  const points = id === 'reading-trace' ? motion.tips : motion.palms;
  if (!Array.isArray(points) || points.length !== character.frames.length || !points.every(validPoint)) {
    throw new Error('Invalid liquid anchors');
  }
  if (id === 'reading-trace' && (!Array.isArray(motion.covers)
    || motion.covers.length !== character.frames.length
    || !motion.covers.every(cover => Array.isArray(cover) && cover.length >= 3 && cover.every(validPoint))
    || !Number.isFinite(motion.start) || !Number.isFinite(motion.end)
    || motion.start < 0 || motion.end <= motion.start || motion.end > sum(motion.durations))) {
    throw new Error('Invalid per-frame book occlusion');
  }
  if (liquid.frames.length !== 16 || liquid.durations.some(value => value !== 140)) {
    throw new Error('Unexpected native liquid timing');
  }
}

export function buildContext({createCanvas = createLiquidCanvas} = {}) {
  const layer = liquidCanvas(createCanvas);
  try {
    return {createCanvas, layer, shadow: liquidCanvas(createCanvas), action: null, disposed: false};
  } catch (error) {
    releaseCanvases([layer]);
    throw error;
  }
}

// The host owns GIF decoding and its frames. Only one action's masks are retained.
export function loadAction(state, id, assets) {
  if (state.disposed) throw new Error('Liquid context disposed');
  validateAction(id, assets);
  const {character, liquid, landmarks, palms} = assets;
  const masks = buildLiquidMasks(character, id === 'reading-trace' ? landmarks.covers : null, state.createCanvas);
  releaseAction(state);
  state.action = {id, liquid, landmarks, palms, masks, durations: [...character.durations], total: sum(character.durations)};
  return state.action;
}

export function releaseAction(state) {
  if (state.action) releaseCanvases(state.action.masks);
  state.action = null;
  for (const canvas of [state.layer, state.shadow]) {
    if (canvas.width) canvas.getContext('2d').clearRect(0, 0, 512, 512);
  }
}

export function disposeContext(state) {
  releaseAction(state);
  releaseCanvases([state.layer, state.shadow]);
  state.disposed = true;
}

// The asset wrapper supplies bundled URLs; this player owns only water frames.
export function createLiquidPlayer({sources, manifest, landmarks, palms, cancelled = () => false,
  decode = decodeWhaleClips, createCanvas} = {}) {
  const state = buildContext({createCanvas});
  let disposed = false, generation = 0, resident = null;
  const stopped = () => disposed || cancelled();
  return {
    async load(id, characterClip) {
      const ticket = ++generation;
      const stale = () => stopped() || ticket !== generation;
      if (stale()) throw new Error('Liquid load cancelled');
      const spec = Object.hasOwn(manifest.liquid.effects, id) ? manifest.liquid.effects[id] : null;
      if (!spec) {
        releaseAction(state);
        closeWhaleClips(resident); resident = null;
        return;
      }
      let next = null;
      try {
        next = await decode({[id]: sources[id]}, stale, globalThis.ImageDecoder, {[id]: spec.frames});
        if (stale()) throw new Error('Liquid load cancelled');
        loadAction(state, id, {
          character: {...characterClip, sha256: characterClip.sha256 ?? manifest.actions[id].sha256},
          liquid: next[id], landmarks, palms,
        });
        const previous = resident;
        resident = next; next = null;
        closeWhaleClips(previous);
      } finally {
        closeWhaleClips(next);
      }
    },
    draw(ctx, id, elapsed, frame) {
      return !stopped() && draw(state, ctx, id, elapsed, frame);
    },
    dispose() {
      if (disposed) return;
      disposed = true; generation++;
      disposeContext(state);
      closeWhaleClips(resident); resident = null;
    },
  };
}

function triangle(ctx, image, source, destination) {
  const [a, b, c] = source, [p, q, r] = destination;
  const det = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  if (Math.abs(det) < .001) return;
  const m0 = ((q[0] - p[0]) * (c[1] - a[1]) - (r[0] - p[0]) * (b[1] - a[1])) / det;
  const m2 = ((r[0] - p[0]) * (b[0] - a[0]) - (q[0] - p[0]) * (c[0] - a[0])) / det;
  const m1 = ((q[1] - p[1]) * (c[1] - a[1]) - (r[1] - p[1]) * (b[1] - a[1])) / det;
  const m3 = ((r[1] - p[1]) * (b[0] - a[0]) - (q[1] - p[1]) * (c[0] - a[0])) / det;
  ctx.save(); polygon(ctx, destination); ctx.clip();
  ctx.setTransform(m0, m1, m2, m3, p[0] - m0 * a[0] - m2 * a[1], p[1] - m1 * a[0] - m3 * a[1]);
  ctx.drawImage(image, 0, 0); ctx.restore();
}

// Same shallow curved-volume projection as the accepted depth player.
export function projectLiquid(x, y, pose) {
  const u = (x - 256) * pose.scale, v = (y - 256) * pose.scale;
  const z = pose.depth + v * .40, perspective = 170 / (170 + z);
  const curl = Math.sin((y / 512) * Math.PI) * Math.sin(pose.time / 280 + y / 140) * 1.1;
  return [pose.x + (u + pose.shear * v + curl) * perspective,
    pose.y + (v * pose.tilt - u * .10) * perspective - z * .12];
}

function drawVolume(ctx, clip, pose) {
  const image = clip.frames[liquidFrame(clip.durations, pose.time)];
  ctx.save(); ctx.globalAlpha = pose.alpha; ctx.filter = 'saturate(0.82)';
  const step = 64;
  for (let y = 0; y < 512; y += step) for (let x = 0; x < 512; x += step) {
    const corners = [[x, y], [x + step, y], [x + step, y + step], [x, y + step]];
    const projected = corners.map(p => projectLiquid(...p, pose));
    triangle(ctx, image, [corners[0], corners[1], corners[2]], [projected[0], projected[1], projected[2]]);
    triangle(ctx, image, [corners[0], corners[2], corners[3]], [projected[0], projected[2], projected[3]]);
  }
  ctx.restore();
}

export function palmDepthPose(spec, ms) {
  if (!Number.isFinite(ms) || ms < 220 || ms >= 4700 || ms >= sum(spec.durations)) return null;
  const age = ms - 220, frame = liquidFrame(spec.durations, ms), p = spec.palms[frame];
  const arrive = ease(age / 570), leave = ease((age - 3350) / 1130);
  const theta = -.6 + age / 690, depth = 7 * Math.sin(theta);
  const orbit = [p[0] + Math.cos(theta) * 9, p[1] - 13 + Math.sin(theta) * 3];
  const seat = [334, 394];
  let pos = point(seat, orbit, arrive);
  pos[0] += Math.sin(Math.PI * arrive) * 16;
  pos = point(pos, seat, leave); pos[0] -= Math.sin(Math.PI * leave) * 16;
  const cycle = age % 2240;
  return {x: pos[0], y: pos[1], scale: .125, tilt: .64, shear: -.24, depth, time: cycle,
    palm: p, frame, phase: age / 4480,
    alpha: ease(age / 150) * (1 - ease((age - 4240) / 240)) * ease(cycle / 130) * (1 - ease((cycle - 2080) / 160))};
}

export function inkDepthPose(ms, landmarks) {
  const {durations, tips, start, end} = landmarks;
  if (!Number.isFinite(ms) || ms < start || ms >= end) return null;
  const t = (ms - start) / (end - start), tip = tips[liquidFrame(durations, ms)];
  const phase = ease(t), depth = 8 + Math.sin(Math.PI * phase) * 5;
  return {x: tip[0] - 4 + 3 * Math.sin(t * Math.PI * 2), y: tip[1] + 4,
    scale: .096, tilt: .43, shear: -.38, depth, time: Math.min(2239, t * 2240), phase,
    alpha: ease(t / .08) * (1 - ease((t - .83) / .17))};
}

function contactShade(ctx, state, pose, mask) {
  const canvas = state.shadow, k = canvas.getContext('2d'); k.clearRect(0, 0, 512, 512);
  k.save(); k.translate(pose.palm[0], pose.palm[1] - 1); k.rotate(-.15);
  const gradient = k.createRadialGradient(0, 0, 0, 0, 0, 19);
  gradient.addColorStop(0, 'rgba(39,76,93,0.20)'); gradient.addColorStop(1, 'rgba(39,76,93,0)');
  k.scale(1, .32); k.fillStyle = gradient; k.fillRect(-20, -20, 40, 40); k.restore();
  k.globalCompositeOperation = 'destination-in'; k.drawImage(mask, 0, 0); k.globalCompositeOperation = 'source-over';
  ctx.save(); ctx.globalAlpha *= pose.alpha * .7; ctx.drawImage(canvas, 0, 0); ctx.restore();
}

// No clock, fetch, RAF or target clearing. Erasure is confined to the effect layer.
export function draw(state, ctx, id, ms, frame) {
  const action = state.action;
  if (state.disposed || !action || action.id !== id || !Number.isFinite(ms) || ms < 0 || ms >= action.total) return false;
  const index = liquidFrame(action.durations, ms);
  if (frame !== undefined && frame !== index) throw new Error('Liquid frame and clock mismatch');
  const pose = id === 'reading-trace' ? inkDepthPose(ms, action.landmarks) : palmDepthPose(action.palms, ms);
  if (!pose || pose.alpha <= 0) return false;
  const k = state.layer.getContext('2d'); k.clearRect(0, 0, 512, 512);
  drawVolume(k, action.liquid, pose);
  k.save(); k.globalCompositeOperation = 'destination-out';
  k.globalAlpha = id === 'reading-trace' ? 1 : ease((pose.depth + 1) / 5);
  k.drawImage(action.masks[index], 0, 0); k.restore();
  if (id === 'idle-droplet' && ms > 700 && ms < 4100) contactShade(ctx, state, pose, action.masks[index]);
  ctx.drawImage(state.layer, 0, 0);
  return true;
}
