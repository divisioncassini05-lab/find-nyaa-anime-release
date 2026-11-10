export function seededRandom(seed = 1) {
  let state = seed >>> 0;
  return () => {
    state += 0x6d2b79f5;
    let t = state;
    t = Math.imul(t ^ t >>> 15, t | 1);
    t ^= t + Math.imul(t ^ t >>> 7, t | 61);
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}

export class AmbientScheduler {
  constructor(pools, {random = Math.random, minimum = 25000, maximum = 45000} = {}) {
    if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum < 0 || maximum < minimum) throw new Error('Invalid interval');
    this.pools = Object.fromEntries(['idle', 'reading'].map(mode => [mode, [...(pools[mode] || [])]]));
    this.random = random; this.minimum = minimum; this.maximum = maximum;
    this.bags = {idle: [], reading: []}; this.previous = {}; this.enabled = true;
    this.reset();
  }
  reset() { this.remaining = this.minimum + this.random() * (this.maximum - this.minimum); }
  setEnabled(value) { this.enabled = Boolean(value); this.reset(); }
  advance(delta, eligible) {
    if (!Number.isFinite(delta) || delta < 0) throw new Error('Invalid delta');
    if (this.enabled && eligible) this.remaining = Math.max(0, this.remaining - delta);
  }
  get due() { return this.enabled && this.remaining === 0; }
  take(mode) {
    if (!this.due || !this.pools[mode]?.length) return null;
    if (!this.bags[mode].length) {
      const bag = [...this.pools[mode]];
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(this.random() * (i + 1)); [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      if (bag.length > 1 && bag[0] === this.previous[mode]) [bag[0], bag[1]] = [bag[1], bag[0]];
      this.bags[mode] = bag;
    }
    const id = this.bags[mode].shift(); this.previous[mode] = id; this.reset(); return id;
  }
}
