export const HOLD_MS = 7680;
export const sum = values => values.reduce((a,b)=>a+b,0);
export function frameAt(times, elapsed) {
  let t = Math.max(0, elapsed) % sum(times);
  for(let i=0;i<times.length;i++){if(t<times[i])return i;t-=times[i];}
  return times.length-1;
}

// The opaque water interval, not the character's final pose, owns the reset.
export class RetreatTimeline {
  constructor(clips) {
    this.clips=clips;this.clock=0;this.readingElapsed=0;this.stage='reading';
    this.elapsed=0;this.pending=null;this.entryAt=null;this.taps=[];this.resetDone=false;this.resetCount=0;
    this.events=[];this.cooldownUntil=0;
    this.durations={character:sum(clips.character),rise:sum(clips.rise),covered:HOLD_MS,
      reveal:sum(clips.reveal),glance:2240};
    this.recoverStart=600;
    this.recoverEnd=this.recoverStart+(clips.recover?sum(clips.recover):0);
    if(this.recoverEnd>HOLD_MS-500)throw Error('Hidden return must finish before the veil reveals reading');
  }
  get locked(){return this.pending==='retreat'||!['reading','glance'].includes(this.stage)||this.clock<this.cooldownUntil;}
  request(action){
    if(!['glance','retreat'].includes(action)||this.locked)return false;
    this.pending=action;this.entryAt=null;
    if(action==='retreat'&&this.stage==='reading'){
      const cycle=sum(this.clips.reading),phase=this.readingElapsed%cycle;
      const firstEnd=this.clips.reading[0];
      this.entryAt=this.readingElapsed-phase+(phase<firstEnd?0:cycle)+firstEnd;
    }
    this.startPending();return true;
  }
  tap(repeat=false){
    if(repeat||this.locked)return;
    this.taps=this.taps.filter(t=>this.clock-t<=1200);this.taps.push(this.clock);
    if(this.taps.length>=3){this.taps=[];this.request('retreat');}
    else if(this.taps.length===1)this.request('glance');
  }
  startPending(){
    if(this.stage!=='reading'||!this.pending)return;
    // Let the settled reference cel actually play, rather than skipping it at loop wrap.
    if(this.entryAt!==null){if(this.readingElapsed<this.entryAt)return;}
    else if(frameAt(this.clips.reading,this.readingElapsed)!==0)return;
    const action=this.pending;
    this.heldElapsed=this.entryAt===null?this.readingElapsed:this.entryAt-this.clips.reading[0];
    this.readingElapsed=this.heldElapsed;this.pending=null;this.entryAt=null;
    this.enter(action==='retreat'?'character':'glance');
  }
  enter(stage){
    this.stage=stage;this.elapsed=0;this.events.push({stage,clock:this.clock});
    if(stage==='character'){this.resetDone=false;this.taps=[];this.cooldownUntil=this.clock+6000;}
  }
  advance(delta){
    if(!Number.isFinite(delta)||delta<0)throw Error('Invalid clock delta');
    let remaining=delta;
    while(remaining>0){
      this.startPending();
      if(this.stage==='reading'){
        const duration=sum(this.clips.reading),phase=this.readingElapsed%duration;
        const boundary=this.pending?(this.entryAt===null?duration-phase:this.entryAt-this.readingElapsed):remaining;
        const step=Math.min(remaining,boundary);this.readingElapsed+=step;this.clock+=step;remaining-=step;
        this.startPending();continue;
      }
      const step=Math.min(remaining,this.durations[this.stage]-this.elapsed);
      this.elapsed+=step;this.clock+=step;remaining-=step;
      if(this.stage==='covered'&&!this.resetDone&&this.elapsed>=this.recoverEnd){
        this.resetDone=true;this.resetCount++;this.readingElapsed=0;
        this.events.push({stage:'reset-under-cover',clock:this.clock});
      }
      if(this.elapsed>=this.durations[this.stage]){
        if(this.stage==='glance'){
          if(this.pending==='retreat'){this.pending=null;this.entryAt=null;this.enter('character');}
          else this.enter('reading');
        }else if(this.stage==='character')this.enter('rise');
        else if(this.stage==='rise')this.enter('covered');
        else if(this.stage==='covered')this.enter('reveal');
        else if(this.stage==='reveal'){this.enter('reading');this.readingElapsed=0;this.taps=[];}
      }
    }
  }
  sample(){
    const s=this.stage,t=this.elapsed;
    let character={clip:'reading',frame:frameAt(this.clips.reading,this.readingElapsed)};
    let water=null;
    if(s==='character')character={clip:'character',frame:frameAt(this.clips.character,t)};
    if(s==='rise'||(s==='covered'&&!this.resetDone))character={clip:'character',frame:this.clips.character.length-1};
    if(s==='covered'&&this.clips.recover&&t>=this.recoverStart&&t<this.recoverEnd){
      character={clip:'recover',frame:frameAt(this.clips.recover,t-this.recoverStart)};
    }
    if(s==='covered'&&this.resetDone||s==='reveal')character={clip:'reading',frame:0};
    if(s==='rise')water={clip:'rise',frame:frameAt(this.clips.rise,t)};
    if(s==='covered')water={clip:'hold',frame:frameAt(this.clips.hold,t)};
    if(s==='reveal')water={clip:'reveal',frame:frameAt(this.clips.reveal,t)};
    return {stage:s,elapsed:t,character,water,resetDone:this.resetDone};
  }
}
