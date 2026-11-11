import test from 'node:test';
import assert from 'node:assert/strict';
import { SPECIES, OceanWorld, socialSteering, CHARACTER_REFERENCE, characterSize, densityLimit } from '../client/ocean/faunaMotion.mjs';
import { WaterAtmosphere } from '../client/ocean/waterAtmosphere.mjs';
import { SeabedDetails, terrainFit } from '../client/ocean/seabedDetails.mjs';
const advance=(world,seconds)=>{for(let i=0;i<seconds*10;i++)world.step(.1);};
const spread=world=>{const a=world.animals;let d=0,n=0;for(let i=0;i<a.length;i++)for(let j=i+1;j<a.length;j++){d+=Math.hypot(a[i].x-a[j].x,a[i].y-a[j].y);n++;}return d/n;};

test('all 19 species have movement, variants and bounded temperament',()=>{
  assert.equal(SPECIES.length,19);
  assert.equal(SPECIES.reduce((n,s)=>n+s.variants.length,0),22);
  for(const s of SPECIES){assert.ok(s.speed>0);assert.ok(s.shy>=0&&s.shy<=1);assert.ok(s.lane[0]<s.lane[1]);}
});
test('sizes use the seated girl reference at both layout breakpoints',()=>{
  assert.deepEqual(CHARACTER_REFERENCE,{desktop:150,narrow:132,breakpoint:600});
  for(const width of [390,600,780,1440]){
    for(const spec of SPECIES){
      const w=new OceanWorld({width,auto:false});const[a]=w.spawn(spec.id,{count:1});
      const expected=spec.ratio*characterSize(width);
      assert.ok(a.size>=expected*.88&&a.size<=expected*1.10,spec.id);
      assert.ok(a.size<characterSize(width)*.5,spec.id);
    }
  }
});
test('resize preserves individuals and adjusts their size to the girl reference',()=>{
  const w=new OceanWorld({auto:false});w.spawn('clownfish',{x:720,y:450});
  const a=w.animals[0],size=a.size,radius=a.radius;
  w.resize(390,700);assert.equal(w.animals[0],a);
  assert.ok(Math.abs(a.size-size*132/150)<.0001);assert.ok(Math.abs(a.radius-radius*132/150)<.0001);
  assert.equal(w.maxAnimals,20);assert.equal(a.x,195);
  w.resize(1440,900);assert.ok(Math.abs(a.size-size)<.0001);
});
test('school size varies from six to ten while respecting capacity',()=>{
  const counts=new Set();
  for(let seed=1;seed<=30;seed++){
    const w=new OceanWorld({auto:false,seed});const group=w.spawn('sardines');
    counts.add(group.length);assert.ok(group.length>=6&&group.length<=10);
    assert.ok(new Set(group.map(a=>a.phase)).size===group.length);
  }
  assert.deepEqual([...counts].sort((a,b)=>a-b),[6,7,8,9,10]);
  const w=new OceanWorld({auto:false,maxAnimals:6});w.spawn('clownfish');
  assert.equal(w.spawn('anchovies',{count:7}).length,5);
});
for(const s of SPECIES)for(const dir of [-1,1])test(`${s.id} enters and exits without visible respawn, direction ${dir}`,()=>{
  const w=new OceanWorld({auto:false,seed:13});const animals=w.spawn(s.id,{dir});
  assert.ok(animals.every(a=>dir===1?a.x+a.size<0:a.x-a.size>w.width));
  let visible=false;
  for(let n=0;n<7000&&w.animals.length;n++){
    const before=new Map(w.animals.map(a=>[a.id,{x:a.x,y:a.y}]));w.step(.1);
    for(const a of w.animals){const p=before.get(a.id);assert.ok(Number.isFinite(a.x+a.y));assert.ok(Math.hypot(a.x-p.x,a.y-p.y)<12);if(a.x>0&&a.x<w.width)visible=true;}
  }
  assert.ok(visible);assert.equal(w.animals.length,0);assert.equal(w.stats.exited,animals.length);
});
test('same-species school gathers but keeps individual spacing',()=>{
  const w=new OceanWorld({auto:false});
  w.spawn('sardines',{x:350,y:350,dir:1,count:1});w.spawn('sardines',{x:430,y:430,dir:1,count:1});w.spawn('sardines',{x:500,y:330,dir:1,count:1});
  const before=spread(w);advance(w,12);assert.ok(spread(w)<before*.9,`${spread(w)} >= ${before}`);assert.ok(w.stats.flocking>0);
  for(let i=0;i<w.animals.length;i++)for(let j=i+1;j<w.animals.length;j++){
    const a=w.animals[i],b=w.animals[j];assert.ok(Math.hypot(a.x-b.x,a.y-b.y)>a.radius+b.radius+7);
  }
});
test('different species do not join a flock',()=>{
  const w=new OceanWorld({auto:false});const [a]=w.spawn('sardines',{x:300,y:300,count:1,dir:1});const [b]=w.spawn('anchovies',{x:420,y:350,count:1,dir:1});
  assert.equal(socialSteering(a,[a,b]).flockmates,0);
});
test('head-on encounter predicts a passing side before contact',()=>{
  const w=new OceanWorld({auto:false});const[a]=w.spawn('butterflyfish',{x:350,y:500,dir:1});const[b]=w.spawn('porcupinefish',{x:800,y:500,dir:-1});
  let min=Infinity;for(let i=0;i<180;i++){w.step(.1);const[a,b]=w.animals;min=Math.min(min,Math.hypot(a.x-b.x,a.y-b.y));}
  assert.ok(min>a.radius+b.radius+12,`closest ${min}`);assert.ok(a.x>b.x,'both fish must pass, not stall');assert.ok(w.stats.avoidance>0);
});
test('timid species reacts sooner and slower species seeks the lower margin',()=>{
  const w=new OceanWorld({auto:false});const[a]=w.spawn('seahorse',{x:620,y:550,dir:1});const[b]=w.spawn('blue-spotted-ray',{x:510,y:570,dir:1});
  const timid=socialSteering(a,[a,b]);const brave=socialSteering({...a,spec:{...a.spec,shy:0}},[a,b]);
  assert.ok(timid.threat>brave.threat);advance(w,6);assert.ok(a.y>550);assert.ok(w.stats.avoidance>0);
});
test('jelly has no fear and no flock chasing',()=>{
  const w=new OceanWorld({auto:false});const[a]=w.spawn('jelly-crossota',{x:600,y:400,dir:1});const[b]=w.spawn('anglerfish',{x:700,y:400,dir:-1});
  const r=socialSteering(a,[a,b]);assert.equal(r.threat,0);assert.equal(r.flockmates,0);
});
test('density, seed repeatability, safe zones and bounded low-fps steps',()=>{
  const a=new OceanWorld({width:500,height:700,seed:99}),b=new OceanWorld({width:500,height:700,seed:99});advance(a,180);advance(b,180);assert.deepEqual(a.snapshot(),b.snapshot());assert.ok(a.animals.length<=densityLimit(500,'day'));
  const w=new OceanWorld({auto:false,safeZones:[{x:400,y:300,width:300,height:180}]});const[f]=w.spawn('clownfish',{x:500,y:320,dir:1});advance(w,4);assert.ok(f.y<320);
  const old=w.time;w.step(500);assert.ok(w.time-old<.101);
});
test('night population stays bounded, including long-lived jellies',()=>{
  for(const width of [390,1440]){
    const w=new OceanWorld({theme:'night',width,height:850,seed:51});
    for(let i=0;i<9000;i++){w.step(.1);assert.ok(w.animals.length<=densityLimit(width,'night'));assert.ok(w.animals.filter(a=>a.spec.style==='jelly').length<=(width<=600?1:2));}
  }
});
test('day population replenishes with more than the old sparse limit',()=>{
  assert.equal(densityLimit(1440,'day'),40);assert.equal(densityLimit(1440,'night'),26);
  assert.equal(densityLimit(780,'day'),28);assert.equal(densityLimit(390,'day'),20);
  for(const width of [390,780,1440]){
    const w=new OceanWorld({width,height:850,seed:51});let visiblePeak=0;
    for(let i=0;i<1800;i++){
      w.step(.1);assert.ok(w.animals.length<=densityLimit(width,'day'));
      visiblePeak=Math.max(visiblePeak,w.animals.filter(a=>a.x>0&&a.x<w.width).length);
    }
    assert.ok(visiblePeak>5,`only ${visiblePeak} visible at ${width}`);
  }
});
test('shoals occupy a loose area rather than a straight line',()=>{
  const w=new OceanWorld({auto:false});const[a,b,c]=w.spawn('sardines',{count:9,x:700,y:450,dir:1});
  const area=Math.abs((b.x-a.x)*(c.y-a.y)-(c.x-a.x)*(b.y-a.y))/2;
  assert.ok(area>a.size*a.size*.25);assert.ok(w.animals.every(f=>f.flockmates===0));
  advance(w,4);assert.ok(w.animals.every(f=>f.flockmates>=3));
  assert.ok(new Set(w.animals.map(f=>f.vy.toFixed(2))).size>4,'individuals must steer independently');
});
test('nearby same-species groups can gather without a permanent group boundary',()=>{
  const w=new OceanWorld({auto:false});const groupA=w.spawn('sardines',{x:500,y:400,dir:1,count:4});
  const groupB=w.spawn('sardines',{x:620,y:455,dir:1,count:4});
  assert.notEqual(groupA[0].group,groupB[0].group);
  const response=socialSteering(groupA[0],[groupA[0],...groupB]);
  assert.ok(response.flockmates>0);
  const before=spread(w);advance(w,15);assert.ok(spread(w)<before*.85);
});
test('a shoal loosens around a passing larger animal and then gathers again',()=>{
  const w=new OceanWorld({auto:false});const group=w.spawn('sardines',{count:9,x:550,y:430,dir:1});
  const[ray]=w.spawn('blue-spotted-ray',{x:770,y:430,dir:-1});
  let minimumClearance=Infinity,maximumFear=0,encounterSpread=0;
  for(let i=0;i<200;i++){
    w.step(.1);
    minimumClearance=Math.min(minimumClearance,...group.map(a=>Math.hypot(a.x-ray.x,a.y-ray.y)-a.radius-ray.radius));
    maximumFear=Math.max(maximumFear,...group.map(a=>a.fear));
    if(i>=50&&i<=120)encounterSpread=Math.max(encounterSpread,spread({animals:group}));
  }
  assert.ok(minimumClearance>0);assert.ok(maximumFear>.2);
  assert.ok(spread({animals:group})<encounterSpread*.75);
  assert.ok(group.every(a=>a.fear<.01));
});
test('non-schooling animals never acquire a following attraction',()=>{
  for(const s of SPECIES.filter(s=>!s.school)){
    const w=new OceanWorld({auto:false});const[a]=w.spawn(s.id,{x:400,y:450});const[b]=w.spawn(s.id,{x:500,y:450});
    assert.equal(socialSteering(a,[a,b]).flockmates,0,s.id);
  }
});
test('respawning reserves space for a shoal instead of filling all gaps with solitary fish',()=>{
  const w=new OceanWorld({width:1440,auto:true,maxAnimals:10});
  for(let i=0;i<5;i++)w.spawn('clownfish',{x:300+i*120,y:700,count:1});
  w.step(.1);assert.equal(w.animals.length,5);
  w.animals.pop();w.nextSpawn=0;w.step(.1);
  assert.equal(w.animals.filter(a=>a.spec.school>0).length,6);
});

