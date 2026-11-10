export const total = (durations) => durations.reduce((sum, value) => sum + value, 0);
export function frameAt(durations, elapsed, loop = true) {
  let time = loop ? Math.max(0, elapsed) % total(durations) : Math.min(Math.max(0, elapsed), total(durations) - .001);
  for (let i = 0; i < durations.length; i++) { if (time < durations[i]) return i; time -= durations[i]; }
  return durations.length - 1;
}

export function curve(points, t) {
  const u = 1 - t;
  return { x: u*u*u*points[0].x + 3*u*u*t*points[1].x + 3*u*t*t*points[2].x + t*t*t*points[3].x,
    y: u*u*u*points[0].y + 3*u*u*t*points[1].y + 3*u*t*t*points[2].y + t*t*t*points[3].y,
    dx: 3*u*u*(points[1].x-points[0].x)+6*u*t*(points[2].x-points[1].x)+3*t*t*(points[3].x-points[2].x),
    dy: 3*u*u*(points[1].y-points[0].y)+6*u*t*(points[2].y-points[1].y)+3*t*t*(points[3].y-points[2].y) };
}

export const MAX_FISH_DEPTH_RATIO=.70;
// Full rotated sprite, including the swim anchor offset and departure droplets.
export const fishClearance=size=>size*.73+2;
export function visibleWaterBounds(panelTop,panelHeight,viewportHeight) {
  const top=Math.max(0,Math.min(panelHeight,-panelTop));
  const bottom=Math.max(top,Math.min(panelHeight,viewportHeight-panelTop));
  return {top,bottom};
}
const STEP_MS=25,TAU=Math.PI*2;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
const unit=(x,y)=>{const n=Math.hypot(x,y);return n>1e-8?{x:x/n,y:y/n}:{x:0,y:0};};
const angleDelta=(target,current)=>Math.atan2(Math.sin(target-current),Math.cos(target-current));

export function seededRandom(seed) {
  let state=seed>>>0;
  return ()=>{state+=0x6D2B79F5;let n=state;n=Math.imul(n^n>>>15,n|1);n^=n+Math.imul(n^n>>>7,n|61);return ((n^n>>>14)>>>0)/4294967296;};
}

// Long residence is intentional, not a timeout. Density affects newcomers only.
export function makeProfile(random,density=0) {
  const roll=random(),pressure=Math.max(0,density-1);
  let kind='visitor',stayMs=(14000+random()*28000)/(1+pressure*3);
  if(roll>=.997){kind='rare';stayMs=Math.min(21600000,600000/Math.pow(Math.max(.0001,1-random()),.65));}
  else if(roll>=.95){kind='linger';stayMs=(80000+random()*160000)/(1+pressure);}
  return {kind,stayMs:Math.max(4000,stayMs),rebel:kind!=='visitor'||random()<.04,
    phase:random()*TAU,period:22000+random()*26000,speed:25+random()*14,
    turnRate:.75+random()*.35,exitBias:random(),exitAlong:.18+random()*.64,
    gap:44+random()*18,laneOffset:(random()-.5)*9,directExit:pressure>.25};
}

// A wake is a bounded record of actual travel, not a pre-authored screen path.
function wakePoint(wake,s) {
  if(s<=wake[0].s)return {...wake[0]};
  let lo=0,hi=wake.length-1;
  while(lo+1<hi){const mid=(lo+hi)>>1;if(wake[mid].s<s)lo=mid;else hi=mid;}
  const a=wake[lo],b=wake[hi],t=(s-a.s)/Math.max(.001,b.s-a.s);
  return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t,s,angle:Math.atan2(b.y-a.y,b.x-a.x)};
}

