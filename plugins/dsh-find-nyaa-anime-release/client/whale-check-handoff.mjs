// One clock owner for WhaleAmbientTimeline and WhaleCheckingController. The host
// calls advance instead of advancing either object itself; drawing stays separate.
export class WhaleCheckHandoff {
  constructor(timeline, checking) {
    this.timeline = timeline;
    this.checking = checking;
    this.engaged = false;
    this.previousBlocked = false;
  }

  get active() { return this.checking.active; }
  get pending() { return this.checking.pending; }
  get needsIdle() { return this.engaged || this.checking.needsIdle; }
  get canReturn() { return !this.needsIdle; }

  start() {
    if (!this.engaged) this.previousBlocked = this.timeline.blocked;
    this.engaged = true;
    this.timeline.setBlocked(true);
    this.timeline.request('idle');
    this.checking.start();
  }

  finish(result = 'cancelled') {
    this.checking.finish(result);
  }

  get idleBoundary() {
    return this.timeline.parent === 'idle' && !this.timeline.action && this.timeline.base.elapsed === 0;
  }

  release() {
    this.timeline.request('idle');
    this.timeline.setBlocked(this.previousBlocked);
    this.engaged = false;
  }

  untilBoundary() {
    const t = this.timeline;
    return t.action
      ? t.actions[t.action].durations.reduce((sum, ms) => sum + ms, 0) - t.actionElapsed
      : t.base.totals[t.parent] - t.base.elapsed;
  }

  // Geometry is the controller's existing contract. Caller-provided idleReady is
  // deliberately overridden. A paused timeline or hidden/reduced controller freezes both.
  advance(delta, geometry = {}) {
    if (!Number.isFinite(delta) || delta < 0) throw new TypeError('Invalid whale handoff clock');
    const t = this.timeline, c = this.checking;
    const options = { ...geometry, running: t.running && (geometry.running ?? true), idleReady: false };
    c.update(0, options);
    if (!c.running || !t.running) return 0;
    if (this.engaged) {
      t.setBlocked(true);
      if (t.requested !== 'idle') t.request('idle');
    }
    let remaining = Math.min(100, delta), advanced = 0;
    for (;;) {
      if (this.engaged && this.idleBoundary) {
        c.update(0, { ...options, idleReady: true });
        if (!c.needsIdle) this.release();
      }
      if (remaining === 0) break;
      if (c.active) {
        // The idle body is parked at its exact boundary; independent layers keep time.
        const step = c.update(remaining, options);
        t.bookElapsed += step;
        t.totalElapsed += step;
        advanced += step;
        if (this.engaged && !c.needsIdle) this.release();
        break;
      }
      // Geometry may not be ready yet. Keep the safe boundary until acquisition succeeds.
      if (this.engaged && this.idleBoundary && c.pending) break;
      const step = this.engaged ? Math.min(remaining, this.untilBoundary()) : remaining;
      if (step <= 0) throw new Error('Invalid whale handoff boundary');
      t.advance(step);
      c.update(step, options);
      remaining -= step;
      advanced += step;
    }
    return advanced;
  }
}
