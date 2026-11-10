import {WhaleTimeline} from './whale-timeline.mjs';
import {AmbientScheduler} from './whale-ambient-scheduler.mjs';

export function clipFrame(durations, elapsed) {
  let i=0;
  while(i<durations.length-1 && elapsed>=durations[i]) elapsed-=durations[i++];
  return i;
}

// Small extension of the four-stage clock: random clips borrow a stable parent
// boundary and return it unchanged. Decoding never blocks the animation clock.
export class WhaleAmbientTimeline {
  constructor(durations, actions, {random=Math.random, ready=()=>true, minimum=25000, maximum=45000}={}) {
    this.base=new WhaleTimeline(durations);
    this.actions=actions;this.ready=ready;
    this.scheduler=new AmbientScheduler({
      idle:Object.keys(actions).filter(id=>actions[id].mode==='idle'),
      reading:Object.keys(actions).filter(id=>actions[id].mode==='reading'),
    },{random,minimum,maximum});
    this.action=null;this.pendingAction=null;this.actionElapsed=0;this.totalElapsed=0;
    this.bookElapsed=0;this.running=true;this.blocked=false;
  }
  request(mode) { this.base.request(mode);this.pendingAction=null;this.scheduler.reset(); }
  setRunning(value) {this.running=Boolean(value);}
  setBlocked(value) {this.blocked=Boolean(value);if(value)this.pendingAction=null;}
  get parent() {return this.base.stage;}
  get stage() {return this.action||this.parent;}
  get elapsed() {return this.action?this.actionElapsed:this.base.elapsed;}
  get frame() {return this.action?clipFrame(this.actions[this.action].durations,this.actionElapsed):this.base.frame;}
  get requested() {return this.base.requested;}
  advance(delta) {
    if(!Number.isFinite(delta)||delta<0)throw new Error('Invalid whale clock');
    if(!this.running)return this.frame;
    while(delta>0){
      const stable=['idle','reading'].includes(this.parent);
      if(this.action){
        const duration=this.actions[this.action].durations.reduce((a,b)=>a+b,0);
        const step=Math.min(delta,duration-this.actionElapsed);
        this.actionElapsed+=step;this.totalElapsed+=step;this.bookElapsed+=step;delta-=step;
        if(this.actionElapsed>=duration){this.action=null;this.actionElapsed=0;this.scheduler.reset();}
        continue;
      }
      const remaining=this.base.totals[this.parent]-this.base.elapsed;
      const step=Math.min(delta,remaining);
      const override=this.requested!=='auto'&&this.requested!==this.parent;
      this.scheduler.advance(step,stable&&!override&&!this.blocked);
      if(this.scheduler.due&&!this.pendingAction)this.pendingAction=this.scheduler.take(this.parent);
      this.totalElapsed+=step;this.bookElapsed+=step;delta-=step;
      if(step===remaining&&this.pendingAction&&this.ready(this.pendingAction)&&!override&&!this.blocked){
        this.action=this.pendingAction;this.pendingAction=null;
        this.base.elapsed=0;this.actionElapsed=0;
      }else{
        const before=this.parent;this.base.advance(step);
        if(before!==this.parent)this.pendingAction=null;
      }
    }
    return this.frame;
  }
}
