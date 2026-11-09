import test from 'node:test';
import assert from 'node:assert/strict';
import { syncLabel, progressPercent, nextCheckLabel, episodeRanges, planFacts } from '../client/presentation.mjs';

test('found resources, verified downloads and schedule uncertainty remain independent', () => {
  const facts = planFacts({plan:{checkStatus:'queued',evidence:{latestFound:{episode:12,finalEpisode:12},completedEpisodes:[1,2,3,5],downloadCheckIncomplete:true}}});
  assert.equal(facts.found, 'E12 · 最终集'); assert.equal(facts.downloaded, 'E01–E03、E05');
  assert.equal(facts.checking, '已排队'); assert.equal(facts.downloadUncertain,true);
  assert.equal(planFacts({plan:{mode:'movie',evidence:{foundPackage:true}}}).found,'整部电影已核验');
  assert.equal(nextCheckLabel({scheduleId:'a',scheduleActive:false,scheduleError:'scheduler_unavailable'}),'时间待确认');
  assert.equal(nextCheckLabel({intervalHours:4}),'定时未建立');
  assert.equal(episodeRanges([5,3,2,1,2,-1]),'E01–E03、E05');
  assert.equal(episodeRanges(Array.from({length:100},(_,i)=>i+1)),'E01–E100');
});

test('sync display does not turn missing or different progress into success', () => {
  assert.equal(syncLabel({}).text, '未关联');
  assert.equal(syncLabel({ bangumiSubjectId: 1 }).text, '未核验');
  assert.equal(syncLabel({ bangumiSubjectId: 1, handled: 2, watchedCount: 3 }).text, '进度不同');
  assert.equal(syncLabel({ bangumiSubjectId: 1, handled: 2, watchedCount: 2 }).text, '进度一致');
  assert.equal(syncLabel({ bangumiSubjectId: 1, handled: 2, watchedCount: 2, syncPending: 1 }).tone, 'warn');
});

test('progress is bounded and missing totals remain unknown', () => {
  assert.equal(progressPercent(6, 12), 50);
  assert.equal(progressPercent(20, 12), 100);
  assert.equal(progressPercent(-1, 12), 0);
  for (const pair of [[1, null], [null, 12], [1, 0], [1, NaN]]) assert.equal(progressPercent(...pair), null);
});

test('schedule display differentiates paused, manual and unverified state', () => {
  assert.equal(nextCheckLabel(null), '未设置');
  assert.equal(nextCheckLabel({}), '手动检查');
  assert.equal(nextCheckLabel({ paused: true }), '已暂停');
  assert.equal(nextCheckLabel({ scheduleId: 'x', scheduleActive: false }), '已暂停');
  assert.equal(nextCheckLabel({ scheduleId: 'x' }), '时间待确认');
  assert.equal(nextCheckLabel({ scheduleId: 'x', scheduleActive: true, nextCheck: 'bad' }), '时间待确认');
  assert.equal(nextCheckLabel({ scheduleId: 'x', scheduleActive: true, nextCheck: '2026-11-09', scheduleError: 'offline' }), '时间待确认');
  assert.notEqual(nextCheckLabel({ scheduleId: 'x', scheduleActive: true, nextCheck: '2026-11-09' }), '时间待确认');
});
