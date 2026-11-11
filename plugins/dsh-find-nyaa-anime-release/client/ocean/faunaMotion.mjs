// Scale is relative to the seated GIRL mascot, not the whale-shaped cameo.
export const CHARACTER_REFERENCE = { desktop: 150, narrow: 132, breakpoint: 600 };
export const characterSize = width => width <= CHARACTER_REFERENCE.breakpoint ? CHARACTER_REFERENCE.narrow : CHARACTER_REFERENCE.desktop;
export const densityLimit = (width, theme) => width <= 600 ? (theme === 'night' ? 14 : 20) : width < 1000 ? (theme === 'night' ? 19 : 28) : (theme === 'night' ? 26 : 40);
const spec = (id, label, theme, style, speed, ratio, lane, shy, variants, extra = {}) =>
  ({ id, label, theme, style, speed, width: CHARACTER_REFERENCE.desktop * ratio, ratio, lane, shy, variants, school: 0, groupRange: [1,1], weight: 1, ...extra });
export const SPECIES = [
  spec('sardines', '沙丁鱼', 'day', 'school', 30, .17, [.24, .60], .7, [['fish-silver', 1]], { school: 1, groupRange: [6,10], weight: 30 }),
  spec('anchovies', '鳀鱼', 'day', 'school', 33, .14, [.28, .65], .85, [['fish-jade', 1]], { school: 1, groupRange: [6,10], weight: 22 }),
  spec('clownfish', '小丑鱼', 'day', 'reef', 22, .24, [.60, .82], .65, [['clownfish-orange', 90], ['clownfish-black', 10]], { weight: 14 }),
  spec('butterflyfish', '长吻蝶鱼', 'day', 'reef', 23, .26, [.49, .77], .75, [['butterflyfish', 1]], { weight: 10 }),
  spec('porcupinefish', '刺鲀', 'day', 'hover', 17, .30, [.46, .73], .3, [['porcupinefish', 1]], { weight: 7 }),
  spec('blue-spotted-ray', '蓝点魟', 'day', 'glide', 22, .45, [.78, .88], .15, [['blue-spotted-ray', 1]], { weight: 6 }),
  spec('seahorse', '海马', 'day', 'shelter', 10, .11, [.69, .86], .95, [['seahorse-brown', 65], ['seahorse-gold', 35]], { weight: 5 }),
  spec('octopus', '章鱼', 'day', 'crawl', 14, .32, [.82, .90], .9, [['octopus-russet', 60], ['octopus-sand', 40]], { weight: 5 }),
  spec('whale', '小鲸鱼彩蛋', 'day', 'glide', 23, .40, [.24, .49], .15, [['whale-easter-egg', 1]], { weight: 1, fantasy: true }),
  spec('lanternfish', '灯笼鱼', 'night', 'cruise', 28, .22, [.37, .70], .65, [['lanternfish', 1]], { weight: 34.8, school: .35, groupRange: [3,6] }),
  spec('hatchetfish', '斧头鱼', 'night', 'hover', 18, .20, [.38, .68], .75, [['hatchetfish', 1]], { weight: 14.4 }),
  spec('barreleye', '管眼鱼', 'night', 'hover', 12, .24, [.40, .71], .85, [['barreleye', 1]], { weight: 4.8 }),
  spec('dumbo-octopus', '小飞象章鱼', 'night', 'fin', 16, .21, [.63, .85], .55, [['dumbo-octopus', 1]], { weight: 3.6 }),
  spec('anglerfish', '鮟鱇鱼', 'night', 'hover', 12, .29, [.50, .78], .2, [['anglerfish', 1]], { weight: 2.4 }),
  spec('jelly-solmissus', '盘形水母', 'night', 'jelly', 12, .28, [.35, .76], 0, [['jelly-solmissus', 1]], { weight: 16 }),
  spec('jelly-atolla', '冠水母', 'night', 'jelly', 10, .15, [.35, .72], 0, [['jelly-atolla', 1]], { weight: 10 }),
  spec('jelly-pandea', '红纸灯笼水母', 'night', 'jelly', 11, .17, [.36, .72], 0, [['jelly-pandea', 1]], { weight: 7.2 }),
  spec('jelly-crossota', '绮丽水母', 'night', 'jelly', 9, .25, [.37, .73], 0, [['jelly-crossota', 1]], { weight: 4.8 }),
  spec('jelly-phantom', '幽灵水母', 'night', 'jelly', 8, .19, [.32, .62], 0, [['jelly-phantom', 1]], { weight: 2 }),
];
export const BY_ID = Object.fromEntries(SPECIES.map(s => [s.id, s]));
export const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
export function seeded(seed = 1) {
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t ^= t + Math.imul(t ^ t >>> 7, 61 | t); return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
export function pick(entries, rng) {
  let n = rng() * entries.reduce((sum, e) => sum + e[1], 0);
  return entries.find(e => (n -= e[1]) < 0)?.[0] ?? entries.at(-1)[0];
}
const length = v => Math.hypot(v.x, v.y);
const limited = (v, max) => { const n = length(v); return n > max ? { x: v.x * max / n, y: v.y * max / n } : v; };
const unit = (x, y) => { const n = Math.hypot(x, y) || 1; return { x: x / n, y: y / n }; };

// Reynolds-style separation/alignment/cohesion, plus predictive passing and timid retreat.
// Snapshot input means pair responses never depend on update order.
export function socialSteering(a, neighbors) {
  let x = 0, y = 0, threat = 0, count = 0, cx = 0, cy = 0, vx = 0, vy = 0;
  const jelly = a.spec.style === 'jelly';
  for (const b of neighbors) {
    if (a.id === b.id) continue;
    const dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy);
    const same = a.spec.id === b.spec.id;
    const schooling = same && a.spec.school > 0 && a.dir === b.dir;
    const gap = a.radius + b.radius + (same ? 7 : 12);
    const awareness = schooling ? gap * (a.spec.school === 1 ? 1.45 : 2.1) : gap + 22 + a.spec.shy * 75 + (b.radius > a.radius ? 22 : 0);
    const rvx = a.vx - b.vx, rvy = a.vy - b.vy;
    const closing = dx * rvx + dy * rvy < 0;
    const t = clamp(-(dx * rvx + dy * rvy) / (rvx * rvx + rvy * rvy || 1), 0, 3.4);
    const near = Math.hypot(dx + rvx * t, dy + rvy * t);
    if (d < awareness || (closing && near < gap && d < awareness * 1.5)) {
      const risk = Math.max(clamp((awareness - d) / awareness, 0, 1), closing ? clamp((gap - near) / gap, 0, 1) * .8 : 0);
      if (!same) threat = Math.max(threat, risk * a.spec.shy);
      const away = unit(dx || (a.id < b.id ? -1 : 1), dy);
      // Consistent side choice prevents head-on symmetry and alternating left/right jitter.
      const side = Math.abs(dy) > 8 ? Math.sign(dy) : (a.id < b.id ? -1 : 1);
      const agency = jelly ? .16 : 1;
      x += away.x * risk * a.spec.speed * .7 * agency;
      y += (away.y * .8 + side * (closing ? 1 : .35)) * risk * a.spec.speed * 1.5 * agency;
      if (d < gap) {
        const pressure = (gap - d) / gap;
        x += away.x * pressure * 35 * agency;
        y += (away.y || side) * pressure * 38 * agency;
      }
    }
    // Different color variants remain the same species. Other species never get chased.
    if (schooling && d < 210 && d > 4) {
      cx += b.x; cy += b.y; vx += b.vx; vy += b.vy; count++;
    }
  }
  if (count) {
    const cohesion = limited({ x: (cx / count - a.x) * .10, y: (cy / count - a.y) * .16 }, a.spec.speed * .55);
    const gather = a.spec.school * (1 - threat * .8);
    x += (cohesion.x + (vx / count - a.vx) * .50) * gather;
    y += (cohesion.y + (vy / count - a.vy) * .50) * gather;
  }
  return { x, y, threat, flockmates: count, neighborY: count ? cy / count : null };
}

