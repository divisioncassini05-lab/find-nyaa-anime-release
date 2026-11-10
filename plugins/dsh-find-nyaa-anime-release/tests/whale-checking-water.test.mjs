import {test} from 'node:test';
import assert from 'node:assert/strict';
import {waterFrame,registration,drawWaterGif} from '../client/whale-checking-water.mjs';
const clip={durations:Array(16).fill(200),frames:Array.from({length:16},(_,i)=>i)};
test('one native water pulse is mapped to formation time, not restarted',()=>{
  assert.equal(waterFrame(clip,-1,3460),-1);
  assert.equal(waterFrame(clip,0,3460),0);
  assert.equal(waterFrame(clip,1730,3460),8);
  assert.equal(waterFrame(clip,3459,3460),15);
  assert.equal(waterFrame(clip,3460,3460),-1);
});
test('the seat source and gathering region use one fixed effect registration',()=>{
  const map=(x,y)=>({x:x*registration.scaleX+registration.x,y:y*registration.scaleY+registration.y});
  const seat=map(285,418),palm=map(275,247),gather=map(360,185);
  assert.ok(Math.hypot(seat.x-338,seat.y-403)<2);
  assert.ok(Math.hypot(palm.x-327,palm.y-273)<5);
  assert.ok(Math.hypot(gather.x-392,gather.y-227)<6);
});
test('water renderer uses native bitmap frames, not synthetic ribbon geometry',()=>{
  const calls=[];
  const ctx={save(){},restore(){},translate(...a){calls.push(['translate',...a]);},scale(...a){calls.push(['scale',...a]);},drawImage(...a){calls.push(['image',...a]);}};
  drawWaterGif(ctx,clip,1730,3460);
  assert.deepEqual(calls,[['translate',116,85],['scale',.78,.76],['image',8,0,0]]);
});
