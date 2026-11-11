import { seeded, clamp } from './faunaMotion.mjs';
import { SeabedDetails, drawSeaweed, drawWaterlight, drawMarineSnow } from './seabedDetails.mjs';

const wrap = (n, span) => ((n % span) + span) % span;

// All motion samples the existing scene clock: pause/visibility/reduced motion stay shared.
export class WaterAtmosphere {
  constructor({ width, height, theme = 'day', seed = 73 }) {
    Object.assign(this, { width, height, theme });
    this.details = new SeabedDetails({ width, height, theme, seed: seed + 34 });
    const rng = seeded(seed), compact = width <= 600, medium = width < 1000;
    const count = (compact ? 3 : medium ? 4 : 6) - (theme === 'night' ? 1 : 0);
    this.bubbles = Array.from({ length: count }, (_, i) => ({
      x: (i + .25 + rng() * .5) / count,
      phase: (i + .28 + rng() * .04) / count,
      size: 64 + rng() * 26,
      drift: rng() * Math.PI * 2,
      beads: Array.from({ length: 3 }, (_, j) => ({
        x: (rng() - .5) * 24, y: (j - 1) * (26 + rng() * 12),
        radius: j === 1 ? 4.5 + rng() * 2.5 : 2 + rng() * 2,
        phase: rng() * Math.PI * 2,
      })),
    }));
    this.streams = Array.from({ length: compact ? 4 : medium ? 5 : 7 }, (_, i) => ({
      x: rng(), y: .22 + (i + .5) / (compact ? 4 : medium ? 5 : 7) * .64,
      length: (compact ? 70 : 125) + rng() * (compact ? 45 : 80),
      speed: 4 + rng() * 3, phase: rng() * Math.PI * 2,
    }));
  }
  frame(seconds) {
    const time = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
    const { width, height } = this, night = this.theme === 'night';
    const margin = Math.max(...this.bubbles.map(item => item.size * 2.2)) / 2 + 1;
    return {
      ...this.details.frame(time),
      bubbles: this.bubbles.map(b => {
        const h = b.size * 2.2;
        const travel = height + margin * 2;
        const y = height + margin - wrap(b.phase * travel + time * 8.5, travel);
        return { x: b.x * width + Math.sin(time * .10 + b.drift) * 13, y,
          width: b.size, height: h,
          alpha: (night ? .56 : .66) * clamp((height + h - y) / h, 0, 1) * clamp((y + h) / h, 0, 1),
          beads: b.beads.map(bead => ({ ...bead,
            x: bead.x + Math.sin(time * .6 + bead.phase) * 1.2,
            stretch: 1 + Math.sin(time * .8 + bead.phase) * .045,
          })) };
      }),
      currents: [0, 1].map(i => ({
        x: width * (i ? .73 : .27) + Math.sin(time * .035 + i * 2) * 22,
        y: height * (i ? .67 : .36) + Math.sin(time * .045 + i) * 8,
        width: Math.min(850, width * (width <= 600 ? 1.05 : .68)),
        alpha: (night ? .24 : .38) * (.88 + Math.sin(time * .07 + i) * .12),
        mirror: Boolean(i),
      })),
      streams: this.streams.map(s => ({
        x: wrap(s.x * (width + s.length * 2) + time * s.speed, width + s.length * 2) - s.length,
        y: s.y * height + Math.sin(time * .13 + s.phase) * 8,
        length: s.length, bend: Math.sin(time * .10 + s.phase) * 6,
        alpha: (night ? .20 : .18) * (.85 + Math.sin(time * .24 + s.phase) * .15),
      })),
    };
  }
}

export async function loadAtmosphereAssets(manifest) {
  const result = {};
  for (const [name, meta] of Object.entries(manifest.environment_assets)) {
    const image = new Image(); image.src = meta.asset;
    await image.decode(); result[name] = image;
  }
  return result;
}

export function drawAtmosphere(canvas, water, assets, time) {
  const ctx = canvas.getContext('2d'), ratio = canvas.width / water.width;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, water.width, water.height);
  const frame = water.frame(time);
  const night = water.theme === 'night';
  drawWaterlight(ctx, frame, night);
  drawSeaweed(ctx, frame, night);
  for (const c of frame.currents) {
    const h = c.width * assets.currents.height / assets.currents.width;
    ctx.save(); ctx.translate(c.x, c.y); ctx.scale(c.mirror ? -1 : 1, 1);
    ctx.globalAlpha = c.alpha; ctx.drawImage(assets.currents, -c.width / 2, -h / 2, c.width, h); ctx.restore();
  }
  ctx.save(); ctx.lineCap = 'round';
  ctx.strokeStyle = night ? '#9bcfd7' : '#4d95a4';
  for (const s of frame.streams) {
    for (let line = 0; line < 2; line++) {
      let last;
      for (let i = 0; i <= 24; i++) {
        const u = i / 24;
        const point = { x: s.x + u * s.length,
          y: s.y + Math.sin(u * Math.PI * 2) * (3 + line) + s.bend * Math.sin(u * Math.PI) + line * 4 };
        if (last) {
          ctx.globalAlpha = s.alpha * Math.sin(u * Math.PI) * (line ? .45 : 1);
          ctx.lineWidth = line ? .7 : 1;
          ctx.beginPath(); ctx.moveTo(last.x, last.y); ctx.lineTo(point.x, point.y); ctx.stroke();
        }
        last = point;
      }
    }
  }
  drawMarineSnow(ctx, frame, night);
  for (const b of frame.bubbles) {
    ctx.globalAlpha = b.alpha;
    ctx.drawImage(assets.bubbles, b.x - b.width / 2, b.y - b.height / 2, b.width, b.height);
    // Preserve a pixel-sized contour when the faint source texture is downscaled.
    for (const bead of b.beads) {
      const x = b.x + bead.x, y = b.y + bead.y, r = bead.radius;
      ctx.lineWidth = .9;
      ctx.strokeStyle = night ? '#9edce6' : '#4d9eaf';
      ctx.globalAlpha = b.alpha * .7;
      ctx.beginPath(); ctx.ellipse(x, y, r, r * bead.stretch, 0, 0, Math.PI * 2); ctx.stroke();
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = '#f1ffff'; ctx.globalAlpha = b.alpha;
      ctx.beginPath(); ctx.ellipse(x - .4, y - .4, r - .65, (r - .65) * bead.stretch, 0, Math.PI * 1.08, Math.PI * 1.65); ctx.stroke();
    }
  }
  ctx.restore();
}
