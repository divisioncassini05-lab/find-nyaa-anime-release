import {frameAt,total} from './whale-checking-fish.mjs';

const RESULTS=new Set(['success','attention','no_update','cancelled']);
const REST_MS=80;

export class CheckingCharacter {
  constructor(clips,metadata) {
    this.clips=clips;this.metadata=metadata;this.state='idle';this.started=0;
    this.wanted=false;this.ending=false;this.result=null;this.settleAt=null;
    this.drainUntil=0;this.holdKey='guide';this.completed=0;this.lastResult=null;
  }
  setChecking(value,now,formationEnd=now) {
    if(!value){this.finishChecking('cancelled',now,formationEnd);return;}
    this.advance(now);this.wanted=true;
    // A new request waits behind the committed close and its one result gesture.
    if(this.state==='idle'&&!this.ending){this.state='enter';this.started=now;}
  }
  finishChecking(result,now,formationEnd=now) {
    if(!RESULTS.has(result))throw new TypeError('Unknown checking result: '+result);
    this.advance(now);this.wanted=false;
    if(this.ending||this.state==='idle')return;
    this.ending=true;this.result=result;this.drainUntil=Math.max(now,formationEnd);
    if(this.state==='loop'){
      const duration=total(this.clips.guide.durations),phase=(now-this.started)%duration;
      this.settleAt=phase===0?now:now+duration-phase;
    }
  }
  complete(at) {
    this.completed++;this.lastResult=this.result;this.result=null;this.ending=false;
    this.settleAt=null;this.started=at;this.state=this.wanted?'enter':'idle';
  }
  advance(now) {
    // Consume elapsed boundaries without replaying or inventing another loop.
    for(let transitions=0;transitions<12;transitions++) {
      const before=this.state;
      if(this.state==='enter'&&now>=this.started+total(this.clips.enter.durations)){
        this.started+=total(this.clips.enter.durations);
        this.state=this.ending?'hold':'loop';this.holdKey='enter';
      } else if(this.state==='loop'&&this.ending&&now>=this.settleAt){
        this.started=this.settleAt;this.state='hold';this.holdKey='guide';
      } else if(this.state==='hold'&&now>=Math.max(this.started,this.drainUntil)){
        if(!this.clips.exit){this.state='blocked';break;}
        this.started=Math.max(this.started,this.drainUntil);this.state='exit';
      } else if(this.state==='exit'&&now>=this.started+total(this.clips.exit.durations)){
        this.started+=total(this.clips.exit.durations);this.state='resting';
      } else if(this.state==='resting'&&now>=this.started+REST_MS){
        this.started+=REST_MS;
        if(['success','attention'].includes(this.result)){
          if(!this.clips[this.result]){this.state='blocked';this.holdKey='idle';break;}
          this.state='feedback';
        } else this.complete(this.started);
      } else if(this.state==='feedback'&&now>=this.started+total(this.clips[this.result].durations)){
        this.complete(this.started+total(this.clips[this.result].durations));
      }
      if(before===this.state)break;
    }
  }
  sample(now) {
    this.advance(now);
    const key=({idle:'idle',resting:'idle',enter:'enter',loop:'guide',exit:'exit',feedback:this.result,
      hold:this.holdKey,blocked:this.holdKey})[this.state];
    const clip=this.clips[key],elapsed=now-this.started;
    const index=this.state==='resting'?0:['hold','blocked'].includes(this.state)?clip.frames.length-1:
      frameAt(clip.durations,elapsed,['idle','loop'].includes(this.state));
    const stage=({enter:'checking-enter',guide:'checking-loop',exit:'checking-exit'})[key];
    const anchors=stage&&this.metadata.clips[stage]?.palm_anchors;
    let palm=anchors?.[index]??{x:335,y:383};
    if(this.state==='loop'&&anchors){
      const phase=elapsed%total(clip.durations),begin=clip.durations.slice(0,index).reduce((a,b)=>a+b,0);
      const t=Math.max(0,Math.min(1,(phase-begin)/clip.durations[index])),ease=t*t*(3-2*t);
      const next=anchors[(index+1)%anchors.length];
      palm={x:palm.x+(next.x-palm.x)*ease,y:palm.y+(next.y-palm.y)*ease};
    }
    return {state:this.state,key,index,image:clip.frames[index],palm,
      canSummon:this.state==='loop'&&this.wanted&&!this.ending,
      ending:this.ending,result:this.result,lastResult:this.lastResult};
  }
}
