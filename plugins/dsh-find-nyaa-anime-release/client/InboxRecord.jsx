import React from 'react';
import { ChevronRight, ExternalLink, Download, CalendarDays, SlidersHorizontal, MoreHorizontal, Search, RotateCw, CircleCheck, CircleAlert, Clock3, Monitor, Captions } from 'lucide-react';
import { Cover } from './Cover.jsx';
import { PlanStatusActions } from './PlanStatusActions.jsx';
import { primaryAction, syncedThrough } from './library.mjs';
import { inboxResult } from './inbox.mjs';
import { planFacts, nextCheckLabel, syncLabel } from './presentation.mjs';
import { hasSchedule, scheduleLabel } from '../host/schedule.js';
import { scopeLabel, wholeWork, packageFound } from '../host/scopes.js';

const quality = { browse: '轻量观看', watch: '普通观看', premium: '高画质' };
const collection = { 2: '看过', 3: '在看', 4: '搁置', 5: '抛弃' };
export function InboxRecord({ record: r, expanded, toggle, action, busy }) {
  const p = r.plan;
  const result = inboxResult(r); const facts = planFacts(r); const sync = syncLabel(r);
  const ResultIcon = result.tone === 'warn' ? CircleAlert : result.tone === 'success' ? CircleCheck : result.download.status === 'downloading' ? Download : Clock3;
  const synced = syncedThrough(p);
  const retryCollection = primaryAction(r).kind === 'retry';
  const retry = () => retryCollection ? action('collection', r, p.collectionType) : action('sync', r);
  const autoEnabled = Boolean(p?.scheduleActive && !p.schedulePaused && !p.paused);
  const stopped = p?.paused ? collection[p.collectionType] || '已停止' : null;
  const cloudState = (p?.collectionType === 2 && p.collectionSync === 'synced') || r.bangumiStatus === 2 ? '看过'
    : !r.bangumiSubjectId && !p?.bangumiSubjectId ? '未关联' : synced ? `已同步 ${synced} 集` : '尚未同步进度';
  return <article data-tone={result.tone} className={`anime-record anime-inbox-record ${expanded ? 'is-selected' : ''}`}>
    <div className="anime-inbox-row">
      <button className="anime-inbox-work" onClick={toggle} aria-expanded={expanded} aria-label={`${r.title}详情`}>
        <ChevronRight className="anime-chevron" size={16}/><Cover url={r.coverUrl}/><span className="anime-work"><strong>{r.title}</strong><small>{[r.season, scopeLabel(p?.mode), packageFound(p) ? '已完成' : stopped].filter(Boolean).join(' · ')}</small></span>
      </button>
      <span className="anime-cell anime-found" data-found={Boolean(result.resource)} data-label="找到的资源"><strong>{facts.found}</strong>{result.resource?.checkedAt && <small>{new Date(result.resource.checkedAt).toLocaleDateString('zh-CN')}</small>}</span>
      <span className={`anime-cell ${result.tone}`} data-label="下载"><span className="anime-result-status"><ResultIcon size={15} aria-hidden="true"/><span>{result.text}</span></span>{result.download.status === 'downloading' && Number.isFinite(result.download.progress) && <progress max="1" value={result.download.progress} aria-label={`${r.title}下载进度`}/>}</span>
      <span className="anime-cell" data-label="Bangumi"><span>{cloudState}</span>{sync.tone === 'warn' && <small className="warn">{sync.text}</small>}</span>
      {p ? <PlanStatusActions record={r} busy={busy} onProgress={retry} onMove={(type) => action('collection', r, type)}/> : <button onClick={() => action('edit', r)}>接管计划</button>}
    </div>
    {expanded && <section className="anime-detail anime-inbox-detail" aria-label={`${r.title}详情`}>
      <section className="anime-inbox-section">
        <h3><Download size={15} aria-hidden="true"/>本次结果</h3>
        {p?.mode === 'missing_episodes' && p.evidence?.resources?.length > 1 ? <div className="anime-episode-results">
          {p.evidence.resources.map((resource) => {
            const item = inboxResult({ plan: { evidence: { latestFound: resource, download: resource.download } } });
            return <div className="anime-episode-result" key={resource.infoHash}>
              <strong>E{String(resource.episode).padStart(2, '0')}</strong><span>{item.text}</span>
              {resource.sourceUrl && <a href={resource.sourceUrl} target="_blank" rel="noreferrer">资源<ExternalLink size={14}/></a>}
              {item.action === 'download' && <button disabled={busy || p.paused} onClick={() => action('download', r, resource.infoHash)}><Download size={14}/>{item.label}</button>}
            </div>;
          })}
          {result.failedSearch && <p role="status">部分集数查找未完成，已找到的资源仍保留。</p>}
          {result.failedSearch && <button disabled={busy || p.paused || result.running} onClick={() => action('check', r)}><RotateCw size={14}/>重试缺集</button>}
        </div> : <>
        {result.resource?.title && <p className="anime-release-title">{result.resource.title}</p>}
        <p>{result.resource?.size && <>{result.resource.size} · </>}{result.text}</p>
        {facts.downloaded && <small>下载记录：{facts.downloaded}</small>}
        {result.failedSearch && result.resource && <p role="status">新一轮查找未完成，保留上次资源。</p>}
        <div className="anime-inbox-section-actions">
          {result.action && <button className="anime-primary" disabled={busy || p?.paused || result.running} onClick={() => action(result.action, r)}>{result.action === 'download' ? <Download size={16}/> : <Search size={16}/>} {result.label}</button>}
          {result.failedSearch && result.resource && <button disabled={busy || p?.paused || result.running} onClick={() => action('check', r)}><RotateCw size={16}/>重试查找</button>}
          {result.resource?.sourceUrl && <a href={result.resource.sourceUrl} target="_blank" rel="noreferrer">查看资源 <ExternalLink size={14}/></a>}
        </div>
        </>}
      </section>
      {p && <><section className="anime-inbox-section">
        <h3><CalendarDays size={15} aria-hidden="true"/>后续安排</h3>
        {!wholeWork(p.mode) && <label className="anime-auto-toggle"><span>自动查找新资源</span><input type="checkbox" role="switch" aria-label={`${r.title}自动查找新资源`} checked={autoEnabled} disabled={busy || Boolean(p.scheduleError) || p.paused || p.scheduleStatus === 'ended'} onChange={() => action(hasSchedule(p) && p.scheduleId ? 'schedulePause' : 'schedule', r)}/></label>}
        <p>{packageFound(p) ? '一次性检索已完成' : stopped ? `${stopped}，后续任务已停止` : hasSchedule(p) ? scheduleLabel(p) : wholeWork(p.mode) ? '一次性检索' : '未设置自动运行'}</p>
        {hasSchedule(p) && <small>下次运行：{nextCheckLabel(p)}</small>}
        {p.scheduleError && <p role="alert">定时状态未核验，请重新设置或稍后刷新。</p>}
        {!packageFound(p) && <button disabled={busy} onClick={() => action('schedule', r)}><CalendarDays size={16}/>{hasSchedule(p) ? '调整运行时间' : '设置运行时间'}</button>}
      </section>
      <section className="anime-inbox-section">
        <h3><SlidersHorizontal size={15} aria-hidden="true"/>追番要求</h3><p className="anime-requirement"><Monitor size={14} aria-hidden="true"/>{quality[p.tier]}</p><p className="anime-requirement"><Captions size={14} aria-hidden="true"/>{p.requireZh ? '必须有中文字幕' : '优先中文字幕'}</p><p className="anime-requirement"><Download size={14} aria-hidden="true"/>{p.enqueue ? '找到后自动提交下载' : '找到后手动下载'}</p>
        <button disabled={busy} onClick={() => action('requirements', r)}><SlidersHorizontal size={16}/>调整资源要求</button>
      </section></>}
      <div className="anime-inbox-secondary">
        {p && <details className="anime-more-actions"><summary><MoreHorizontal size={16}/>更多</summary><div>
          <button disabled={busy || p.paused || result.running} onClick={() => action('check', r)}>现在查找一次</button>
          {p.paused && <button disabled={busy} onClick={() => action('pause', r)}>重新启用计划</button>}
          <button disabled={busy} onClick={() => action('delete', r)}>删除本地计划</button>
        </div></details>}
        <details className="anime-secondary-info"><summary>运行与同步记录</summary><dl className="anime-detail-grid">
          <div><dt>Bangumi 同步</dt><dd>{sync.text}</dd></div>
          {p?.lastDispatch && <div><dt>最近执行</dt><dd>{new Date(p.lastDispatch).toLocaleString('zh-CN')}</dd></div>}
          {r.bangumiSubjectId && <div><dt>作品资料</dt><dd><a href={`https://bgm.tv/subject/${r.bangumiSubjectId}`} target="_blank" rel="noreferrer">Bangumi <ExternalLink size={14}/></a></dd></div>}
        </dl></details>
      </div>
    </section>}
  </article>;
}
