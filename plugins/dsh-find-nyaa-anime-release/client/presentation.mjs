import { hasSchedule, scheduleFor } from '../host/schedule.js';
import { syncedThrough } from './library.mjs';

export function syncErrorText(code) {
  return ({bangumi_timeout:'Bangumi 请求超时', bangumi_dns_failed:'Bangumi 地址解析失败',
    bangumi_tls_failed:'Bangumi 证书校验失败', bangumi_connection_reset:'Bangumi 连接被中断',
    bangumi_proxy_refused:'本机网络代理拒绝连接', bangumi_proxy_unsupported:'当前代理协议不受支持',
    bangumi_network_unavailable:'Bangumi 暂时无法连接', bangumi_token_required:'请先连接 Bangumi',
    bangumi_http_401:'Bangumi 登录凭据已失效', bangumi_http_403:'Bangumi 拒绝访问，请检查权限',
    bangumi_http_429:'Bangumi 请求过于频繁，请稍后重试', bangumi_account_conflict:'Bangumi 账号与当前绑定不一致',
    bangumi_connection_changed:'Bangumi 连接已变更，请刷新后重试', bangumi_binding_required:'尚未关联 Bangumi 作品',
    bangumi_invalid_subject:'Bangumi 作品关联不匹配', bangumi_invalid_response:'Bangumi 响应格式异常',
    bangumi_invalid_page:'Bangumi 分集列表不完整', bangumi_write_not_confirmed:'收藏写入尚未得到回读确认',
    bangumi_progress_not_confirmed:'分集进度尚未得到回读确认', cancelled:'同步已取消或超时'})[code]
    || (/^bangumi_http_\d{3}$/u.test(code || '') ? `Bangumi 请求失败（HTTP ${code.slice(-3)}）` : null);
}

export function collectionResultMessage(result) {
  if (result.status === 'collection_synced') return result.trackingCompleted
    ? '已同步 Bangumi 并结束追番，下载记录保留' : '已同步 Bangumi，本地下载历史保留';
  const reason = syncErrorText(result.syncError);
  if (result.status === 'collection_partial') return ['unknown_total', 'coverage_unconfirmed'].includes(result.progress)
    ? '收藏状态已同步，正篇集数范围尚未确认，未补齐分集进度'
    : `收藏状态已同步，分集进度待同步${reason ? '：' + reason : '，可重试'}`;
  return `本地状态已保存，Bangumi 待确认${reason ? '：' + reason : '，请重试同步'}`;
}

export function syncLabel(record) {
  const error = syncErrorText(record.plan?.collectionError);
  if (record.plan?.collectionSync === 'partial') return { text: '状态已同步，集数未补齐' + (error ? '：' + error : ''), tone: 'warn' };
  if (record.plan?.collectionSync === 'pending') return { text: '状态待同步' + (error ? '：' + error : ''), tone: 'warn' };
  if (record.plan?.evidence?.startSync === 'pending') return { text: '在看状态待同步', tone: 'warn' };
  if (record.plan) {
    if (!record.bangumiSubjectId) return { text: '未关联', tone: 'muted' };
    const found = record.plan.evidence?.latestFound?.episode;
    const synced = syncedThrough(record.plan);
    if (record.plan.collectionType === 2 && record.plan.collectionSync === 'synced' && record.plan.collectionProgress === 'synced') return { text: '看过，分集进度已同步', tone: 'success' };
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