export class FishSchool {
  constructor({width,height,birthDurations,swimDurations,gatherMs=900,seed=globalThis.crypto?.getRandomValues(new Uint32Array(1))[0]??Date.now()}) {
    this.width=width;this.height=height;this.birthDurations=birthDurations;this.swimDurations=swimDurations;
    this.viewTop=0;this.viewBottom=height;this.boundaryClamps=0;
    this.birthMs=total(birthDurations);this.gatherMs=gatherMs;this.formationMs=gatherMs+this.birthMs;
    this.items=[];this.nextId=0;this.released=0;this.retired=0;this.skipped=0;this.simAt=null;
    this.random=seededRandom(seed);this.seed=seed;this.peak=0;this.socialSteps=0;
    this.followersCreated=0;this.leadersCreated=0;this.detoursCreated=0;this.branchFollowers=0;
  }
  get comfort() {return this.width<=600?8:12;}
  // Emergency protection only, well above the normal controlled population.
  get limit() {return this.width<=600?40:64;}
  get waterBottom() {return this.viewTop+(this.viewBottom-this.viewTop)*MAX_FISH_DEPTH_RATIO;}
  get waterHeight() {return this.waterBottom-this.viewTop;}
  setViewport(top,bottom) {
    this.viewTop=clamp(top,0,this.height);this.viewBottom=clamp(bottom,this.viewTop,this.height);
    // A viewport contraction reflows the school and its recorded wakes together.
    // Ordinary animation never changes coordinates this way.
    const swimmers=this.items.filter(f=>f.mode==='swim');
    const overflow=Math.max(0,...swimmers.map(f=>f.y+fishClearance(f.size)-this.waterBottom));
    if(overflow){
      const all=new Set(swimmers);
      for(const f of all)if(f.leader)all.add(f.leader);
      for(const f of all){f.y-=overflow;f.origin.y-=overflow;for(const p of f.wake)p.y-=overflow;}
    }
  }
  spawn(now,anchor,size) {
    if(anchor.y+fishClearance(size)>this.waterBottom||anchor.y< this.viewTop)return false;
    if(this.items.length>=this.limit){this.skipped++;return false;}
    if(this.simAt===null)this.simAt=now;
    this.items.push({id:this.nextId++,born:now,mode:this.gatherMs?'gather':'birth',x:anchor.x,y:anchor.y,
      size,angle:0,frame:0,speed:0,companions:0,behavior:'forming',active:true,
      profile:makeProfile(this.random,this.items.length/this.comfort)});
    this.peak=Math.max(this.peak,this.items.length);return true;
  }
  formation(item,now,anchor) {
    if(item.mode==='swim')return;
    item.x=anchor.x;item.y=anchor.y;
    const age=now-item.born;
    if(age<this.gatherMs){item.mode='gather';item.frame=0;return;}
    item.mode='birth';item.frame=frameAt(this.birthDurations,age-this.gatherMs,false);
    if(age<this.formationMs)return;
    item.mode='swim';item.swimAt=item.born+this.formationMs;item.frame=0;
    item.leaveAt=item.swimAt+item.profile.stayMs;this.released++;
    this.joinConvoy(item,now);
  }
  joinConvoy(item,now) {
    const candidates=this.items.filter(other=>other.id<item.id&&other.mode==='swim'&&other.active
      &&!other.hasFollower&&now-other.swimAt<8500&&now<other.group.until
      &&other.group.members<(other.group.kind==='detour'?3:10)
      &&Math.hypot(other.wake[0].x-item.x,other.wake[0].y-item.y)<120);
    const leader=candidates.sort((a,b)=>b.id-a.id)[0];
    item.leader=leader??null;item.followS=0;item.hasFollower=false;
    item.wake=[{x:item.x,y:item.y,s:0,angle:0,time:now}];item.distance=0;
    item.origin={x:item.x,y:item.y};item.bend=0;item.bendTarget=0;item.nextCourse=now;
    if(leader){leader.hasFollower=true;this.followersCreated++;}
    else this.leadersCreated++;
    item.group=item.profile.rebel||!leader?{id:item.id,kind:item.profile.rebel?'detour':'main',
      members:1,until:now+(item.profile.directExit?18000:30000+this.random()*10000)}:leader.group;
    if(leader&&!item.profile.rebel){item.group.members++;if(item.group.kind==='detour')this.branchFollowers++;}
    item.breakAt=item.profile.rebel?now+6500+this.random()*2500:Infinity;
    item.followUntil=item.group.kind==='detour'&&!item.profile.rebel?now+24000+this.random()*14000:Infinity;
    if(item.profile.rebel)this.detoursCreated++;
  }
  exitTarget(item) {
    const margin=item.size*1.5,p=item.profile;
    if(item.exitEdge===undefined){
      const distances=[item.x,this.width-item.x,item.y-this.viewTop];
      const edges=[0,1,2].sort((a,b)=>distances[a]-distances[b]);
      item.exitEdge=edges[p.directExit||p.exitBias<.72?0:1];
    }
    return [{x:-margin,y:this.viewTop+this.waterHeight*p.exitAlong},{x:this.width+margin,y:this.viewTop+this.waterHeight*p.exitAlong},
      {x:this.width*p.exitAlong,y:this.viewTop-margin}][item.exitEdge];
  }
  follow(item) {
    const leader=item.leader,wake=leader.wake,last=wake.at(-1);
    item.followS=Math.max(item.followS,wake[0].s);
    // Advance along nearby traversed segments; never jump across a loop in the wake.
    let best=null;
    for(let i=1;i<wake.length;i++){
      const a=wake[i-1],b=wake[i];
      if(b.s<item.followS-4)continue;
      if(a.s>item.followS+32)break;
      const dx=b.x-a.x,dy=b.y-a.y;
      const t=clamp(((item.x-a.x)*dx+(item.y-a.y)*dy)/Math.max(.001,dx*dx+dy*dy),0,1);
      const d=Math.hypot(item.x-a.x-dx*t,item.y-a.y-dy*t);
      if(!best||d<best.d)best={d,s:a.s+(b.s-a.s)*t};
    }
    if(best)item.followS=Math.max(item.followS,best.s);
    const remaining=last.s-item.followS-(leader.active?item.profile.gap:0);
    const aimS=Math.min(last.s+(leader.active?0:item.size*2),item.followS+Math.max(14,item.speed*.65));
    const aim=wakePoint(wake,Math.max(wake[0].s,Math.min(aimS,last.s-(leader.active?item.profile.gap:0))));
    if(!leader.active&&item.followS>=last.s-5){
      aim.x=last.x+Math.cos(last.angle)*item.size*2;aim.y=last.y+Math.sin(last.angle)*item.size*2;
    }
    const lateral=item.profile.laneOffset*Math.min(1,(last.s-item.followS)/60);
    const dx=aim.x-Math.sin(aim.angle)*lateral-item.x,dy=aim.y+Math.cos(aim.angle)*lateral-item.y;
    item.companions=1;item.behavior=leader.active?'following':'following-out';
    return {angle:Math.hypot(dx,dy)>3?Math.atan2(dy,dx):item.angle,
      speed:leader.active?Math.max(0,Math.min(leader.profile.speed*1.3,remaining*.7)):leader.profile.speed*1.1};
  }
  lead(item,now) {
    const p=item.profile,t=now/p.period*TAU+p.phase;
    const wandering=p.rebel&&now<item.leaveAt;
    let target;
    if(wandering){
      target={x:this.width*(.5+.28*Math.sin(t*.72)+.09*Math.sin(t*1.41)),
        y:this.viewTop+this.waterHeight*(.48+.25*Math.cos(t*.56+p.phase)+.08*Math.sin(t*.91))};
    }else{
      if(item.exitEdge===undefined){
        item.exitEdge=p.rebel?undefined:item.origin.x>this.width/2?0:1;
      }
      target=this.exitTarget(item);
      // The exit is a broad direction. Its live current and steering evolve while swimming.
      const along=.5+.23*Math.sin(now/31000+p.phase)+.08*Math.sin(item.x/310+now/13000);
      if(item.exitEdge<2)target.y=this.viewTop+this.waterHeight*along;else target.x=this.width*along;
    }
    if(now>=item.nextCourse){item.bendTarget=(this.random()-.5)*.95;item.nextCourse=now+3500+this.random()*4000;}
    item.bend+=clamp(item.bendTarget-item.bend,-.18*STEP_MS/1000,.18*STEP_MS/1000);
    const distance=Math.hypot(target.x-item.x,target.y-item.y);
    const bend=item.bend*Math.min(1,distance/140)+(wandering?0:.16*Math.sin(now/4700+item.y/190));
    let angle=Math.atan2(target.y-item.y,target.x-item.x)+bend;
    if(wandering){
      const edge=Math.max(1,Math.min(95,this.width*.24,this.waterHeight*.2));
      let fx=Math.cos(angle),fy=Math.sin(angle);
      fx+=clamp((edge-item.x)/edge,0,2)*4-clamp((item.x-this.width+edge)/edge,0,2)*4;
      fy+=clamp((this.viewTop+edge-item.y)/edge,0,2)*4-clamp((item.y-this.waterBottom+edge)/edge,0,2)*4;
      angle=Math.atan2(fy,fx);
    }
    item.behavior=wandering?'wandering':now>=item.leaveAt?'departing':'leading';item.companions=0;
    return {angle,speed:p.speed*(wandering?.9:1.05)};
  }
  steer(item,neighbors,now) {
    if((item.profile.rebel&&now>=item.breakAt)||now>=item.followUntil)item.leader=null;
    const desired=item.leader?this.follow(item):this.lead(item,now);
    let fx=Math.cos(desired.angle),fy=Math.sin(desired.angle);
    // Separation is a small local correction, not a competing screen-wide destination.
    for(const other of neighbors){
      if(other.id===item.id)continue;
      const d=Math.hypot(other.x-item.x,other.y-item.y),spacing=item.size*.58;
      if(d<spacing&&d>.01){const away=unit(item.x-other.x,item.y-other.y),weight=(1-d/spacing)*.65;fx+=away.x*weight;fy+=away.y*weight;}
    }
    const clearance=this.waterBottom-fishClearance(item.size)-item.y;
    const turningRoom=Math.max(55,item.speed/item.profile.turnRate*2+item.size*.4);
    const pressure=clamp((turningRoom-clearance)/turningRoom,0,1);
    // The same gradual upward current acts on leaders, followers and wanderers.
    fy-=pressure*pressure*5;
    const age=(now-item.swimAt)/1000,launch=clamp(age/.6,0,1);
    return {angle:Math.atan2(fy*launch,1-launch+fx*launch),speed:desired.speed*Math.min(1,age/1.2)};
  }
  recordWake(item,now,previous) {
    item.distance+=Math.hypot(item.x-previous.x,item.y-previous.y);
    const last=item.wake.at(-1);
    if(item.distance-last.s<.01||(item.distance-last.s<2&&now-last.time<125))return;
    item.wake.push({x:item.x,y:item.y,s:item.distance,angle:item.angle,time:now});
    if(item.wake.length>640)item.wake.splice(0,item.wake.length-640);
  }
  step(now,anchor) {
    for(const item of this.items)this.formation(item,now,anchor);
    const snapshot=this.items.filter(item=>item.mode==='swim').map(({id,x,y})=>({id,x,y}));
    const moves=this.items.filter(item=>item.mode==='swim').map(item=>({item,desired:this.steer(item,snapshot,now)}));
    for(const {item,desired} of moves){
      const previous={x:item.x,y:item.y};
      const dt=Math.min(STEP_MS,Math.max(0,now-item.swimAt))/1000;
      const turn=clamp(angleDelta(desired.angle,item.angle),-item.profile.turnRate*dt,item.profile.turnRate*dt);
      item.angle+=turn;
      item.speed+=clamp(desired.speed-item.speed,-18*dt,18*dt);
      item.x+=Math.cos(item.angle)*item.speed*dt;item.y+=Math.sin(item.angle)*item.speed*dt;
      const floor=this.waterBottom-fishClearance(item.size);
      if(item.y>floor){item.y=floor;this.boundaryClamps++;}
      this.recordWake(item,now,previous);
      if(item.companions)this.socialSteps++;
    }
    this.items=this.items.filter(item=>{
      const outside=item.mode==='swim'&&(item.x+fishClearance(item.size)<0||item.x-fishClearance(item.size)>this.width||item.y+fishClearance(item.size)<this.viewTop);
      if(outside){
        item.active=false;item.leader=null;
        item.wake.push({x:item.x,y:item.y,s:item.distance,angle:item.angle,time:now});
        this.retired++;return false;
      }return true;
    });
  }
  update(now,anchor) {
    if(this.simAt===null)this.simAt=now;
    while(this.simAt+STEP_MS<=now){this.simAt+=STEP_MS;this.step(this.simAt,anchor);}
    for(const item of this.items){
      this.formation(item,now,anchor);
      if(item.mode==='swim')item.frame=frameAt(this.swimDurations,now-item.swimAt);
    }
  }
  resize(width,height) {
    this.width=width;this.height=height;
    this.setViewport(0,height);
    for(const item of this.items)delete item.exitEdge;
  }
}
