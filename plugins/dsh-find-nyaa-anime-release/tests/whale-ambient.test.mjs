import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {WhaleAmbientTimeline} from '../client/whale-ambient-timeline.mjs';
import {AmbientScheduler,seededRandom} from '../client/whale-ambient-scheduler.mjs';
import {inkState,palmLiquidState} from '../client/whale-liquid.mjs';
const root=new URL('../assets/ocean/whale/ambient/',import.meta.url);
const manifest=JSON.parse(await readFile(new URL('manifest.json',root),'utf8'));
const durations={idle:[100,100],reading:[100,100],receive:[100],return:[100]};
const actions={feet:{mode:'idle',durations:[50,100]},trace:{mode:'reading',durations:[50,100]}};
function clock(options={}){return new WhaleAmbientTimeline(durations,actions,{minimum:50,maximum:50,...options});}

test('ambient waits for a full parent loop, retains book clock and returns to identical parent frame',()=>{
 const c=clock();c.request('idle');c.advance(75);assert.equal(c.stage,'idle');
 c.advance(125);assert.equal(c.stage,'feet');assert.equal(c.frame,0);
 c.advance(150);assert.equal(c.stage,'idle');assert.equal(c.frame,0);assert.equal(c.bookElapsed,350);
});
test('reading gestures do not interrupt the original page turn',()=>{
 const c=clock();c.request('reading');c.advance(300);assert.equal(c.stage,'reading');
 c.advance(199);assert.equal(c.stage,'reading');c.advance(1);assert.equal(c.stage,'trace');
 c.advance(150);assert.equal(c.parent,'reading');assert.equal(c.frame,0);
});
test('latest mode intent cancels pending ambient but lets a started action finish',()=>{
 const c=clock();c.request('idle');c.advance(200);assert.equal(c.stage,'feet');
 c.request('reading');c.advance(149);assert.equal(c.stage,'feet');
 c.advance(1);assert.equal(c.stage,'idle');c.advance(200);assert.equal(c.stage,'receive');
 c.advance(100);assert.equal(c.stage,'reading');
});
test('hidden, reduced or paused player freezes all clocks; blocking forbids new ambient actions',()=>{
 const c=clock();c.request('idle');c.advance(210);c.setRunning(false);
 c.advance(10000);assert.equal(c.bookElapsed,210);assert.equal(c.actionElapsed,10);
 c.setRunning(true);c.setBlocked(true);c.advance(140);assert.equal(c.stage,'idle');
 c.advance(2000);assert.equal(c.stage,'idle');
});
test('lazy decoder failure does not stall a base loop or start an unavailable clip',()=>{
 const c=clock({ready:()=>false});c.request('idle');c.advance(5000);
 assert.equal(c.stage,'idle');assert.equal(c.totalElapsed,5000);
 c.ready=()=>true;c.advance(200);assert.equal(c.stage,'feet');
});
test('separate shuffle bags do not repeat across bag boundaries; intervals stay 25-45s',()=>{
 const s=new AmbientScheduler({idle:['a','b','c'],reading:['d','e']},{random:seededRandom(10)});
 let previous=null;
 for(let i=0;i<30;i++){
  assert.ok(s.remaining>=25000&&s.remaining<=45000);s.advance(45000,true);
  const next=s.take('idle');assert.notEqual(next,previous);previous=next;
 }
});
test('only accepted five gestures and approved split layers are packaged',async()=>{
 assert.deepEqual(Object.keys(manifest.actions).sort(),['idle-droplet','idle-feet','idle-sleeve','reading-think','reading-trace']);
 for(const entry of [...Object.values(manifest.actions),...Object.values(manifest.layers)]){
  const bytes=await readFile(new URL(entry.file,root));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),entry.sha256);
  assert.equal(bytes.readUInt16LE(6),512);assert.equal(bytes.readUInt16LE(8),512);
 }
});
test('water transitions to dark ink monotonically and effects vanish before returning to rest',async()=>{
 assert.equal(inkState(500).ink,0);assert.equal(inkState(2500).ink,1);
 let before=0;for(let t=100;t<4100;t+=25){assert.ok(inkState(t).ink>=before);before=inkState(t).ink;}
 assert.equal(inkState(4500),null);
 const palm=JSON.parse(await readFile(new URL('palm-motion.json',root),'utf8'));
 assert.equal(palm.gif_sha256,manifest.actions['idle-droplet'].sha256);
 assert.equal(palmLiquidState(palm,0),null);assert.ok(palmLiquidState(palm,2000).strength>.9);
 assert.equal(palmLiquidState(palm,4700),null);
});
