import test from 'node:test';
import assert from 'node:assert/strict';
import {WhaleAmbientTimeline} from '../client/whale-ambient-timeline.mjs';
import {ReadingRetreatHandoff} from '../client/whale-reading-handoff.mjs';
import {RetreatTimeline,HOLD_MS} from '../client/whale-retreat-timeline.mjs';

const baseTimes={idle:Array(16).fill(200),reading:Array(16).fill(200),receive:Array(16).fill(140),return:Array(16).fill(150)};
const actionTimes={reading:baseTimes.reading,character:[...Array(16).fill(110),...Array(16).fill(140)],
  rise:Array(16).fill(120),hold:Array(16).fill(180),reveal:Array(16).fill(180),recover:Array(16).fill(220)};
function create(ready=true){
 const base=new WhaleAmbientTimeline(baseTimes,{},{});base.request('reading');base.advance(5440);
 const h={base,loads:0,singles:[],ready};
 h.branch=new ReadingRetreatHandoff(base,{ready:()=>h.ready?{durations:actionTimes}:null,
  load:()=>h.loads++,single:mode=>{h.singles.push(mode);base.request(mode);}});
 h.advance=ms=>{while(ms>0){const step=Math.min(100,ms);if(!h.branch.advance(step))base.advance(step);ms-=step;}};
 h.triple=()=>{h.branch.tap('idle');h.advance(80);h.branch.tap('idle');h.advance(80);h.branch.tap('idle');};
 return h;
}

test('ordinary idle/receive/return and active ambient never enter the new branch',()=>{
 const h=create();
 for(const stage of ['idle','receive','return']){h.base.base.stage=stage;assert.equal(h.branch.tap('reading'),false);}
 h.base.base.stage='reading';h.base.action='reading-think';assert.equal(h.branch.tap('idle'),false);
 assert.equal(h.loads,0);
});
test('single reading click preserves its original mode change after the counting window',()=>{
 const h=create();assert.equal(h.branch.tap('idle'),true);h.advance(1200);
 assert.deepEqual(h.singles,[]);h.advance(1);assert.deepEqual(h.singles,['idle']);
 assert.equal(h.loads,0);assert.equal(h.base.blocked,false);assert.equal(h.base.requested,'idle');
});
test('three clicks reserve reading even across an automatic return boundary',()=>{
 const h=create();h.base.base.elapsed=3190;h.triple();
 assert.equal(h.base.parent,'reading');assert.equal(h.branch.busy,true);assert.equal(h.loads,1);
 h.advance(4000);assert.equal(h.branch.actor.stage,'character');assert.deepEqual(h.singles,[]);
});
test('first actual settled reading cel finishes before the accepted close-book take',()=>{
 const h=create();h.base.base.elapsed=1400;h.triple();h.advance(1);const t=h.branch.actor;
 assert.equal(t.stage,'reading');h.advance(3200-t.readingElapsed);assert.equal(t.stage,'reading');
 assert.equal(t.sample().character.frame,0);h.advance(199);assert.equal(t.stage,'reading');
 h.advance(1);assert.equal(t.stage,'character');
});
test('complete curtain branch restores original reading and advances independent clocks exactly once',()=>{
 const h=create();h.triple();const book=h.base.bookElapsed,total=h.base.totalElapsed;
 h.advance(20500);assert.equal(h.branch.completed,1);assert.equal(h.branch.busy,false);
 assert.equal(h.base.parent,'reading');assert.equal(h.base.blocked,false);assert.equal(h.base.requested,'reading');
 assert.equal(h.base.bookElapsed-book,20500);assert.equal(h.base.totalElapsed-total,20500);
 assert.equal(h.loads,1);assert.deepEqual(h.singles,[]);
});
test('missing assets keep reading alive and decode failure releases the branch',()=>{
 const h=create(false);h.triple();h.advance(8000);
 assert.equal(h.base.parent,'reading');assert.equal(h.branch.ownsCharacter,false);assert.equal(h.loads,1);
 h.branch.fail();assert.equal(h.branch.busy,false);assert.equal(h.base.blocked,false);
});
test('checking cancels counting/loading, but waits for an already visible curtain action',()=>{
 const h=create(false);h.branch.tap('idle');assert.equal(h.branch.cancelPending(),true);
 assert.equal(h.base.blocked,false);h.triple();assert.equal(h.branch.cancelPending(),true);
 h.ready=true;h.triple();h.advance(3500);assert.equal(h.branch.actor.stage,'character');
 assert.equal(h.branch.cancelPending(),false);assert.equal(h.branch.busy,true);
});
test('pause keeps native return progress and prevents a delayed single-click on resume',()=>{
 const h=create();h.branch.tap('idle');h.base.setRunning(false);h.branch.clearClicks();
 assert.equal(h.branch.advance(5000),false);h.base.setRunning(true);h.advance(100);
 assert.deepEqual(h.singles,[]);assert.equal(h.base.blocked,false);
 h.triple();h.advance(7000);const before=JSON.stringify(h.branch.actor.sample());h.base.setRunning(false);
 h.branch.advance(5000);assert.equal(JSON.stringify(h.branch.actor.sample()),before);
});
test('repeated clicks never extend the curtain or create another queued branch',()=>{
 const h=create();h.triple();
 for(let i=0;i<210;i++){h.branch.tap('idle');h.advance(100);}
 assert.equal(h.branch.completed,1);assert.equal(h.loads,1);assert.deepEqual(h.singles,[]);
});
test('only the matching rolling 1.2 second group upgrades',()=>{
 const h=create();h.branch.tap('idle');h.advance(800);h.branch.tap('idle');h.advance(800);h.branch.tap('idle');
 assert.equal(h.branch.busy,false);assert.equal(h.loads,0);
});
test('hidden recovery plays every native cel before resetting under opaque water',()=>{
 const t=new RetreatTimeline(actionTimes);t.request('retreat');t.advance(200+4000+1920+600);
 for(let i=0;i<16;i++){assert.deepEqual(t.sample().character,{clip:'recover',frame:i});assert.equal(t.resetDone,false);t.advance(220);}
 assert.equal(t.stage,'covered');assert.equal(t.elapsed,4120);assert.equal(t.resetDone,true);assert.equal(t.resetCount,1);
 assert.deepEqual(t.sample().character,{clip:'reading',frame:0});t.advance(HOLD_MS-4120);
 assert.equal(t.stage,'reveal');assert.deepEqual(t.sample().character,{clip:'reading',frame:0});
});
