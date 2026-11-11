import {RetreatTimeline} from './whale-retreat-timeline.mjs';

// A reading-only branch. The existing ambient/checking owners keep their clocks.
export class ReadingRetreatHandoff {
  constructor(base,{ready=()=>null,load=()=>{},single=()=>{}}={}) {
    this.base=base;this.ready=ready;this.load=load;this.single=single;
    this.clock=0;this.taps=[];this.pending=false;this.actor=null;this.completed=0;
    this.cooldownUntil=0;this.reserved=false;
  }
  get busy(){return this.pending||Boolean(this.actor);}
  get counting(){return this.taps.length>0;}
  get ownsCharacter(){return Boolean(this.actor);}
  get state(){return this.actor?.stage||(this.pending?'loading':'idle');}
  tap(singleMode) {
    if(this.busy)return true;
    if(this.base.parent!=='reading'||this.base.action||!this.base.running||(this.base.blocked&&!this.reserved))return false;
    if(this.clock<this.cooldownUntil)return true;
    this.taps=this.taps.filter(t=>this.clock-t<=1200);
    if(!this.taps.length){
      this.reserve();this.singleMode=singleMode;
    }
    this.taps.push(this.clock);
    if(this.taps.length>=3){this.taps=[];this.pending=true;this.load();}
    return true;
  }
  reserve(){
    if(this.reserved)return;
    this.previousMode=this.base.requested;this.previousBlocked=this.base.blocked;
    this.reserved=true;this.base.request('reading');this.base.setBlocked(true);
  }
  release(){
    if(!this.reserved)return;
    this.base.request(this.previousMode);this.base.setBlocked(this.previousBlocked);this.reserved=false;
  }
  // A checking signal cancels only counting/loading, never cuts an accepted visible action.
  cancelPending(){
    this.taps=[];
    if(this.actor&&this.actor.stage!=='reading')return false;
    if(this.actor)this.base.base.elapsed=this.actor.readingElapsed%this.base.base.totals.reading;
    this.actor=null;this.pending=false;this.release();return true;
  }
  fail(){this.cancelPending();}
  clearClicks(){
    this.taps=[];
    if(!this.busy)this.release();
  }
  advance(delta){
    if(!Number.isFinite(delta)||delta<0)throw Error('Invalid reading interaction clock');
    if(!this.base.running)return false;
    this.clock+=delta;
    if(this.counting&&this.clock-this.taps.at(-1)>1200){
      const mode=this.singleMode;this.taps=[];this.release();this.single(mode);
    }
    if(this.pending){
      const loaded=this.ready();
      if(loaded){
        this.actor=new RetreatTimeline(loaded.durations);
        this.actor.readingElapsed=this.base.base.elapsed;
        this.actor.request('retreat');this.pending=false;
      }
    }
    if(!this.actor)return false;
    this.actor.advance(delta);this.base.bookElapsed+=delta;this.base.totalElapsed+=delta;
    if(this.actor.stage==='reading'&&!this.actor.pending&&this.actor.resetCount){
      this.base.base.stage='reading';this.base.base.elapsed=this.actor.readingElapsed;
      this.base.base.loops=0;this.actor=null;this.completed++;this.release();
      this.cooldownUntil=this.clock+6000;
    }
    return true;
  }
}
