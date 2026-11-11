import { seeded, clamp } from './faunaMotion.mjs';

const wrap = (value, span) => ((value % span) + span) % span;
const TERRAIN = { width: 1536, height: 1024 };
// Anchors use the unchanged painting's coordinates, including CSS center/cover cropping.
const PLANTS = [
  { x: 48, y: 946, height: 112, count: 5 },
  { x: 475, y: 996, height: 46, count: 3 },
  { x: 1083, y: 947, height: 76, count: 4 },
  { x: 1240, y: 868, height: 102, count: 4 },
  { x: 1386, y: 905, height: 148, count: 5 },
];
const LIGHT_PATCHES = [
  [180, 960, 112, 10], [430, 991, 142, 9], [755, 985, 175, 11],
  [1005, 943, 92, 8], [1160, 921, 93, 11], [1304, 849, 102, 8],
  [1455, 803, 96, 12],
];

export function terrainFit(width, height) {
  const scale = Math.max(width / TERRAIN.width, height / TERRAIN.height);
  return { scale, x: (width - TERRAIN.width * scale) / 2, y: (height - TERRAIN.height * scale) / 2 };
}

export class SeabedDetails {
  constructor({ width, height, theme = 'day', seed = 107 }) {
    Object.assign(this, { width, height, theme });
    const rng = seeded(seed);
    this.fit = terrainFit(width, height);
    this.plants = PLANTS.flatMap((patch, p) => Array.from({ length: patch.count }, (_, i) => ({
      x: patch.x + (rng() - .5) * 10, y: patch.y + (rng() - .5) * 3,
      length: patch.height * (.64 + rng() * .38), width: 3 + rng() * 4,
      lean: (i / (patch.count - 1) - .5) * patch.height * .58,
      phase: p * .45 + rng() * 1.7, tone: i % 3,
    })));
    this.lights = LIGHT_PATCHES.map(([x, y, length, thickness], i) => ({
      x, y, length, thickness, phase: i * 1.3 + rng() * .5,
    }));
    const count = width <= 600 ? 22 : width < 1000 ? 32 : 48;
    this.snow = Array.from({ length: theme === 'night' ? Math.round(count * 1.5) : count }, (_, i) => ({
      x: rng(), y: rng(), depth: i % 3, phase: rng() * Math.PI * 2,
      size: .45 + rng() * .35 + (i % 3) * .23,
      speed: .8 + rng() * .8 + (i % 3) * .55,
    }));
  }
  frame(seconds) {
    const t = Math.max(0, Number.isFinite(seconds) ? seconds : 0);
    const { scale, x: ox, y: oy } = this.fit, night = this.theme === 'night';
    return {
      seaweed: this.plants.map(p => {
        const bend = Math.sin(t * .23 + p.x * .002) * p.length * .055;
        const spine = Array.from({ length: 13 }, (_, i) => {
          const u = i / 12;
          return {
            x: ox + (p.x + p.lean * u ** 1.15 + Math.sin(u * 4.6 + p.phase) * p.length * .13 * u + bend * u ** 1.7 +
              Math.sin(t * .43 + p.phase - u * 2.2) * p.length * .025 * u ** 1.8) * scale,
            y: oy + (p.y - p.length * u) * scale,
            halfWidth: Math.sin(u * Math.PI) ** .7 * p.width * scale * (.72 + Math.cos(u * 7 + p.phase) ** 2 * .28),
          };
        });
        return { spine, tone: p.tone, alpha: night ? .30 : .40 };
      }),
      waterlight: this.lights.map(p => ({
        x: ox + (p.x + Math.sin(t * .14 + p.phase) * 18) * scale,
        y: oy + (p.y + Math.sin(t * .18 + p.phase) * 3) * scale,
        length: p.length * scale * (1 + Math.sin(t * .12 + p.phase) * .06),
        thickness: p.thickness * scale,
        bend: Math.sin(t * .15 + p.phase) * 3 * scale,
        alpha: (night ? .035 : .19) * (.77 + Math.sin(t * .22 + p.phase) * .23),
      })),
      snow: this.snow.map(p => {
        const spanX = this.width + 24, spanY = this.height + 24;
        const x = wrap(p.x * spanX + t * p.speed * .65 + Math.sin(t * .12 + p.phase) * 5, spanX) - 12;
        const y = wrap(p.y * spanY + t * p.speed, spanY) - 12;
        const fade = clamp(Math.min(x + 6, this.width + 6 - x, y + 6, this.height + 6 - y) / 14, 0, 1);
        return { x, y, size: p.size, depth: p.depth, tilt: Math.sin(t * .35 + p.phase) * .6,
          alpha: ((night ? .25 : .15) + p.depth * .045) * fade };
      }),
    };
  }
}

