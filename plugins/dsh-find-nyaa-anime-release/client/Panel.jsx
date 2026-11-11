import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDownAZ, ArrowUpAZ, CalendarDays, ChevronRight, ExternalLink, Film, Filter, ListVideo, Plus, RefreshCw, Search, Settings, SlidersHorizontal, X, CircleHelp, Check, Clock3, Link2, Download, Inbox, Library, CircleAlert, CircleCheck, Radio, Star } from 'lucide-react';
import { defaultView, filterRecords, typeName, needsAttention, workSubtitle, planStatus, hasCompletedDownloads } from './library.mjs';
import { Cover } from './Cover.jsx';
import { Modal, PlanForm, ScheduleForm, RequirementsForm, BangumiForm, QbForm } from './Dialogs.jsx';
import { InboxRecord } from './InboxRecord.jsx';
import { OceanScene, useOceanMotion } from './OceanScene.jsx';
import { TelevisionIcon } from './TelevisionIcon.jsx';
import { CurrentRibbon } from './CurrentRibbon.jsx';
import { WhaleCheckStatus } from './whale-check-status.mjs';
import { syncLabel, progressPercent, nextCheckLabel, planFacts } from './presentation.mjs';
import { hasSchedule, scheduleLabel } from '../host/schedule.js';

const collectionText = { 1: '想看', 2: '看过', 3: '在看', 4: '搁置', 5: '抛弃' };
const phases = { airing: '追番中', blocked: '待处理', completed: '本季资源已交付', finale_pending_evidence: '待确认完结', planned: '待首次核验', unmanaged: '仅番单记录' };
const ep = (v) => v == null ? '未记录' : `E${String(v).padStart(2, '0')}`;
const date = (v) => v && !Number.isNaN(Date.parse(v)) ? new Date(v).toLocaleString('zh-CN') : '未记录';
const recentlySucceeded = (record) => {
  const checked = Date.parse(record.latestDelivery?.checkedAt || '');
  return Number.isFinite(checked) && Date.now() - checked >= 0 && Date.now() - checked <= 30 * 24 * 60 * 60 * 1000;
};
const errors = { panel_transport_unavailable: '插件后台未连通，请重新加载 DSH；若仍失败，请检查插件是否已启用', config_failed: '无法读写本机配置，请检查配置文件权限或格式', cancelled: '请求已取消或超时，请重试', bangumi_http_403: 'Bangumi 拒绝访问，请检查 Token 权限', bangumi_invalid_profile: 'Bangumi 返回的账号信息无效', state_read_failed: '无法读取 DSH 追番记录', migration_required: '本地记录需要迁移', invalid_state: '本地记录格式异常', forbidden: '当前账号无权执行此操作',
  invalid_schedule: '请检查执行时间，每周任务至少选择一天', invalid_time_zone: '时区无效，请选择有效的 IANA 时区', not_future: '预约时间必须晚于当前时间', time_out_of_range: '预约日期超出宿主支持范围', invalid_rule: '当前时间规则无效，请重新选择',
  plan_identity_change: '更换作品、季数或切换追番/补番请新增计划；原计划和下载历史会保留。画质、字幕和检查周期可继续修改。',
  history_check_incomplete: '资源记录核验未完成，请稍后重试；未修改 Bangumi', no_found_episode: '尚无已核验的正篇资源，未修改 Bangumi', bangumi_binding_required: '尚未确认对应的 Bangumi 条目，请先检查作品身份',
  bangumi_http_401: 'Bangumi Token 已失效', bangumi_token_required: 'Bangumi 尚未连接', bangumi_network_unavailable: 'Bangumi 暂时无法连接，本地计划仍可使用', bangumi_account_conflict: '请先断开当前账号，再连接其他账号',
  bangumi_connection_changed: '连接信息已变更，请刷新后重试', bangumi_library_incomplete: '番单尚未完整读取，请稍后重试', bangumi_read_failed: '番单读取失败，请稍后重试',
  schedule_missing: '定时任务不存在，请重新保存检查周期', scheduler_unavailable: '当前 DSH 未启用原生调度服务', plan_exists: '该作品已有计划，请修改已有计划', plan_conflict: '计划已被其他操作修改，请刷新后重试', schedule_conflict: '定时任务已变更，请刷新后重试',
  schedule_ownership_conflict: '任务归属不一致，未修改宿主任务', schedule_execution_pending: '查找已排队或正在运行，请稍后刷新', qb_auth_failed: 'qBittorrent 用户名或密码验证失败', invalid_qb_url: 'Web API 地址无效', qb_network_unavailable: '无法连接 qBittorrent', plan_operation_failed: '计划操作未完成，请刷新核对后再试' };