export class OceanWorld {
  constructor({ width = 1440, height = 900, theme = 'day', seed = 7, auto = true, maxAnimals, available = null, safeZones = [] } = {}) {
    Object.assign(this, { width, height, theme, auto, available, safeZones });
    this.rng = seeded(seed); this.animals = []; this.time = 0; this.serial = 0; this.nextSpawn = 0;
    this.maxAnimals = maxAnimals ?? densityLimit(width, theme);
    this.densityOverride = maxAnimals;
    this.stats = { spawned: 0, exited: 0, avoidance: 0, flocking: 0 };
  }
  spawn(speciesId, options = {}) {
    const spec = BY_ID[speciesId];
    if (!spec) throw new Error(`Unknown species: ${speciesId}`);
    const variant = options.variant ?? pick(spec.variants, this.rng);
    const dir = options.dir ?? (this.rng() < .5 ? 1 : -1);
    const amount = options.count ?? spec.groupRange[0] + Math.floor(this.rng() * (spec.groupRange[1]-spec.groupRange[0]+1));
    const baseY = options.y ?? this.height * (spec.lane[0] + this.rng() * (spec.lane[1] - spec.lane[0]));
    const baseSize = spec.ratio * characterSize(this.width);
    const clustered = spec.school > 0 && amount > 1;
    const spacing = baseSize * (spec.school === 1 ? 1.3 : 1.65);
    const margin = baseSize * (clustered ? 1.4 : 2);
    const frontX = options.x ?? (dir === 1 ? -margin : this.width + margin);
    const footprint = Array.from({length: amount}, (_, i) => {
      const angle = i * 2.3999632297, spread = Math.sqrt(i);
      return { x: (Math.cos(angle) * spread - Math.sqrt(amount)) * spacing,
        y: Math.sin(angle) * spread * spacing * .85 };
    });
    // Put the leading member just beyond the edge, not a whole extra shoal-width away.
    const lead = clustered && options.x === undefined ? Math.max(...footprint.map(p => p.x)) : 0;
    const group = ++this.serial, result = [];
    for (let i = 0; i < amount && this.animals.length < this.maxAnimals; i++) {
      const size = baseSize * (spec.school === 1 ? (.88 + this.rng() * .22) : 1);
      // An irregular shoal footprint, never a rigid row or one moving group texture.
      const offsetX = clustered ? footprint[i].x - lead : -i * size * 1.35;
      const offsetY = clustered ? footprint[i].y : 0;
      const id = ++this.serial;
      const a = { id, group, spec, variant, part: spec.school === 1 ? i % 3 : null, dir, size,
        radius: size * .44 * Math.max(1, ({seahorse:2.3,'jelly-atolla':3,'jelly-pandea':2,'jelly-crossota':1.3,'jelly-phantom':3}[spec.id] ?? 1)),
        x: frontX + offsetX * dir,
        y: baseY + offsetY,
        laneY: baseY, vx: dir * spec.speed, vy: 0, born: this.time, phase: this.rng() * 10,
        age: 0, fear: 0, state: 'enter', entered: false, flockmates: 0 };
      this.animals.push(a); result.push(a); this.stats.spawned++;
    }
    return result;
  }
  resize(width, height) {
    const rx = width / this.width, ry = height / this.height;
    const scale = characterSize(width) / characterSize(this.width);
    for (const a of this.animals) { a.x *= rx; a.y *= ry; a.laneY *= ry; a.size *= scale; a.radius *= scale; }
    this.width = width; this.height = height;
    this.maxAnimals = this.densityOverride ?? densityLimit(width, this.theme);
  }
  step(seconds) {
    // Fixed substeps keep social avoidance stable at low display frame rates.
    let remaining = clamp(seconds, 0, .1);
    while (remaining > .00001) { const dt = Math.min(remaining, 1 / 60); this.tick(dt); remaining -= dt; }
  }
  tick(dt) {
    this.time += dt;
    if (this.auto && this.time >= this.nextSpawn) {
      const jellyCount = this.animals.filter(a => a.spec.style === 'jelly').length;
      let pool = SPECIES.filter(s => s.theme === this.theme && (!this.available || s.variants.some(v => this.available.has(v[0]))) && this.animals.length + s.groupRange[0] <= this.maxAnimals && (s.style !== 'jelly' || jellyCount < (this.width <= 600 ? 1 : 2)));
      const schoolingCount = this.animals.filter(a => a.spec.school > 0).length;
      const schoolTypes = SPECIES.filter(s => s.theme === this.theme && s.school > 0 && (!this.available || s.variants.some(v => this.available.has(v[0]))));
      const wantsSchool = schoolTypes.length && schoolingCount < this.maxAnimals * (this.theme === 'day' ? .55 : .40);
      // Reserve enough free space for the next shoal instead of filling every gap with loners.
      if (wantsSchool && this.maxAnimals >= Math.min(...schoolTypes.map(s => s.groupRange[0]))) pool = pool.filter(s => s.school > 0);
      if (pool.length) this.spawn(pick(pool.map(s => [s.id, s.weight]), this.rng));
      const visible = this.animals.filter(a => a.x > 0 && a.x < this.width).length;
      const sparse = visible < this.maxAnimals * .55;
      this.nextSpawn = this.time + (sparse ? 1 : this.theme === 'night' ? 3 : 2) + this.rng() * (sparse ? .8 : 2);
    }
    const snapshot = this.animals.map(a => ({ ...a }));
    for (const a of this.animals) {
      a.age += dt;
      if (a.x > a.size && a.x < this.width - a.size) a.entered = true;
      const social = socialSteering(a, snapshot);
      a.fear += (social.threat - a.fear) * (1 - Math.exp(-dt * 2));
      a.flockmates = social.flockmates;
      if (social.neighborY !== null) a.laneY += (social.neighborY - a.laneY) * dt * .045 * a.spec.school;
      if (social.threat > .12) this.stats.avoidance++;
      if (social.flockmates) this.stats.flocking++;
      const style = a.spec.style, phase = a.age + a.phase;
      let speed = a.spec.speed, lane = a.laneY, currentY = Math.sin(this.time * .13 + a.x / 520) * 2.2;
      if (style === 'school') {
        currentY += Math.sin(this.time * .22 - a.x / 180) * (a.spec.id === 'anchovies' ? 9 : 5);
        if (a.spec.id === 'sardines') speed *= .9 + .22 * Math.max(0, Math.sin(this.time * .5 - a.x / 180)) ** 4;
      }
      const edge = a.x < this.width * .15 || a.x > this.width * .85;
      // Slow species yield toward the lower edge instead of sprinting like schooling fish.
      if (['shelter', 'crawl'].includes(style) && a.fear > .12) lane = this.height * .88;
      if (style === 'hover' && a.entered && !edge) speed *= .30 + .70 * Math.pow(Math.sin(phase * .17), 4);
      if (style === 'shelter' && a.entered && !edge) speed *= .48 + .40 * Math.pow(Math.sin(phase * .20), 4);
      if (style === 'reef') { speed *= .7 + .3 * Math.sin(phase * .31) ** 2; lane += Math.sin(phase * .28) * 18; }
      if (style === 'glide') lane += Math.sin(phase * .12) * 13;
      if (style === 'crawl') speed *= .65 + .35 * Math.sin(phase * .7) ** 2;
      if (style === 'fin') lane += Math.sin(phase * .36) * 20;
      if (style === 'jelly') { speed *= .65; currentY -= 2.2 + 2 * Math.max(0, Math.sin(phase * 2.5)); }
      if (['school', 'cruise', 'reef'].includes(style)) speed *= 1 + a.fear * .38;
      let desired = { x: a.dir * speed + social.x, y: (lane - a.y) * .14 + currentY + social.y };
      // Page integration can reserve text/controls without adding obstacles to the artwork.
      for (const r of this.safeZones) {
        if (a.x > r.x - a.radius - 60 && a.x < r.x + r.width + a.radius + 60 && a.y > r.y - a.radius && a.y < r.y + r.height + a.radius) {
          desired.y += a.y < r.y + r.height / 2 ? -a.spec.speed : a.spec.speed;
        }
      }
      if (a.y < 80) desired.y += (80 - a.y) * .6;
      if (a.y > this.height - 45) desired.y -= (a.y - this.height + 45) * .6;
      // No in-view mirrored flip. Yield mainly sideways, with a low positive travel speed.
      desired.x = a.dir * Math.max(a.spec.speed * .12, a.dir * desired.x);
      desired = limited(desired, a.spec.speed * 1.75);
      const acceleration = limited({ x: (desired.x - a.vx) * 1.4, y: (desired.y - a.vy) * 1.4 }, a.spec.speed * .9);
      a.vx += acceleration.x * dt; a.vy += acceleration.y * dt;
      a.x += a.vx * dt; a.y += a.vy * dt;
      a.state = a.fear > .15 ? (['shelter', 'crawl'].includes(style) ? 'shelter' : 'yield') : social.flockmates ? 'school' : style === 'jelly' ? 'drift' : Math.abs(a.vx) < a.spec.speed * .5 ? 'hover' : 'cruise';
    }
    this.animals = this.animals.filter(a => {
      const gone = a.dir === 1 ? a.x > this.width + a.size * 2.5 : a.x < -a.size * 2.5;
      if (gone) this.stats.exited++;
      return !gone;
    });
  }
  snapshot() { return this.animals.map(({ id, spec, x, y, vx, vy, state, fear, flockmates, variant }) => ({ id, species: spec.id, variant, x, y, vx, vy, state, fear, flockmates })); }
}
