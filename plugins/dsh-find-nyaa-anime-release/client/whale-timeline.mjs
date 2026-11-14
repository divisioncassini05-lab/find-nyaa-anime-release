export const WHALE_STAGES = ['idle', 'receive', 'reading', 'return'];
// Hold stable poses in real animation time; clip length is not a rest interval.
export const WHALE_AUTO_HOLD_MS = Object.freeze({idle: 60000, reading: 90000});

// All requests take effect at complete clip boundaries, never halfway through a handoff.
export class WhaleTimeline {
  constructor(durations) {
    this.durations = durations;
    for (const stage of WHALE_STAGES) {
      if (!Array.isArray(durations[stage]) || !durations[stage].length
        || durations[stage].some((value) => !Number.isFinite(value) || value <= 0)) {
        throw new Error('Invalid whale clip timing');
      }
    }
    this.totals = Object.fromEntries(WHALE_STAGES.map((stage) =>
      [stage, durations[stage].reduce((sum, value) => sum + value, 0)]));
    this.stage = 'idle';
    this.elapsed = 0;
    this.totalElapsed = 0;
    this.loops = 0;
    this.requested = 'auto';
  }

  request(mode) {
    if (!['auto', 'idle', 'reading'].includes(mode)) throw new Error('Invalid whale mode');
    this.requested = mode;
  }

  advance(delta) {
    if (!Number.isFinite(delta) || delta < 0) throw new Error('Invalid whale clock');
    this.elapsed += delta;
    this.totalElapsed += delta;
    while (this.elapsed >= this.totals[this.stage]) {
      this.elapsed -= this.totals[this.stage];
      this.loops++;
      let next = this.stage;
      if (this.stage === 'idle' && (this.requested === 'reading'
        || (this.requested === 'auto' && this.loops * this.totals.idle >= WHALE_AUTO_HOLD_MS.idle))) next = 'receive';
      else if (this.stage === 'receive') next = 'reading';
      else if (this.stage === 'reading' && (this.requested === 'idle'
        || (this.requested === 'auto' && this.loops * this.totals.reading >= WHALE_AUTO_HOLD_MS.reading))) next = 'return';
      else if (this.stage === 'return') next = 'idle';
      if (next !== this.stage) { this.stage = next; this.loops = 0; }
    }
    return this.frame;
  }

  get frame() {
    let time = this.elapsed;
    const durations = this.durations[this.stage];
    let index = 0;
    while (index < durations.length-1 && time >= durations[index]) time -= durations[index++];
    return index;
  }
}

export function closeWhaleClips(clips) {
  for (const clip of Object.values(clips || {})) for (const frame of clip.frames) frame.close();
}

export async function decodeWhaleClips(urls, cancelled, Decoder = globalThis.ImageDecoder, expected = null) {
  if (!Decoder || !(await Decoder.isTypeSupported('image/gif'))) throw new Error('Static whale fallback');
  const clips = {};
  try {
    for (const stage of expected ? Object.keys(expected) : WHALE_STAGES) {
      if (cancelled()) throw new Error('Whale unmounted');
      const encoded = urls[stage].split(',')[1];
      const decoder = new Decoder({type: 'image/gif', data: Uint8Array.from(atob(encoded), (c) => c.charCodeAt(0))});
      const clip = clips[stage] = {frames: [], durations: []};
      try {
        await decoder.tracks.ready;
        const track = decoder.tracks.selectedTrack;
        if (!track || track.frameCount !== (expected?.[stage] || 16)) throw new Error('Unexpected whale frames');
        for (let i = 0; i < track.frameCount; i++) {
          if (cancelled()) throw new Error('Whale unmounted');
          const {image} = await decoder.decode({frameIndex: i, completeFramesOnly: true});
          clip.frames.push(image);
          if (cancelled() || image.displayWidth !== 512 || image.displayHeight !== 512 || !image.duration) {
            throw new Error('Invalid whale frame');
          }
          clip.durations.push(image.duration/1000);
        }
      } finally { decoder.close(); }
    }
    if (cancelled()) throw new Error('Whale unmounted');
    return clips;
  } catch (error) { closeWhaleClips(clips); throw error; }
}