test('ambient decorations use bounded responsive counts and stay understated',()=>{
  for(const width of [390,780,1440])for(const theme of ['day','night']){
    const water=new WaterAtmosphere({width,height:830,theme});
    const frame=water.frame(17);
    assert.ok(frame.bubbles.length<=6&&frame.bubbles.length>=2);
    assert.equal(frame.currents.length,2);assert.ok(frame.snow.length<=72);
    assert.ok(frame.bubbles.every(b=>b.alpha<=.66));
    assert.ok(frame.currents.every(c=>c.alpha<=.38));
    assert.ok(frame.snow.every(d=>d.alpha<=.34));
    assert.ok(frame.streams.length>=4&&frame.streams.length<=7);
    assert.ok(frame.streams.every(s=>s.alpha<=.20));
    for(const b of frame.bubbles){
      assert.equal(b.beads.length,3);
      assert.ok(b.beads.every(bead=>bead.radius>=2&&bead.radius<=7));
    }
  }
});
test('seaweed roots remain attached to the same terrain in both themes',()=>{
  for(const [width,height] of [[1440,830],[780,680],[390,540]]){
    const day=new SeabedDetails({width,height}),night=new SeabedDetails({width,height,theme:'night'});
    const roots=day.frame(0).seaweed.map(leaf=>leaf.spine[0]);
    assert.deepEqual(roots,night.frame(20).seaweed.map(leaf=>leaf.spine[0]));
    assert.deepEqual(roots,day.frame(40).seaweed.map(leaf=>leaf.spine[0]));
    assert.ok(roots.filter(p=>p.x>0&&p.x<width&&p.y<height+50).length>=3);
    assert.notDeepEqual(day.frame(0).seaweed.map(leaf=>leaf.spine.at(-1)),day.frame(8).seaweed.map(leaf=>leaf.spine.at(-1)));
  }
});
test('terrain mapping follows centered cover without warping or moving the painting',()=>{
  for(const [width,height]of [[1440,830],[780,680],[390,540]]){
    const fit=terrainFit(width,height);
    assert.ok(fit.scale*1536>=width&&fit.scale*1024>=height);
    assert.equal(fit.x+1536*fit.scale/2,width/2);
    assert.equal(fit.y+1024*fit.scale/2,height/2);
  }
});
test('seaweed tips stay restrained and neighboring leaves are not rigid copies',()=>{
  const details=new SeabedDetails({width:1440,height:830});
  const initial=details.frame(0).seaweed;
  for(let t=0;t<160;t+=.5){
    const frame=details.frame(t).seaweed;
    for(let i=0;i<frame.length;i++){
      assert.ok(Math.abs(frame[i].spine.at(-1).x-initial[i].spine.at(-1).x)<22);
      assert.ok(frame[i].spine.every(p=>Number.isFinite(p.x+p.y+p.halfWidth)));
    }
  }
  const later=details.frame(8).seaweed;
  const movement=later.map((leaf,i)=>(leaf.spine.at(-1).x-initial[i].spine.at(-1).x).toFixed(2));
  assert.ok(new Set(movement).size>10);
});
test('day favors painted waterlight while night has more marine snow',()=>{
  const day=new SeabedDetails({width:1440,height:830}).frame(11);
  const night=new SeabedDetails({width:1440,height:830,theme:'night'}).frame(11);
  assert.equal(day.snow.length,48);assert.equal(night.snow.length,72);
  assert.equal(day.waterlight.length,7);
  day.waterlight.forEach((light,i)=>{
    assert.ok(light.alpha>night.waterlight[i].alpha*5);
    assert.equal(light.x,night.waterlight[i].x);assert.equal(light.y,night.waterlight[i].y);
    assert.ok(light.y>830*.75);assert.ok(light.alpha<=.19);
  });
  assert.ok(night.waterlight.every(p=>p.alpha<=.035));
});
test('marine snow descends slowly at different depths with invisible wrapping',()=>{
  const details=new SeabedDetails({width:390,height:540,theme:'night'});
  let last=details.frame(0).snow;
  for(let t=.2;t<600;t+=.2){
    const current=details.frame(t).snow;
    current.forEach((p,i)=>{
      const old=last[i];
      if(p.y<old.y)assert.ok(old.y>540&&p.y<0);
      else assert.ok(p.y-old.y<.8);
      if(Math.abs(p.x-old.x)>5)assert.ok(p.x<0&&old.x>390);
      assert.ok(p.size<1.3);assert.ok(p.alpha<=.34);
    });
    last=current;
  }
});
test('all seabed details share a deterministic pause-safe time sample',()=>{
  const details=new SeabedDetails({width:780,height:680});
  assert.deepEqual(details.frame(18),details.frame(18));
  assert.deepEqual(details.frame(NaN),details.frame(0));
  assert.deepEqual(details.frame(-100),details.frame(0));
  assert.notDeepEqual(details.frame(18).waterlight,details.frame(20).waterlight);
});
test('bubble contours remain small and visible throughout the cycle',()=>{
  for(const width of [390,780,1440])for(const theme of ['day','night']){
    const height=width<=600?350:830;
    const water=new WaterAtmosphere({width,height,theme});
    for(let t=0;t<=180;t+=1){
      const visible=water.frame(t).bubbles.filter(b=>b.y>20&&b.y<height-20&&b.alpha>.4);
      assert.ok(visible.length>=1,`no visible bubble group ${width}/${theme} at ${t}`);
      assert.ok(visible.every(b=>b.beads.every(bead=>bead.radius*2<15)));
    }
  }
});
test('ambient motion is deterministic and frozen when scene time is unchanged',()=>{
  const a=new WaterAtmosphere({width:1440,height:830}),b=new WaterAtmosphere({width:1440,height:830});
  assert.deepEqual(a.frame(30),a.frame(30));assert.deepEqual(a.frame(30),b.frame(30));
  assert.notDeepEqual(a.frame(30),a.frame(31));
  assert.deepEqual(a.frame(-1),a.frame(0));assert.deepEqual(a.frame(NaN),a.frame(0));
});
test('bubble wrap happens only beyond the screen and moves upward gradually',()=>{
  const water=new WaterAtmosphere({width:780,height:620,theme:'night'});
  let last=water.frame(0);
  for(let t=.1;t<240;t+=.1){
    const frame=water.frame(t);
    for(let i=0;i<frame.bubbles.length;i++){
      const a=last.bubbles[i],b=frame.bubbles[i];
      if(b.y>a.y)assert.ok(a.y+a.height/2<0&&b.y-b.height/2>water.height);
      else assert.ok(a.y-b.y<1.2);
      assert.ok(Math.abs(a.x-b.x)<.2);
    }
    last=frame;
  }
});
test('replacement shoal starts outside without an unnecessary full-group entry delay',()=>{
  for(const id of ['sardines','anchovies','lanternfish'])for(const dir of [-1,1]){
    const w=new OceanWorld({width:390,height:540,auto:false});
    const group=w.spawn(id,{dir,count:5});
    const closest=Math.min(...group.map(a=>dir===1?-a.x:a.x-w.width));
    assert.ok(closest<group[0].size*1.7);
    assert.ok(group.every(a=>dir===1?a.x+a.size<0:a.x-a.size>w.width));
    advance(w,3);assert.ok(group.some(a=>a.x>0&&a.x<w.width),id);
  }
});
