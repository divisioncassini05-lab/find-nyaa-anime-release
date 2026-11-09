import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultView, filterRecords, typeName, workSubtitle } from '../client/library.mjs';

const records = [
  { id: 'a', bangumiSubjectId: 1, bangumiStatus: 3, title: '星空旅行', originalTitle: 'Star: Journey', aliases: ['星旅'], managed: true, type: 'TV', date: '2026-07-01', watchedCount: 2, total: 12, rating: 8, tags: ['科幻'], updatedAt: '2026-11-01' },
  { id: 'b', bangumiSubjectId: 2, bangumiStatus: 2, title: '月亮', managed: false, type: 'Movie', date: '2025-01-03', watchedCount: 1, total: 1, collectionDate: '2026-10-01' },
  { id: 'c', title: '仅本地', managed: true, phase: 'airing' },
];
const ids = (view = {}, tab = 'bangumi') => filterRecords(records, tab, { ...defaultView(), ...view }).map((row) => row.id);
test('airing quarter is distinct from sequel number and missing types stay unknown', () => {
  assert.equal(typeName(null), '类型未知'); assert.equal(typeName('Web'), 'ONA'); assert.equal(typeName('剧场版'), '剧场版');
  assert.equal(workSubtitle({ season: 'S04', date: '2026-07-03', type: 'TV' }), 'S04 · 2026年7月番 · TV');
  assert.equal(workSubtitle({ date: '2025-13-01' }), '首播日期未知 · 类型未知');
});
test('library and local plans remain separate', () => {
  assert.deepEqual(ids(), ['a', 'b']);
  assert.deepEqual(ids({}, 'plans'), ['a', 'c']);
});
test('normalized names and known short aliases are searchable', () => {
  assert.deepEqual(ids({ query: 'STAR journey' }), ['a']);
  assert.deepEqual(ids({ query: '星旅' }), ['a']);
});
test('filters compose without turning types into sort keys', () => {
  assert.deepEqual(ids({ status: '在看', type: 'TV', management: 'managed', unwatched: 'yes', rated: 'yes', annotated: 'yes', year: '2026', quarter: '3' }), ['a']);
  assert.deepEqual(ids({ type: '剧场版', rated: 'no' }), ['b']);
  assert.deepEqual(ids({ quarter: '4' }), []);
  assert.equal(typeName('WEB'), 'ONA');
});
test('collection date falls back to update date and sorting is reversible', () => {
  assert.deepEqual(ids({ direction: 'asc' }), ['b', 'a']);
  assert.deepEqual(ids({ sort: 'rating', direction: 'asc' }), ['a', 'b']);
  assert.deepEqual(ids({ sort: 'watchedCount', direction: 'asc' }), ['b', 'a']);
  assert.equal(records[0].id, 'a');
});