const networkMessages = { bangumi_timeout: 'Bangumi 请求超时，请检查网络或代理后重试', bangumi_dns_failed: '无法解析 Bangumi 地址，请检查 DNS 或代理', bangumi_tls_failed: 'Bangumi 证书验证失败，请检查系统时间或代理证书', bangumi_connection_reset: 'Bangumi 连接被重置，请检查系统代理后重试', bangumi_proxy_refused: '网络连接被拒绝，请确认本机代理正在运行', bangumi_proxy_unsupported: '当前代理协议不受支持，请使用 HTTP 或 HTTPS 代理' };
const message = (error) => error?.message === 'plan_paused' ? '计划已停止，请先重新启用计划' : networkMessages[error?.message] || errors[error?.message] || '操作未完成，请稍后重试';
Object.assign(errors, { resource_review_required: '原资源的核验条件已变化，需要重新核验；未提交下载', download_failed: '下载提交尚未确认，请刷新后重试；不会重新搜索资源', python_unavailable: '未找到可用的 Python，无法执行下载' });

export function mergeRecords(shows, items, planData) {
  const deleted = new Set(planData?.deletedTrackIds || []);
  const local = shows.filter((s) => !deleted.has(s.id)).map((s) => ({ ...s, trackId: s.id, managed: true, inLibrary: false, bangumiStatus: s.collectionType }));
  for (const plan of planData?.plans || []) {
    const record = local.find((r) => (plan.trackId && r.trackId === plan.trackId) || (plan.bangumiSubjectId && r.bangumiSubjectId === plan.bangumiSubjectId && (!plan.season || r.season === plan.season)));
    if (record) Object.assign(record, { plan, bangumiSubjectId: record.bangumiSubjectId || plan.bangumiSubjectId });
    else local.push({ id: `plan-${plan.id}`, title: plan.title, season: plan.season, trackId: plan.trackId, bangumiSubjectId: plan.bangumiSubjectId, managed: true, inLibrary: false, phase: 'planned', handled: null, target: null, plan });
  }
  const bound = new Set();
  const records = items.map((item) => {
    const record = local.find((r) => r.bangumiSubjectId === item.subject_id);
    if (record) bound.add(record.id);
    return { ...record, id: record?.id || `bangumi-${item.subject_id}`, title: item.title, originalTitle: item.original_title,
      aliases: [...(item.aliases || []), ...(record?.aliases || [])], date: item.date, total: record?.total || item.episode_count,
      phase: record?.phase || 'unmanaged', managed: Boolean(record), bangumiSubjectId: item.subject_id, inLibrary: true,
      bangumiStatus: item.collection_type, watchedCount: item.watched_count, rating: item.rating, comment: item.comment,
      tags: item.tags || [], type: item.type, coverUrl: item.cover_url, collectionDate: item.collection_date, updatedAt: item.updated_at };
  });
  return [...records, ...local.filter((r) => !bound.has(r.id))];
}
function IconButton({ label, onClick, children, disabled }) { return <button className="anime-icon" title={label} aria-label={label} onClick={onClick} disabled={disabled}>{children}</button>; }
function Record({ record: r, expanded, toggle, action, busy, tab }) {
  if (tab === 'plans') return <InboxRecord record={r} expanded={expanded} toggle={toggle} action={action} busy={busy}/>;
  const percent = progressPercent(r.watchedCount, r.total);
  return <article className={`anime-record ${expanded ? 'is-selected' : ''}`}>
    <div className="anime-row" role="button" tabIndex={0} aria-expanded={expanded} onClick={toggle} onKeyDown={(e) => { if (['Enter', ' '].includes(e.key)) { e.preventDefault(); toggle(); } }}>
      <span className="anime-work-cell"><ChevronRight className="anime-chevron" size={16}/><Cover url={r.coverUrl}/><span className="anime-work"><strong>{r.title}</strong><small>{workSubtitle(r)}</small>{r.originalTitle && <small className="anime-original">{r.originalTitle}</small>}</span></span>
      <span className="anime-progress anime-cell" data-label="已看集数"><strong>{r.watchedCount ?? '未记录'} <span>/ {r.total || '?'}</span></strong><span className="anime-progress-track" aria-hidden="true">{percent != null && <i style={{ width: `${percent}%` }}/>}</span></span>
      <span className="anime-cell anime-rating" data-label="评分">{r.rating > 0 ? <span><Star size={13} aria-hidden="true"/>{r.rating}<small>/ 10</small></span> : '未评分'}</span>
      <span className="anime-cell" data-label="Bangumi 状态"><span className="anime-collection-state" data-status={r.bangumiStatus}>{collectionText[r.bangumiStatus] || '未记录'}</span></span>
      <span className="anime-cell anime-time" data-label="收藏日期">{date(r.collectionDate || r.updatedAt)}</span>
      <span className="anime-cell" data-label="DSH 管理">{r.managed ? '已加入' : '未加入'}</span>
    </div>
    {expanded && <section className="anime-detail" aria-label={`${r.title}详情`}>
      <div className="anime-metadata">{r.tags?.length > 0 && <span>{r.tags.join('、')}</span>}{r.comment && <p>{r.comment}</p>}</div>
      <div className="anime-detail-actions">{!r.plan && <button className="anime-primary" disabled={busy} onClick={() => action('edit', r)}>开始由 DSH 管理</button>}
        {r.bangumiSubjectId && <a href={`https://bgm.tv/subject/${r.bangumiSubjectId}`} target="_blank" rel="noreferrer">Bangumi 详情 <ExternalLink size={14}/></a>}
      </div>
    </section>}
  </article>;
}