function softPolygon(ctx, points) {
  const first = points[0], last = points.at(-1);
  ctx.beginPath(); ctx.moveTo((first.x + last.x) / 2, (first.y + last.y) / 2);
  for (let i = 0; i < points.length; i++) {
    const point = points[i], next = points[(i + 1) % points.length];
    ctx.quadraticCurveTo(point.x, point.y, (point.x + next.x) / 2, (point.y + next.y) / 2);
  }
  ctx.closePath();
}

export function drawSeaweed(ctx, frame, night) {
  const tones = night ? ['#508b8f', '#457c81', '#598d8d'] : ['#55a9aa', '#70b8ad', '#62aab0'];
  ctx.save();
  for (const leaf of frame.seaweed) {
    const left = leaf.spine.map(p => ({ x: p.x - p.halfWidth, y: p.y }));
    const right = leaf.spine.map(p => ({ x: p.x + p.halfWidth, y: p.y })).reverse();
    ctx.globalAlpha = leaf.alpha; ctx.fillStyle = tones[leaf.tone];
    softPolygon(ctx, [...left, ...right]); ctx.fill();
    ctx.globalAlpha = leaf.alpha * .46; ctx.strokeStyle = night ? '#94c8c4' : '#d5f1dc';
    ctx.lineWidth = .65; ctx.beginPath();
    leaf.spine.forEach((p, i) => i ? ctx.lineTo(p.x - p.halfWidth * .25, p.y) : ctx.moveTo(p.x, p.y));
    ctx.stroke();
  }
  ctx.restore();
}

export function drawWaterlight(ctx, frame, night) {
  ctx.save(); ctx.fillStyle = night ? '#9acfd8' : '#ffffe6';
  for (const light of frame.waterlight) {
    const top = [], bottom = [];
    for (let i = 0; i <= 14; i++) {
      const u = i / 14, x = light.x + (u - .5) * light.length;
      const y = light.y + Math.sin(u * Math.PI * 2) * light.bend;
      const w = Math.sin(Math.PI * u) * light.thickness * (.6 + Math.sin(u * 13) * .16);
      top.push({ x, y: y - w * .5 }); bottom.push({ x, y: y + w * .5 });
    }
    // Broad painted strokes, not sharp caustic grids or a full-screen glow.
    ctx.globalAlpha = light.alpha * .35;
    softPolygon(ctx, [...top.map(p => ({ x: p.x, y: p.y - 1.2 })), ...bottom.map(p => ({ x: p.x, y: p.y + 1.2 })).reverse()]); ctx.fill();
    ctx.globalAlpha = light.alpha;
    softPolygon(ctx, [...top, ...bottom.reverse()]); ctx.fill();
  }
  ctx.restore();
}

export function drawMarineSnow(ctx, frame, night) {
  ctx.save(); ctx.lineCap = 'round';
  for (const flake of frame.snow) {
    ctx.globalAlpha = flake.alpha;
    ctx.fillStyle = ctx.strokeStyle = night ? '#b3d3da' : '#699fa8';
    if (flake.depth < 2) {
      ctx.beginPath(); ctx.ellipse(flake.x, flake.y, flake.size, flake.size * .7, flake.tilt, 0, Math.PI * 2); ctx.fill();
    } else {
      ctx.lineWidth = flake.size * .75;
      ctx.beginPath(); ctx.moveTo(flake.x, flake.y); ctx.lineTo(flake.x + flake.tilt, flake.y + flake.size * 1.5); ctx.stroke();
    }
  }
  ctx.restore();
}
