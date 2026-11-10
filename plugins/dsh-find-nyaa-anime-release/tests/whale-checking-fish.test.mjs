import test from 'node:test';
import assert from 'node:assert/strict';
import {FishSchool,frameAt,makeProfile,seededRandom,MAX_FISH_DEPTH_RATIO,fishClearance,visibleWaterBounds} from '../client/whale-checking-fish.mjs';
const anchor={x:300,y:200},birthDurations=Array(16).fill(160),swimDurations=Array(16).fill(200);
const make=()=>new FishSchool({width:1200,height:800,birthDurations,swimDurations,seed:17});

test('water gathers before the fish appears and follows the palm',()=>{
  const s=make();s.spawn(0,anchor,54);s.update(899,anchor);
  assert.equal(s.items[0].mode,'gather');assert.equal(s.released,0);
  const moved={x:320,y:210};s.update(900,moved);
  assert.equal(s.items[0].mode,'birth');assert.equal(s.items[0].frame,0);
  assert.equal(s.items[0].x,moved.x);assert.equal(s.items[0].y,moved.y);
  assert.equal(s.items[0].size,54);
});
test('birth hands over without position or size jump and swimming remains animated',()=>{
  const s=make();s.spawn(0,anchor,54);s.update(s.formationMs-1,anchor);const a={...s.items[0]};
  s.update(s.formationMs,anchor);const b={...s.items[0]};assert.equal(b.mode,'swim');assert.equal(b.frame,0);
  assert.equal(a.x,b.x);assert.equal(a.y,b.y);assert.equal(a.size,b.size);
  s.update(s.formationMs+201,anchor);assert.equal(s.items[0].frame,1);assert.ok(s.items[0].x>b.x);
  s.update(s.formationMs+3200,anchor);assert.equal(s.items[0].frame,0);
});
test('tails cycle independently for each birth',()=>{
  const s=make();s.spawn(0,anchor,54);s.spawn(200,anchor,54);s.update(s.formationMs+440,anchor);
  assert.notEqual(s.items[0].frame,s.items[1].frame);
});
test('emergency pool cap is far above ordinary population and never deletes residents',()=>{
  const s=make();for(let i=0;i<70;i++)s.spawn(0,anchor,54);
  assert.equal(s.items.length,64);assert.equal(s.skipped,6);
  s.items.forEach(item=>item.profile.stayMs=1000);
  s.update(s.formationMs,anchor);s.update(180000,anchor);
  assert.equal(s.items.length,0);assert.equal(s.retired,64);
});
test('resize preserves current position, scale and swim phase',()=>{
  const s=make();s.spawn(0,anchor,54);s.update(3500,anchor);const a={...s.items[0]};
  s.resize(390,844,3500);s.update(3500,anchor);const b=s.items[0];
  assert.equal(b.x,a.x);assert.equal(b.y,a.y);assert.equal(b.size,a.size);assert.equal(b.frame,a.frame);
  assert.equal(s.limit,40);
});
test('steady frame selection and nonlooping final frame',()=>{
  assert.equal(frameAt(birthDurations,9000,false),15);assert.equal(frameAt(swimDurations,3400),1);
});

test('rare residence outlives a search and is not a retirement deadline',()=>{
  const s=make();s.spawn(0,anchor,54);const item=s.items[0];
  item.profile=makeProfile(()=>.999);assert.equal(item.profile.kind,'rare');
  assert.ok(item.profile.stayMs>=600000);
  s.update(1800000,anchor);assert.equal(s.items.length,1);
  assert.notEqual(item.behavior,'departing');assert.ok(item.speed>0);
  item.leaveAt=1800000;s.update(1920000,anchor);assert.equal(s.items.length,0);
});

