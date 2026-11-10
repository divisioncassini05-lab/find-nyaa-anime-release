import test from 'node:test';
import assert from 'node:assert/strict';
import {CheckingCharacter} from '../client/whale-checking-character.mjs';
const clip=duration=>({durations:Array(16).fill(duration),frames:Array.from({length:16},(_,i)=>i)});
const create=()=>new CheckingCharacter({idle:clip(200),enter:clip(150),guide:clip(200),exit:clip(180),success:clip(160),attention:clip(260)},
  {clips:Object.fromEntries(['checking-enter','checking-loop','checking-exit'].map(k=>[k,{palm_anchors:Array(16).fill({x:327,y:273})}]))});
test('water cannot spawn before the hand is raised',()=>{
  const c=create();c.setChecking(true,0);
  assert.equal(c.sample(2399).state,'enter');assert.equal(c.sample(2399).canSummon,false);
  assert.equal(c.sample(2400).state,'loop');assert.equal(c.sample(2400).index,0);assert.equal(c.sample(2400).canSummon,true);
});
test('ending during entry finishes the gesture without a reverse or a fish burst',()=>{
  const c=create();c.setChecking(true,0);c.sample(600);c.setChecking(false,600);
  assert.equal(c.sample(700).state,'enter');assert.equal(c.sample(2400).state,'exit');assert.equal(c.sample(2400).canSummon,false);
  c.setChecking(true,3000);assert.equal(c.sample(3000).state,'exit');assert.equal(c.sample(5360).state,'enter');
});
test('reading clock is not used; sampling the same progress preserves the arm frame',()=>{
  const c=create();c.setChecking(true,0);const a=c.sample(2870);assert.deepEqual(c.sample(2870),a);
  assert.equal(c.sample(2870+3200).index,a.index);
});
test('stopping a later cycle waits for its own stable boundary',()=>{
  const c=create();c.setChecking(true,0);c.sample(2400);c.sample(6000);c.setChecking(false,6000);
  assert.equal(c.sample(6001).state,'loop');assert.equal(c.sample(6001).canSummon,false);
  assert.equal(c.sample(8800).state,'exit');
});

test('last formation and guiding boundary drain concurrently',()=>{
  const c=create();c.setChecking(true,0);c.finishChecking('no_update',6000,9900);
  assert.equal(c.sample(6001).canSummon,false);assert.equal(c.sample(8799).state,'loop');
  assert.equal(c.sample(8800).state,'hold');assert.equal(c.sample(9899).state,'hold');
  assert.equal(c.sample(9900).state,'exit');assert.equal(c.started,9900);
});
test('departed fish and exact stable boundary do not add a full cycle',()=>{
  const c=create();c.setChecking(true,0);c.finishChecking('no_update',6000,7100);
  assert.equal(c.sample(8800).state,'exit');assert.equal(c.started,8800);
  const d=create();d.setChecking(true,0);d.finishChecking('cancelled',5600);
  assert.equal(d.sample(5600).state,'exit');assert.equal(d.started,5600);
});
test('success and attention play once after idle bridge, then idle',()=>{
  for(const result of ['success','attention']){
    const c=create();c.setChecking(true,0);c.finishChecking(result,3000,3500);
    assert.equal(c.sample(5600).state,'exit');assert.equal(c.sample(8480).key,'idle');
    assert.equal(c.sample(8560).key,result);c.sample(20000);
    assert.equal(c.state,'idle');assert.equal(c.lastResult,result);assert.equal(c.completed,1);
    c.finishChecking(result,20001);assert.equal(c.sample(40000).state,'idle');assert.equal(c.completed,1);
  }
});
test('no update and cancel never play a result gesture',()=>{
  for(const result of ['no_update','cancelled']){
    const c=create();c.setChecking(true,0);c.finishChecking(result,3000);
    assert.equal(c.sample(8560).state,'idle');assert.equal(c.completed,1);
  }
});
test('duplicate finish preserves first outcome and never postpones closure',()=>{
  const c=create();c.setChecking(true,0);c.finishChecking('success',3000,5800);
  c.finishChecking('cancelled',4000,12000);assert.equal(c.result,'success');assert.equal(c.drainUntil,5800);
  assert.equal(c.sample(5800).state,'exit');
});
test('restart waits for committed close and feedback; latest desired state wins',()=>{
  const c=create();c.setChecking(true,0);c.finishChecking('success',3000);
  c.setChecking(true,6000);assert.equal(c.sample(6100).state,'exit');
  assert.equal(c.sample(8560).state,'feedback');assert.equal(c.sample(11120).state,'enter');
  assert.equal(c.completed,1);assert.equal(c.sample(13520).canSummon,true);
  c.finishChecking('attention',14000);c.setChecking(true,15000);c.setChecking(false,15001);
  assert.equal(c.sample(25000).state,'idle');assert.equal(c.completed,2);
});
test('sampling the same paused closing progress is stable',()=>{
  const c=create();c.setChecking(true,0);c.finishChecking('success',3000);
  const a=c.sample(6000);assert.deepEqual(c.sample(6000),a);
});
test('missing exit blocks explicitly without any old-clip fallback',()=>{
  const c=create();delete c.clips.exit;c.setChecking(true,0);c.finishChecking('cancelled',3000);
  assert.equal(c.sample(5600).state,'blocked');assert.equal(c.completed,0);assert.equal(c.sample(8000).canSummon,false);
});
test('unknown result is rejected without committing state',()=>{
  const c=create();c.setChecking(true,0);assert.throws(()=>c.finishChecking('guess',3000),TypeError);assert.equal(c.ending,false);
});
