import test from 'node:test';
import assert from 'node:assert/strict';
import { primaryAction, filterRecords, defaultView, hasCompletedDownloads, planStatus } from '../client/library.mjs';

const record = {id:'a',title:'Atlas',managed:true,phase:'airing',watchedCount:1,bangumiStatus:3,
  plan:{mode:'next_tracked',evidence:{latestFound:{episode:5},completedDownloads:1,completedEpisodes:[1]}}};

test('whole season is completed on verified find, while download is independently pending',()=>{
  const season={...record,plan:{mode:'season_batch',evidence:{foundPackage:true,latestPackage:{scope:'season'},completedDownloads:0}}};
  assert.equal(planStatus(season),'completed');
  assert.equal(hasCompletedDownloads(season),false);
  assert.equal(filterRecords([season],'plans',{...defaultView(),status:'completed'}).length,1);
  assert.equal(filterRecords([season],'plans',{...defaultView(),status:'airing'}).length,0);
  assert.equal(planStatus({...season,plan:{mode:'season_batch',evidence:{}}}),'package_pending');
});

test('sync is based on found, not handled, download or broadcast next episode',()=>{
  assert.equal(primaryAction({...record,handled:0,target:99}).disabled,false);
  assert.equal(primaryAction(record).label,'同步至第 5 集');
  assert.equal(primaryAction({...record,plan:{...record.plan,syncedEpisode:5}}).disabled,true);
  assert.equal(primaryAction({...record,plan:{...record.plan,evidence:{latestFound:{episode:6}}},watchedCount:5}).disabled,false);
  assert.equal(primaryAction({...record,plan:{mode:'next_tracked'}}).disabled,true);
});
test('finale remains one Sync action until watched; catchup has Mark watched',()=>{
  const finale={...record,watchedCount:12,plan:{mode:'next_tracked',evidence:{latestFound:{episode:12,finalEpisode:12}}}};
  assert.equal(primaryAction(finale).label,'同步至第 12 集'); assert.equal(primaryAction(finale).disabled,false);
  assert.equal(primaryAction({...finale,plan:{...finale.plan,collectionType:2,collectionSync:'synced'}}).disabled,true);
  assert.equal(primaryAction({...record,plan:{mode:'season_batch'}}).label,'标记看过');
  assert.equal(primaryAction({...record,bangumiStatus:2,plan:{mode:'movie'}}).disabled,true);
});
test('completed download history survives watched, held, dropped and coexists with active tracking',()=>{
  const completed={...defaultView(),status:'completed'};
  assert.equal(filterRecords([record],'plans',completed).length,1);
  assert.equal(filterRecords([record],'plans',{...defaultView(),status:'airing'}).length,1);
  for(const collectionType of [2,4,5]) {
    const stopped={...record,plan:{...record.plan,paused:true,collectionType,collectionSync:'synced'}};
    assert.equal(hasCompletedDownloads(stopped),true);
    assert.equal(filterRecords([stopped],'plans',completed).length,1);
    assert.equal(filterRecords([stopped],'plans',{...defaultView(),status:'airing'}).length,0);
  }
  assert.equal(filterRecords([{...record,phase:'completed',plan:{mode:'next_tracked'}}],'plans',completed).length,0);
});