test('crowding shortens newcomer visits without shortening existing rare residents',()=>{
  const quiet=makeProfile(()=>.5,0),busy=makeProfile(()=>.5,2);
  assert.ok(busy.stayMs<quiet.stayMs);assert.equal(busy.directExit,true);
  assert.equal(makeProfile(()=>.999,0).stayMs,makeProfile(()=>.999,3).stayMs);
});

test('rare residence is uncommon and visitors dominate',()=>{
  const random=seededRandom(143),counts={visitor:0,linger:0,rare:0};
  for(let i=0;i<20000;i++)counts[makeProfile(random).kind]++;
  assert.ok(counts.visitor>18500);assert.ok(counts.rare>20&&counts.rare<100);
});

test('most ordinary fish follow a predecessor and new convoys renew the live route',()=>{
  const s=make();let next=0;
  for(let t=0;t<=180000;t+=100){
    if(t>=next){s.spawn(t,anchor,54);s.items.at(-1).profile.rebel=false;next=t+3700;}
    s.update(t,anchor);
  }
  assert.ok(s.followersCreated/s.released>.75);
  assert.ok(s.leadersCreated>=4);assert.ok(s.socialSteps>0);assert.equal(s.skipped,0);
  assert.ok(s.items.every(f=>!f.leader||f.leader.id<f.id));
});

test('followers track the preceding fish actual wake, including bends, rather than its current position',()=>{
  const s=make();let next=0,errors=[];
  for(let t=0;t<=45000;t+=100){
    if(t>=next&&t<20000){s.spawn(t,anchor,54);s.items.at(-1).profile.rebel=false;next=t+3700;}
    s.update(t,anchor);
    for(const f of s.items){
      if(f.leader&&f.leader.active&&t-f.swimAt>4000){
        errors.push(Math.min(...f.leader.wake.map(p=>Math.hypot(f.x-p.x,f.y-p.y))));
        assert.ok(f.followS<=f.leader.wake.at(-1).s+.01);
      }
    }
  }
  errors.sort((a,b)=>a-b);assert.ok(errors.length>100);
  assert.ok(errors[Math.floor(errors.length*.9)]<18,`wake P90 ${errors[Math.floor(errors.length*.9)]}`);
});

test('live course changes alter future leader travel without moving existing points',()=>{
  const a=make(),b=make();
  for(const s of [a,b]){s.spawn(0,anchor,54);s.items[0].profile.rebel=false;s.update(10000,anchor);}
  const before=a.items[0].wake.map(p=>({...p}));
  a.items[0].bendTarget=.7;b.items[0].bendTarget=-.7;
  a.items[0].nextCourse=b.items[0].nextCourse=20000;
  a.update(18000,anchor);b.update(18000,anchor);
  assert.ok(Math.hypot(a.items[0].x-b.items[0].x,a.items[0].y-b.items[0].y)>60);
  assert.deepEqual(a.items[0].wake.slice(0,before.length),before);
});

test('a rebel peels away with at most two new followers; the rest keep a main convoy',()=>{
  const s=make();let next=0,rebel,followers=[];
  for(let t=0;t<=30000;t+=100){
    if(t>=next&&t<24000){
      s.spawn(t,anchor,54);const f=s.items.at(-1);f.profile.rebel=f.id===2;
      if(f.id===2){f.profile.kind='linger';f.profile.stayMs=120000;rebel=f;}
      next=t+3700;
    }
    s.update(t,anchor);
    followers=s.items.filter(f=>f.group?.id===2&&f.id!==2);
    assert.ok(followers.length<=2);
  }
  assert.equal(rebel.behavior,'wandering');assert.equal(rebel.leader,null);
  assert.equal(rebel.group.members,3);assert.equal(s.branchFollowers,2);
  assert.ok(followers.some(f=>f.leader&&f.group.kind==='detour'));
  assert.ok(s.items.some(f=>f.id>4&&f.group.kind==='main'));
});

