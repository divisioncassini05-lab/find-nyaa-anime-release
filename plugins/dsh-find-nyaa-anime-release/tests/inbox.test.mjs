import test from 'node:test';
import assert from 'node:assert/strict';
import {inboxResult} from '../client/inbox.mjs';
import {defaultView,filterRecords,primaryAction} from '../client/library.mjs';
const record={id:'new',title:'Atlas',managed:true,phase:'airing',plan:{mode:'next_tracked',evidence:{latestFound:{episode:5,canDownload:true},download:{status:'not_submitted'}}}};
test('inbox retries the failed stage without turning download or search into watched',()=>{
  assert.equal(inboxResult(record).action,'download');
  for(const [status,action] of [['download_pending','download'],['resource_review_required','check'],['downloading',null],['completed',null],['download_submitted',null]]) {
    const r={...record,plan:{...record.plan,evidence:{...record.plan.evidence,download:{status,progress:.43}}}};
    assert.equal(inboxResult(r).action,action);assert.equal(primaryAction(r).disabled,false);
  }
  assert.match(inboxResult({...record,plan:{evidence:{...record.plan.evidence,download:{status:'downloading',progress:.43}}}}).text,/43%/);
});
test('old evidence cannot be silently downloaded and no result stays honest',()=>{
  assert.equal(inboxResult({...record,plan:{evidence:{latestFound:{episode:5}}}}).action,'check');
  assert.equal(inboxResult({...record,plan:{evidence:{latestFound:{episode:5,canDownload:false},download:{status:'download_pending'}}}}).action,'check');
  const r=inboxResult({...record,plan:{scheduleId:'weekly',evidence:{lastSearch:{status:'not_yet_aired'}}}});
  assert.equal(r.text,'等待合格资源');assert.equal(r.action,null);
});
test('failed hold before any resource retries hold rather than disabling progress',()=>{
  const action=primaryAction({plan:{mode:'next_tracked',collectionType:4,collectionSync:'pending',evidence:{}}});
  assert.equal(action.kind,'retry');assert.equal(action.disabled,false);
});
test('inbox sorts failures then new results before quiet waiting and preserves completed history',()=>{
  const wait={...record,id:'wait',plan:{scheduleId:'weekly',evidence:{}}};
  const failed={...record,id:'failed',plan:{collectionSync:'pending',evidence:{}}};
  const rows=filterRecords([wait,record,failed],'plans',{...defaultView(),sort:'inbox'});
  assert.deepEqual(rows.map(r=>r.id),['failed','new','wait']);
});