export function Panel({ loadSnapshot, loadBangumi, loadMetadata, loadConfig, loadPlans, saveConfig }) {
  const motion = useOceanMotion();
  const [filterPanels, setFilterPanels] = useState({ plans: false, bangumi: true });
  const [snapshot, setSnapshot] = useState({ shows: [] }); const [library, setLibrary] = useState({ items: [] }); const [plans, setPlans] = useState({ plans: [] }); const [config, setConfig] = useState(null);
  const [errorsBySource, setErrors] = useState({}); const [loading, setLoading] = useState(true); const [refresh, setRefresh] = useState({ sequence: 0, remote: false });
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [localTick, setLocalTick] = useState(0);
  const libraryEpoch = useRef(0);
  const loadedSequence = useRef(-1);
  const [tab, setTab] = useState('plans'); const [selected, setSelected] = useState(null); const [modal, setModal] = useState(null); const [busy, setBusy] = useState(false); const [notice, setNotice] = useState('');
  const [operationError, setOperationError] = useState('');
  const [metadataLoading, setMetadataLoading] = useState(false);
  const checkObserver = useRef(new WhaleCheckStatus());
  const [whaleCheck, setWhaleCheck] = useState({checking:false, result:null, sequence:0});
  useEffect(() => { setWhaleCheck(checkObserver.current.update(plans.plans || [])); }, [plans]);
  useEffect(() => setOperationError(''), [modal?.kind]);
  const [views, setViews] = useState(() => { try { const s = JSON.parse(localStorage.getItem('anime-panel-views') || '{}'); if (s.plans && !['all', 'airing', 'blocked', 'completed'].includes(s.plans.status)) s.plans.status = 'all'; return { plans: { ...defaultView(), ...s.plans, sort: s.plans?.inboxVersion === 1 ? s.plans.sort : 'inbox', inboxVersion: 1 }, bangumi: { ...defaultView(), ...s.bangumi } }; } catch { return { plans: { ...defaultView(), sort: 'inbox', inboxVersion: 1 }, bangumi: defaultView() }; } });
  useEffect(() => { try { localStorage.setItem('anime-panel-views', JSON.stringify(views)); } catch { /* Host storage is optional. */ } }, [views]);
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    if (loadedSequence.current !== refresh.sequence) setLoading(true);
    loadedSequence.current = refresh.sequence;
    const timer = setTimeout(() => controller.abort(), 30000);
    const loaders = [['local', () => loadSnapshot(controller.signal), setSnapshot], ['config', () => loadConfig?.(controller.signal), setConfig], ['plans', () => loadPlans?.(controller.signal), setPlans]];
    Promise.allSettled(loaders.map(async ([key, loader, setter]) => { try { const value = await loader(); if (active && value) { setter(value); setErrors((old) => ({ ...old, [key]: undefined })); } } catch (error) { if (active) setErrors((old) => ({ ...old, [key]: message(error) })); } })).finally(() => { clearTimeout(timer); if (active) setLoading(false); });
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [loadSnapshot, loadConfig, loadPlans, refresh, localTick]);
  useEffect(() => {
    const controller = new AbortController(); const epoch = ++libraryEpoch.current;
    let active = true; setLibraryLoading(true); setErrors((old) => ({ ...old, bangumi: undefined }));
    const timer = setTimeout(() => controller.abort(), 30000);
    (async () => {
      try {
        const value = await loadBangumi(controller.signal, refresh.remote);
        if (active && epoch === libraryEpoch.current) {
          setLibrary(value);
          if (value.status === 'stale') setErrors((old) => ({ ...old, bangumi: `${message({ message: value.warning })}；当前显示上次缓存` }));
        }
      } catch (error) {
        if (active && epoch === libraryEpoch.current) {
          setErrors((old) => ({ ...old, bangumi: message(error) }));
          setLibrary((old) => ['bangumi_http_401', 'bangumi_http_403', 'bangumi_token_required', 'bangumi_connection_changed'].includes(error.message)
            ? { items: [], status: 'unavailable' } : { ...old, status: 'stale' });
        }
      } finally { clearTimeout(timer); if (active && epoch === libraryEpoch.current) setLibraryLoading(false); }
    })();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [loadBangumi, refresh]);
  useEffect(() => {
    const running = (plans.plans || []).some((plan) => ['queued', 'running'].includes(plan.checkStatus));
    if (!running && !(plans.plans || []).some((plan) => (plan.scheduleActive && !plan.paused) || ['downloading', 'download_submitted'].includes(plan.evidence?.download?.status))) return;
    const timer = setInterval(() => { if (!document.hidden) setLocalTick((old) => old + 1); }, running ? 15000 : 30000);
    return () => clearInterval(timer);
  }, [plans]);
  useEffect(() => {
    if (!loadMetadata || library.status !== 'ready') return;
    const controller = new AbortController(); let active = true;
    const ids = [...new Set((library.items || []).filter((r) => !r.metadata_checked && (!r.type || !r.date)).map((r) => r.subject_id))];
    setMetadataLoading(ids.length > 0);
    (async () => {
      try {
        for (let i = 0; i < ids.length && active; i += 24) {
          const result = await loadMetadata(ids.slice(i, i + 24), controller.signal);
          if (!active) break;
          const updates = new Map(result.items.map((row) => [row.subject_id, row]));
          setLibrary((old) => ({ ...old, items: old.items.map((row) => {
            const update = updates.get(row.subject_id);
            return update ? { ...row, ...update, type: update.type || row.type, date: update.date || row.date, cover_url: row.cover_url || update.cover_url } : row;
          }) }));
        }
      } catch { /* Metadata failures never hide a successfully loaded collection. */ }
      finally { if (active) setMetadataLoading(false); }
    })();
    return () => { active = false; controller.abort(); };
  }, [loadMetadata, library.checked_at, library.account_id, library.status]);
  const records = useMemo(() => mergeRecords(snapshot.shows || [], library.items || [], plans), [snapshot, library, plans]);
  const view = views[tab]; const setField = (key, value) => setViews((old) => ({ ...old, [tab]: { ...old[tab], [key]: value } }));
  const showFilters = filterPanels[tab];
  const visible = useMemo(() => filterRecords(records, tab, view), [records, tab, view]);
  const local = records.filter((r) => r.managed); const remote = records.filter((r) => r.inLibrary);
  const years = [...new Set(remote.map((r) => String(r.date || '').slice(0, 4)).filter((v) => /^\d{4}$/u.test(v)))].sort().reverse();
  const hasFilters = Object.entries(defaultView()).some(([key, v]) => !['sort', 'direction'].includes(key) && view[key] !== v);
  const clear = () => setViews((old) => ({ ...old, [tab]: { ...defaultView(), sort: view.sort, direction: view.direction, ...(tab === 'plans' ? { inboxVersion: 1 } : {}) } }));
  const reload = (remote) => setRefresh((v) => ({ sequence: v.sequence + 1, remote }));
  const refreshAll = () => reload(true);
  async function call(endpoint, payload, success, close = true) {
    setBusy(true); setNotice(''); setOperationError('');
    try {
      if (!saveConfig) throw new Error('forbidden');
      const result = await saveConfig(endpoint, payload);
      if (endpoint.startsWith('config/bangumi/')) {
        libraryEpoch.current++;
        setLibrary({ items: [], status: 'not_configured' });
        setConfig((old) => ({ ...old, bangumi: result.status === 'connected'
          ? { connected: true, account_id: result.account_id, username: result.username } : { connected: false } }));
      }
      if (close) setModal(null); setNotice(typeof success === 'function' ? success(result) : success);
      reload(endpoint.startsWith('config/bangumi/')); return result;
    }
    catch (error) { setNotice(message(error)); setOperationError(message(error)); if (endpoint.startsWith('plans/')) reload(false); throw error; } finally { setBusy(false); }
  }
  const safely = (promise) => promise.catch(() => {});
  const syncMessage = (result) => result.status === 'collection_synced' ? '已同步 Bangumi，本地下载历史保留' : result.status === 'collection_partial' ? '收藏状态已写入，集数未完全同步，可重试' : 'Bangumi 待同步，请检查连接或作品关联后重试';
  const execute = (kind, r, infoHash) => { const p = r.plan; const payload = { id: p.id, revision: p.revision, ...(['pause', 'schedulePause'].includes(kind) ? { paused: kind === 'pause' ? !p.paused : p.scheduleActive } : {}), ...(kind === 'download' ? { infoHash: infoHash || (p.evidence.latestPackage || p.evidence.latestFound).infoHash } : {}) }; safely(call(`plans/${kind}`, payload, kind === 'sync' ? syncMessage : kind === 'download' ? (result) => ({ download_submitted: '已核验并提交原资源，等待下载完成', download_pending: '下载提交尚未确认，可重试提交，不会重新找番', resource_review_required: '原资源核验条件已变化，请重新核验；未提交下载' })[result.status] : kind === 'check' ? '本次查找已排队，原有定时安排不变' : '计划已更新')); };
  const action = (kind, r, collectionType) => {
    if (kind === 'collection') safely(call('plans/collection', { id: r.plan.id, revision: r.plan.revision, collectionType }, (result) => result.status === 'collection_synced' ? '已同步 Bangumi，本地计划保留' : result.status === 'collection_partial' ? (result.progress === 'unknown_total' || result.progress === 'coverage_unconfirmed' ? '已移入看过，全集范围尚未确认，未补齐集数' : '已移入看过，集数同步未完成，请稍后重试') : '本地状态已保存，Bangumi 未同步；请检查连接或作品关联后再次点击'));
    else if (['edit', 'schedule', 'requirements'].includes(kind)) setModal({ kind, row: r });
    else if (kind === 'delete') setModal({ kind: 'confirm', action: kind, row: r });
    else if (!r.plan) setModal({ kind: 'edit', row: r });
    else execute(kind, r, kind === 'download' ? collectionType : undefined);
  };
  const statusOptions = tab === 'plans' ? [['all', '全部'], ['airing', '追番中'], ['blocked', '待处理'], ['completed', '已完成']] : [['all', '全部'], ...[3, 1, 2, 4, 5].map((n) => [collectionText[n], collectionText[n]])];
  const options = (key, label, choices) => <label key={key}>{label}<select value={view[key]} onChange={(e) => setField(key, e.target.value)}>{choices.map(([v, name]) => <option key={v} value={v}>{name}</option>)}</select></label>;
  const close = () => { if (!busy) setModal(null); };
  const sourceError = tab === 'plans' ? errorsBySource.local || errorsBySource.plans : errorsBySource.bangumi;
  const currentLoading = tab === 'plans' ? loading : libraryLoading;
  return <div className="anime-panel">
    <OceanScene enabled={motion.enabled} reduced={motion.reduced}/>
    <div className="anime-scroll"><div className="anime-content">
    <header className="anime-heading"><div className="anime-brand"><span className="anime-mark"><TelevisionIcon size={46}/></span><div><h1>dsh-find-anime</h1><div className="anime-eyebrow">NYAA / DSH</div></div></div><div className="anime-heading-actions"><IconButton label="刷新番单" disabled={loading} onClick={refreshAll}><RefreshCw className={loading ? 'anime-spin' : ''} size={18}/></IconButton><IconButton label="插件设置" onClick={() => setModal({ kind: 'settings' })}><Settings size={18}/></IconButton><IconButton label="使用说明" onClick={() => setModal({ kind: 'help' })}><CircleHelp size={18}/></IconButton></div></header>
    <CurrentRibbon enabled={motion.enabled} reduced={motion.reduced} check={whaleCheck}/>
    <div className="anime-metrics">{[['正在追踪', local.filter((r) => !r.plan?.paused && !['completed', 'package_pending', 'watched', 'on_hold', 'dropped', 'wish'].includes(planStatus(r))).length, Radio], ['等待更新', local.filter((r) => r.waiting && !r.plan?.paused).length, Clock3], ['待处理', local.filter(needsAttention).length, CircleAlert], ['最近成功', local.filter(recentlySucceeded).length, CircleCheck], ['Bangumi 待同步', local.reduce((n, r) => n + (r.syncPending || 0) + (['pending', 'partial'].includes(r.plan?.collectionSync) ? 1 : 0), 0), RefreshCw]].map(([label, count, Icon], i) => <span key={label} className={`anime-metric-${i}`}><span><Icon size={14} aria-hidden="true"/>{label}</span><strong>{loading ? '—' : count}</strong></span>)}</div>
    <nav className="anime-tabs" role="tablist" aria-label="追番视图">{[['plans', '追番收件箱', local.length, Inbox], ['bangumi', 'Bangumi 番单', remote.length, Library]].map(([key, label, count, Icon]) => <button key={key} role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setSelected(null); }}><Icon size={18} aria-hidden="true"/>{label} <small>{count}</small></button>)}</nav>
    <section className="anime-library"><div className="anime-section-heading"><h2>{tab === 'plans' ? '资源与进度' : 'Bangumi 番单'} <small>{visible.length} 部</small></h2><div className="anime-toolbar-actions"><button className="anime-icon" aria-label="筛选与排序" title="筛选与排序" aria-expanded={showFilters} onClick={() => setFilterPanels((v) => ({ ...v, [tab]: !v[tab] }))}><Filter size={18}/></button><button className="anime-primary" onClick={() => setModal({ kind: 'edit' })}><Plus size={16}/>添加追番</button></div></div>
      <div className="anime-filters"><div className="anime-status-tabs" role="tablist" aria-label="记录状态">{statusOptions.map(([key, label]) => <button key={key} role="tab" aria-selected={view.status === key} onClick={() => setField('status', key)}>{label}</button>)}</div><label className="anime-filter-input"><Search size={16}/><input aria-label="搜索番单" placeholder="搜索名称、别名或标签" value={view.query} onChange={(e) => setField('query', e.target.value)}/></label></div>
      {showFilters && <div className="anime-filter-row anime-filter-fields">{options('type', '类型', [['all', '全部类型'], ...['TV', '剧场版', 'OVA', 'ONA', '短篇', '音乐', '其他'].map((v) => [v, v])])}{tab === 'bangumi' && <>{options('management', '管理状态', [['all', '全部'], ['managed', '已由 DSH 管理'], ['unmanaged', '仅 Bangumi 记录']])}{options('unwatched', '未看集数', [['all', '全部'], ['yes', '有未看集数'], ['no', '无已知未看集数']])}{options('rated', '评分', [['all', '全部'], ['yes', '有评分'], ['no', '无评分']])}{options('annotated', '短评或标签', [['all', '全部'], ['yes', '有'], ['no', '无']])}{options('year', '年份', [['all', '全部年份'], ...years.map((v) => [v, v])])}{options('quarter', '季度', [['all', '全部季度'], ['1', '冬季'], ['2', '春季'], ['3', '夏季'], ['4', '秋季']])}</>}</div>}
      {hasFilters && <button className="anime-clear" onClick={clear}><X size={14}/>清除筛选</button>}
      {showFilters && <div className="anime-filter-row anime-sort-row">{options('sort', '排序', [...(tab === 'plans' ? [['inbox', '待处理与新结果优先']] : []), ['collectionDate', '收藏日期'], ['updatedAt', '最近状态更新'], ['rating', '评分'], ['title', '名称'], ['watchedCount', '已看集数'], ['total', '总集数']])}<IconButton label={view.direction === 'desc' ? '降序，点击切换升序' : '升序，点击切换降序'} onClick={() => setField('direction', view.direction === 'desc' ? 'asc' : 'desc')}>{view.direction === 'desc' ? <ArrowDownAZ size={16}/> : <ArrowUpAZ size={16}/>}</IconButton></div>}
      {sourceError && <div className="anime-warning" role="alert">{sourceError}<button onClick={refreshAll}>重试</button></div>}
      {metadataLoading && <p role="status">正在补全作品类型与首播资料…</p>}
      {currentLoading && !visible.length ? <div className="anime-empty" role="status">正在读取记录…</div> : visible.length ? <div className="anime-rows"><div className={`anime-table-heading ${tab === 'plans' ? 'anime-inbox-heading' : ''}`} aria-hidden="true">{(tab === 'plans' ? ['作品', '找到的资源', '下载', 'Bangumi', '同步'] : ['作品', '已看集数', '评分', 'Bangumi 状态', '收藏日期', 'DSH 管理']).map((label) => <span key={label}>{label}</span>)}</div>{visible.map((r) => <Record key={r.id} tab={tab} record={r} busy={busy} expanded={selected === r.id} toggle={() => setSelected(selected === r.id ? null : r.id)} action={action}/>)}</div> : <div className="anime-empty"><ListVideo size={30}/><h3>{hasFilters ? '没有匹配的记录' : tab === 'plans' ? '还没有 DSH 追番计划' : '暂无 Bangumi 番单'}</h3><div className="anime-empty-actions">{hasFilters ? <button onClick={clear}>清除筛选</button> : <><button onClick={() => { setTab('bangumi'); setViews((old) => ({ ...old, bangumi: { ...defaultView(), status: '在看' } })); }}>从 Bangumi 在看中选择</button><button onClick={() => setModal({ kind: 'bangumi' })}>连接 Bangumi</button><button onClick={() => setModal({ kind: 'qb' })}>配置 qBittorrent</button></>}</div></div>}
    </section>
    <footer className="anime-footer"><span>{!errorsBySource.local && !loading && <i className="anime-dot"/>}{errorsBySource.local ? '本地记录读取失败' : loading ? '正在读取记录' : 'DSH 本地记录'}</span><span>Bangumi {libraryLoading ? '正在读取番单' : errorsBySource.bangumi || errorsBySource.config ? (library.checked_at ? `缓存 ${date(library.checked_at)} · 刷新未完成` : '暂无法核验连接') : library.checked_at ? `最近读取 ${date(library.checked_at)}` : config?.bangumi?.connected ? '账号已配置' : '未连接'}</span></footer>
    {notice && <div className="anime-notice" role="status"><span>{notice}</span><IconButton label="关闭提示" onClick={() => setNotice('')}><X size={14}/></IconButton></div>}
    </div></div>
    {modal?.kind === 'settings' && <Modal title="插件设置" onClose={close}>
      <div className="anime-settings-list">
        <button className="anime-settings-entry" aria-label="连接 Bangumi" onClick={() => setModal({ kind: 'bangumi' })}><Link2 size={20}/><span><strong>Bangumi</strong><small>{loading ? '正在读取' : errorsBySource.config ? '状态未知' : config?.bangumi?.connected ? '账号已配置' : '未连接'}</small></span><ChevronRight size={17}/></button>
        <button className="anime-settings-entry" aria-label="配置 qBittorrent" onClick={() => setModal({ kind: 'qb' })}><Download size={20}/><span><strong>qBittorrent</strong><small>{loading ? '正在读取' : errorsBySource.config ? '状态未知' : config?.qbittorrent?.configured ? '已配置' : '未配置'}</small></span><ChevronRight size={17}/></button>
        <label className="anime-settings-motion"><span>背景动态{motion.reduced && <small>系统要求减少动态，当前静止</small>}</span><input type="checkbox" role="switch" aria-label="背景动态" checked={motion.enabled} onChange={motion.toggle}/></label>
      </div>
    </Modal>}
    {modal?.kind === 'edit' && <PlanForm record={modal.row} busy={busy} error={operationError} defaultEnqueue={config?.qbittorrent?.auto_submit} onClose={close} onSave={(v) => safely(call('plans/save', v, (result) => result.status === 'queued' ? '补番任务已排队，尚不代表找到或下载成功' : result.status === 'saved_not_queued' ? '计划已保留，但任务未成功排队；请稍后在条目中开始查找' : '计划已保存，尚未自动下载'))}/>}
    {modal?.kind === 'schedule' && <ScheduleForm record={modal.row} busy={busy} error={operationError} onClose={close} onSave={(v) => safely(call('plans/schedule', v, '运行时间已保存，资源要求不变'))}/>}
    {modal?.kind === 'requirements' && <RequirementsForm record={modal.row} busy={busy} error={operationError} onClose={close} onSave={(v) => safely(call('plans/requirements', v, '资源要求已保存，运行时间不变'))}/>}
    {modal?.kind === 'bangumi' && <BangumiForm error={operationError || errorsBySource.config || errorsBySource.bangumi} config={config?.bangumi} checkedAt={library.checked_at} libraryStatus={library.status} count={library.items?.length || 0} loading={libraryLoading} busy={busy} onClose={close} onConnect={(token) => safely(call('config/bangumi/connect', { token }, '账号验证成功，正在读取番单', false))} onRefresh={refreshAll} onDisconnect={() => safely(call('config/bangumi/disconnect', {}, '已断开 Bangumi，本地计划保留', false))}/>}
    {modal?.kind === 'qb' && <QbForm error={operationError || errorsBySource.config} config={config?.qbittorrent} busy={busy} onClose={close} onSave={(v) => safely(call('config/qbittorrent/save', v, 'qBittorrent 配置已保存'))} onTest={(v) => call('config/qbittorrent/test', v, '连接测试完成，未提交下载', false)}/>}
    {modal?.kind === 'confirm' && <Modal title="删除本地追番计划" busy={busy} onClose={close}><p>删除“{modal.row.title}”的本地计划及关联定时任务。不会删除下载文件或 Bangumi 收藏。</p><div className="anime-modal-actions"><button disabled={busy} onClick={close}>取消</button><button disabled={busy} onClick={() => execute('delete', modal.row)}>确认</button></div></Modal>}
    {modal?.kind === 'help' && <Modal title="使用说明" onClose={close}><p>添加作品时设置资源要求和运行时间，之后在收件箱查看查找结果、下载进度并手动同步 Bangumi。勾选“必须有中文字幕”后只接受核验通过的中文资源。</p><p>关闭自动查找不影响正在下载的文件，也不修改 Bangumi。同步按钮按最新找到的集数更新，最终集同步后标记看过；本地任务和下载历史保留。</p></Modal>}
  </div>;
}