test('followers finish the recorded route after a leader leaves and all trails stay bounded',()=>{
  const s=make();let next=0;
  for(let t=0;t<=200000;t+=100){
    if(t>=next&&t<25000){s.spawn(t,anchor,54);s.items.at(-1).profile.rebel=false;next=t+3700;}
    s.update(t,anchor);assert.ok(s.items.every(f=>!f.wake||f.wake.length<=640));
  }
  assert.equal(s.items.length,0);assert.equal(s.retired,s.nextId);
});

test('turning, speed and position remain continuous across small updates',()=>{
  const s=make();s.spawn(0,anchor,54);s.update(5000,anchor);
  for(let t=5025;t<15000;t+=25){
    const a={...s.items[0]};s.update(t,anchor);const b=s.items[0];
    assert.equal(b.size,a.size);assert.ok(Math.hypot(b.x-a.x,b.y-a.y)<1.5);
    assert.ok(Math.abs(b.angle-a.angle)<=b.profile.turnRate*.025+1e-9);
  }
});

test('fixed steps are reproducible at different display update frequencies',()=>{
  const a=make(),b=make();a.spawn(0,anchor,54);b.spawn(0,anchor,54);
  for(let t=0;t<=10000;t+=25)a.update(t,anchor);
  for(let t=0;t<=10000;t+=100)b.update(t,anchor);
  assert.deepEqual(a.items,b.items);
});

test('depth limit uses the visible plugin area rather than long document height',()=>{
  assert.equal(MAX_FISH_DEPTH_RATIO,.7);
  assert.deepEqual(visibleWaterBounds(20,2400,844),{top:0,bottom:824});
  assert.deepEqual(visibleWaterBounds(-500,2400,844),{top:500,bottom:1344});
  const s=make();s.resize(390,2400);s.setViewport(500,1344);
  assert.equal(s.waterBottom,500+844*.7);
});

test('ordinary, following and wandering fish keep their full sprite above the lower limit',()=>{
  for(const width of [390,1200])for(const seed of [7,17,93]){
    const s=new FishSchool({width,height:1800,birthDurations,swimDurations,seed});
    s.setViewport(0,720);
    const origin={x:width*.75,y:210};let next=0;
    for(let now=0;now<180000;now+=50){
      if(now>=next&&now<120000){
        assert.ok(s.spawn(now,origin,54));
        if(s.nextId===3){s.items.at(-1).profile.rebel=true;s.items.at(-1).profile.stayMs=900000;}
        next=now+3700;
      }
      s.update(now,origin);
      for(const fish of s.items){
        assert.ok(fish.y+fishClearance(fish.size)<=s.waterBottom+1e-8);
        assert.notEqual(fish.exitEdge,3);
      }
    }
    assert.equal(s.skipped,0);
    assert.equal(s.boundaryClamps,0,'normal travel should turn before the emergency position guard');
  }
});

test('viewport contraction reflows existing wakes without resizing fish or resetting tail phase',()=>{
  const s=make();s.spawn(0,anchor,54);s.update(10000,anchor);
  const fish=s.items[0],before={x:fish.x,y:fish.y,frame:fish.frame,size:fish.size};
  const relative=fish.wake.map(p=>({x:p.x-fish.x,y:p.y-fish.y}));
  s.setViewport(0,300);
  assert.equal(fish.x,before.x);assert.equal(fish.size,before.size);assert.equal(fish.frame,before.frame);
  assert.ok(fish.y+fishClearance(fish.size)<=s.waterBottom+1e-8);
  fish.wake.forEach((p,i)=>{assert.ok(Math.abs(p.x-fish.x-relative[i].x)<1e-8);assert.ok(Math.abs(p.y-fish.y-relative[i].y)<1e-8);});
});

test('a palm below the safe water area does not spawn a fish at a fake offset position',()=>{
  const s=make();s.setViewport(0,240);
  assert.equal(s.spawn(0,anchor,54),false);assert.equal(s.nextId,0);assert.equal(s.items.length,0);
});
