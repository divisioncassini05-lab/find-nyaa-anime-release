const active = plan => ['queued', 'running'].includes(plan.checkStatus) && !plan.paused;
const attention = new Set(['needs_confirmation', 'latest_unresolved', 'resolver_failed', 'search_incomplete']);

// Observe existing host evidence only. The mascot never starts a search or infers
// success from old resources, elapsed animation time, or the number of fish.
export class WhaleCheckStatus {
  constructor() {
    this.baselines = new Map();
    this.checking = false;
    this.outcome = null;
    this.sequence = 0;
  }
  update(plans) {
    const running = plans.filter(active);
    const byId = new Map(plans.map(plan => [plan.id, plan]));
    for (const plan of running) {
      if (!this.baselines.has(plan.id)) this.baselines.set(plan.id, plan.evidence?.lastSearch?.checkedAt || '');
    }
    for (const [id, baseline] of this.baselines) {
      const plan = byId.get(id), search = plan?.evidence?.lastSearch;
      if (!search || !(Date.parse(search.checkedAt) > (Date.parse(baseline) || 0))) continue;
      if (attention.has(search.status)) this.outcome = 'attention';
      else if (search.status === 'found' && this.outcome !== 'attention') this.outcome = 'success';
    }
    let result = null;
    if (this.checking && !running.length) {
      const cancelled = [...this.baselines.keys()].every(id => !byId.has(id) || byId.get(id).paused);
      result = this.outcome || (cancelled ? 'cancelled' : 'no_update');
      this.baselines.clear();
      this.outcome = null;
      this.sequence++;
    }
    this.checking = running.length > 0;
    return {checking: this.checking, result, sequence: this.sequence};
  }
}
