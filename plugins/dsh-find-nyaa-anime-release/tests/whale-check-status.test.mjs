import test from 'node:test';
import assert from 'node:assert/strict';
import {WhaleCheckStatus} from '../client/whale-check-status.mjs';
const row = (checkStatus, status='found', checkedAt='2026-11-01T00:00:00Z', extra={}) =>
  ({id:'one', checkStatus, evidence:{lastSearch:{status, checkedAt}}, ...extra});
test('initial idle and stale success do not trigger feedback',()=>{
  const c=new WhaleCheckStatus();
  assert.equal(c.update([row('idle')]).result,null);
  assert.equal(c.update([row('queued')]).checking,true);
  assert.equal(c.update([row('idle')]).result,'no_update');
});
test('fresh host evidence determines success or attention once',()=>{
  for(const [status,result] of [['found','success'],['needs_confirmation','attention'],['not_yet_aired','no_update']]){
    const c=new WhaleCheckStatus();c.update([row('running')]);
    assert.equal(c.update([row('idle',status,'2026-11-11T00:00:00Z')]).result,result);
    assert.equal(c.update([row('idle',status,'2026-11-11T00:00:00Z')]).result,null);
  }
});
test('overlapping tasks finish together and attention is retained',()=>{
  const c=new WhaleCheckStatus();c.update([row('running'),row('queued','found',undefined,{id:'two'})]);
  assert.equal(c.update([row('idle','needs_confirmation','2026-11-11T00:00:00Z'),row('running','found',undefined,{id:'two'})]).checking,true);
  assert.equal(c.update([row('idle','needs_confirmation','2026-11-11T00:00:00Z'),row('idle','found','2026-11-11T01:00:00Z',{id:'two'})]).result,'attention');
});
test('pause and deletion cancel, unrelated evidence cannot report success',()=>{
  const c=new WhaleCheckStatus();c.update([row('running')]);
  assert.equal(c.update([row('idle','found','2026-11-11T00:00:00Z',{id:'other'})]).result,'cancelled');
  c.update([row('running')]);assert.equal(c.update([row('queued','found',undefined,{paused:true})]).result,'cancelled');
});
