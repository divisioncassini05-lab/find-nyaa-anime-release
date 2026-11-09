import { hasSchedule, scheduleFor } from '../host/schedule.js';

export function syncLabel(record) {
  if (record.plan?.collectionSync === 'partial') return { text: '状态已同步，集数未补齐', tone: 'warn' };
  if (record.plan?.collectionSync === 'pending') return { text: '状态待同步', tone: 'warn' };
  if (record.plan?.evidence?.startSync === 'pending') return { text: '在看状态待同步', tone: 'warn' };
  if (record.plan) {
    if (!record.bangumiSubjectId) return { text: '未关联', tone: 'muted' };
    const found = record.plan.evidence?.latestFound?.episode;
    const synced = Math.max(record.plan.syncedEpisode || 0, record.watchedCount || 0);
    if (record.plan.collectionType === 2 && record.plan.collectionSync === 'synced') return { text: '看过', tone: 'success' };
    if (found) return found > synced ? { text: `可同步至 E${String(found).padStart(2, '0')}`, tone: 'muted' } : { text: '已同步', tone: 'success' };
    return { text: '暂无新进度', tone: 'muted' };
  }
  if (record.syncPending > 0) return { text: `${record.syncPending} 项待同步`, tone: 'warn' };
  if (!record.bangumiSubjectId) return { text: '未关联', tone: 'muted' };
  if (record.handled != null && record.watchedCount != null) {
    return record.handled === record.watchedCount
      ? { text: '进度一致', tone: 'success' }
      : { text: '进度不同', tone: 'muted' };
  }
  return { text: '未核验', tone: 'muted' };
}

export function progressPercent(handled, total) {
  if (!Number.isFinite(handled) || !Number.isFinite(total) || total <= 0) return null;
  return Math.min(100, Math.max(0, handled / total * 100));
}

export function nextCheckLabel(plan) {
  if (!plan) return '未设置';
  if (plan.paused || plan.schedulePaused) return '已暂停';
  if (plan.scheduleError) return '时间待确认';
  if (plan.scheduleStatus === 'ended' && scheduleFor(plan).kind === 'once') return '预约已执行';
  if (plan.scheduleId && plan.scheduleActive === false) return '已暂停';
  if (hasSchedule(plan) && !plan.scheduleId) return '定时未建立';
  if (!plan.scheduleId) return '手动检查';
  if (plan.scheduleActive !== true || plan.scheduleError) return '时间待确认';
  if (!plan.nextCheck || Number.isNaN(Date.parse(plan.nextCheck))) return '时间待确认';
  return new Date(plan.nextCheck).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function episodeRanges(values = []) {
  const numbers = [...new Set(values.filter((n) => Number.isSafeInteger(n) && n > 0))].sort((a, b) => a - b);
  const ranges = [];
  const label = (n) => `E${String(n).padStart(2, '0')}`;
  for (let i = 0; i < numbers.length; i++) {
    const start = numbers[i];
    while (numbers[i + 1] === numbers[i] + 1) i++;
    ranges.push(start === numbers[i] ? label(start) : `${label(start)}–${label(numbers[i])}`);
  }
  return ranges.length > 4 ? `${ranges.slice(0, 2).join('、')} … ${ranges.at(-1)}（共 ${numbers.length} 集）` : ranges.join('、');
}

export function planFacts(record) {
  const p = record.plan || {}; const e = p.evidence || {};
  const latest = e.latestFound || record.latestDelivery;
  const found = e.foundPackage ? (p.mode === 'movie' ? '整部电影已核验' : '整季合集已核验')
    : p.mode === 'missing_episodes' && e.recordedEpisodes?.length ? episodeRanges(e.recordedEpisodes)
      : latest?.episode ? `E${String(latest.episode).padStart(2, '0')}${latest.finalEpisode === latest.episode ? ' · 最终集' : ''}` : '尚无已核验资源';
  const downloaded = e.completedPackage ? (p.mode === 'movie' ? '整部电影' : '整季合集') : episodeRanges(e.completedEpisodes) || '尚无已核验完成的文件';
  return { found, downloaded, downloadUncertain: Boolean(p.evidenceError || e.downloadCheckIncomplete),
    checking: p.checkStatus === 'running' ? '正在检查' : p.checkStatus === 'queued' ? '已排队' : null };
}
