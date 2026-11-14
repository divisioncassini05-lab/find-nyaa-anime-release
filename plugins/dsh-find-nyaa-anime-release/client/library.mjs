import { inboxPriority, inboxResult } from './inbox.mjs';
import { packageFound, wholeWork } from '../host/scopes.js';
export const defaultView = () => ({ query: '', status: 'all', type: 'all', management: 'all', unwatched: 'all', rated: 'all', annotated: 'all', year: 'all', quarter: 'all', sort: 'collectionDate', direction: 'desc' });
export const fold = (value) => String(value || '').normalize('NFKC').toLocaleLowerCase('zh-CN').replace(/[\s\p{P}\p{S}]+/gu, '');
export const typeName = (value) => ({ movie: '剧场版', '剧场版': '剧场版', '剧场': '剧场版', tv: 'TV', ova: 'OVA', ona: 'ONA', web: 'ONA', music: '音乐', mv: '音乐', short: '短篇', special: '其他', '其他': '其他' }[String(value || '').trim().toLowerCase()] || (value ? '其他' : '类型未知'));
export function workSubtitle(record) {
  const match = /^(\d{4})-(0[1-9]|1[0-2])(?:-\d{2})?$/u.exec(record.date || '');
  const quarter = match ? `${match[1]}年${(Math.ceil(Number(match[2]) / 3) - 1) * 3 + 1}月番` : '首播日期未知';
  return [record.season, quarter, typeName(record.type)].filter(Boolean).join(' · ');
}
const statuses = { 1: '想看', 2: '看过', 3: '在看', 4: '搁置', 5: '抛弃' };
export const watchedPlan = (plan) => plan?.collectionType === 2 && plan.collectionSync === 'synced' && plan.collectionProgress === 'synced';
export const syncedThrough = (plan) => plan?.collectionProgress === 'not_requested' ? 0 : plan?.syncedEpisode || 0;
export const needsAttention = (record) => record.pending > 0 || record.syncPending > 0 || Boolean(record.plan?.scheduleError || record.plan?.evidenceError || record.plan?.evidence?.downloadCheckIncomplete) || inboxResult(record).tone === 'warn' || inboxResult(record).failedSearch || record.plan?.evidence?.startSync === 'pending' || ['pending', 'partial'].includes(record.plan?.collectionSync) || record.phase === 'blocked' || (record.phase === 'finale_pending_evidence' && !watchedPlan(record.plan));
export function planStatus(record) {
  if (watchedPlan(record.plan)) return 'completed';
  if (packageFound(record.plan)) return 'completed';
  if (record.plan?.paused) return 'paused';
  if (wholeWork(record.plan?.mode)) return 'package_pending';
  if (record.plan?.evidence?.completedPackage) return 'completed';
  return ['planned', 'finale_pending_evidence'].includes(record.phase) ? 'airing' : record.phase;
}
export const hasCompletedDownloads = (record) => (record.plan?.evidence?.completedDownloads || 0) > 0;
export const hasCompletedTask = (record) => watchedPlan(record.plan) || packageFound(record.plan) || hasCompletedDownloads(record);
export function primaryAction(record) {
  const plan = record.plan || {};
  const evidence = plan.evidence || {};
  const finished = ['season_batch', 'movie'].includes(plan.mode);
  const type = plan.collectionSync === 'synced' ? plan.collectionType : record.bangumiStatus;
  const pending = ['pending', 'partial'].includes(plan.collectionSync);
  const found = evidence.latestFound?.episode || 0;
  // A collection flag or watched count does not prove contiguous episode coverage.
  const synced = syncedThrough(plan);
  const finale = evidence.latestFound?.finalEpisode === found && found > 0;
  const done = !pending && (finished ? watchedPlan(plan) : found > 0 && synced >= found && (!finale || type === 2));
  const retryMove = pending && plan.collectionAction !== 'sync' && [2, 4, 5].includes(plan.collectionType);
  const disabled = done || (!retryMove && !finished && !found);
  const label = pending ? '重试同步' : done ? (finished ? '已标记看过' : `已同步至第 ${found} 集`)
    : finished ? (type === 2 ? '补全分集进度' : '标记看过') : found ? `同步至第 ${found} 集` : '同步进度';
  return { kind: retryMove ? 'retry' : finished ? 'watched' : 'sync', label, disabled,
    reason: done ? '分集进度已核验同步' : !finished && !found ? '尚无已核验的资源'
      : type === 2 ? '保留看过状态，核对并补齐分集进度' : undefined };
}
export function filterRecords(records, tab, view) {
  const result = records.filter((record) => {
    if (tab === 'plans' ? !record.managed : !(record.inLibrary ?? Boolean(record.bangumiSubjectId))) return false;
    const titles = [record.title, record.originalTitle, ...(record.aliases || []), ...(record.tags || [])];
    if (!titles.some((title) => fold(title).includes(fold(view.query)))) return false;
    if (view.status !== 'all' && (tab === 'plans' ? (view.status === 'completed' ? !hasCompletedTask(record) : view.status === 'blocked' ? !needsAttention(record) : planStatus(record) !== view.status || (view.status === 'airing' && record.plan?.paused)) : statuses[record.bangumiStatus] !== view.status)) return false;
    if (view.type !== 'all' && typeName(record.type) !== view.type) return false;
    if (view.management !== 'all' && record.managed !== (view.management === 'managed')) return false;
    const remaining = record.total > 0 && record.watchedCount != null && record.watchedCount < record.total;
    if (view.unwatched !== 'all' && remaining !== (view.unwatched === 'yes')) return false;
    if (view.rated !== 'all' && Boolean(record.rating > 0) !== (view.rated === 'yes')) return false;
    if (view.annotated !== 'all' && Boolean(record.comment || record.tags?.length) !== (view.annotated === 'yes')) return false;
    const year = String(record.date || '').slice(0, 4);
    const month = Number(String(record.date || '').slice(5, 7));
    if (view.year !== 'all' && year !== view.year) return false;
    if (view.quarter !== 'all' && (!month || Math.ceil(month / 3) !== Number(view.quarter))) return false;
    return true;
  });
  const value = (record) => view.sort === 'collectionDate' ? record.collectionDate || record.updatedAt : view.sort === 'updatedAt' ? record.updatedAt || record.collectionDate : record[view.sort];
  return result.sort((left, right) => {
    if (tab === 'plans' && view.sort === 'inbox') {
      const priority = inboxPriority(right) - inboxPriority(left);
      return priority || (Date.parse(right.latestDelivery?.checkedAt || right.plan?.updatedAt || '') || 0) - (Date.parse(left.latestDelivery?.checkedAt || left.plan?.updatedAt || '') || 0);
    }
    const a = value(left); const b = value(right);
    // Missing metadata stays last in either direction, rather than appearing newest.
    if (a == null || a === '') return b == null || b === '' ? 0 : 1;
    if (b == null || b === '') return -1;
    const compare = view.sort === 'title' ? String(a).localeCompare(String(b), 'zh-CN') : (typeof a === 'number' ? a : Date.parse(a) || 0) - (typeof b === 'number' ? b : Date.parse(b) || 0);
    return view.direction === 'asc' ? compare : -compare;
  });
}
