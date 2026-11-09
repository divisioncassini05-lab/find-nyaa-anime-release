export function inboxResult(record) {
  const p = record.plan || {}; const e = p.evidence || {};
  const resource = e.latestPackage || e.latestFound || record.latestDelivery;
  const download = e.download || {};
  const search = e.lastSearch;
  const failedSearch = ['resolver_failed', 'search_incomplete', 'needs_confirmation', 'latest_unresolved'].includes(search?.status)
    && (!resource?.checkedAt || Date.parse(search.checkedAt) > Date.parse(resource.checkedAt));
  const running = ['queued', 'running'].includes(p.checkStatus);
  let text = '尚无资源'; let action = null; let label = null; let tone = 'muted';
  if (resource) {
    if (download.status === 'completed') { text = '下载完成'; tone = 'success'; }
    else if (download.status === 'downloading') {
      text = download.state === 'paused' ? '下载已暂停' : '下载中';
      if (Number.isFinite(download.progress)) text += ` ${Math.floor(download.progress * 100)}%`;
    } else if (download.status === 'download_submitted') text = '已提交，待核验文件';
    else if (download.status === 'resource_review_required' || !resource.canDownload) { text = '需重新核验资源'; tone = 'warn'; action = 'check'; label = '重新核验资源'; }
    else if (download.status === 'download_pending') { text = '下载提交未完成'; tone = 'warn'; action = 'download'; label = '重试下载提交'; }
    else { text = '待下载'; action = 'download'; label = '下载此资源'; }
  } else if (running) text = p.checkStatus === 'queued' ? '查找已排队' : '正在查找资源';
  else if (failedSearch) { text = search.status === 'needs_confirmation' ? '作品或版本待确认' : '本次查找未完成'; action = 'check'; label = '重试查找'; tone = 'warn'; }
  else if (['not_yet_aired', 'no_nyaa_release_for_target', 'no_rss_candidates', 'release_unqualified'].includes(search?.status) || record.waiting) text = '等待合格资源';
  else if (!p.scheduleId) { action = 'check'; label = '开始查找'; }
  if (download.unconfirmed || e.downloadCheckIncomplete) { text += ' · 状态待刷新'; tone = 'warn'; }
  if (p.mode === 'missing_episodes' && e.resources?.length > 1) {
    const parts = e.resources.map((r) => inboxResult({ plan: { evidence: { latestFound: r, download: r.download } } }));
    const completed = parts.filter((r) => r.download.status === 'completed').length;
    const pending = parts.filter((r) => r.action === 'download').length;
    const active = parts.filter((r) => ['downloading', 'download_submitted'].includes(r.download.status)).length;
    text = [`${e.resources.length} 集已找到`, completed && `${completed} 集已下载`, active && `${active} 集下载处理中`, pending && `${pending} 集待下载`].filter(Boolean).join(' · ');
    tone = parts.some((r) => r.tone === 'warn') ? 'warn' : completed === parts.length ? 'success' : 'muted';
    action = null; label = null;
  }
  return { resource, download, text, action, label, tone, running, failedSearch };
}

export function inboxPriority(record) {
  const p = record.plan || {}; const result = inboxResult(record);
  if (['pending', 'partial'].includes(p.collectionSync) || p.scheduleError || result.tone === 'warn' || result.failedSearch) return 4;
  if (p.paused) return 0;
  const found = p.evidence?.latestFound?.episode || 0;
  if (found > Math.max(p.syncedEpisode || 0, record.watchedCount || 0) || result.action === 'download'
      || (p.evidence?.completedPackage && (p.collectionType || record.bangumiStatus) !== 2)) return 3;
  if (result.running || result.download.status === 'downloading') return 2;
  return 1;
}
