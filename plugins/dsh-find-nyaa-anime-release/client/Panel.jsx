import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, CalendarClock, Check, ChevronRight, Copy, Film, ListVideo, RefreshCw, Search, ShieldCheck, TriangleAlert, X } from 'lucide-react';
import { modes, qualities, searchRequest, trackRequest } from './requests.js';

const phaseText = { airing: '追番中', finale_pending_evidence: '待确认完结', completed: '已完结', blocked: '需处理' };
const errors = { forbidden: '当前账号无权读取追番记录', migration_required: '追番记录需要迁移，请交给 Agent 检查', invalid_state: '追番记录格式异常', state_too_large: '追番记录超出面板读取范围', invalid_data_directory: 'DSH 数据目录配置无效', state_read_failed: '无法读取 DSH 追番记录' };
const needsAttention = (s) => s.pending > 0 || s.syncPending > 0 || s.phase === 'blocked' || s.phase === 'finale_pending_evidence';
const collectionText = { 1: '想看', 2: '已看完', 3: '在看', 4: '搁置', 5: '抛弃' };
const ep = (n) => n == null ? '—' : `E${String(n).padStart(2, '0')}`;

export function Panel({ loadSnapshot, openDraft }) {
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(null);
  const [notice, setNotice] = useState('');
  const [title, setTitle] = useState('');
  const [mode, setMode] = useState('next');
  const [quality, setQuality] = useState('browse');
  const [season, setSeason] = useState('');
  const [episode, setEpisode] = useState('');
  const [requireZh, setRequireZh] = useState(false);
  const [download, setDownload] = useState(false);
  const [formError, setFormError] = useState('');
  const titleInput = useRef(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => { controller.abort(); if (active) { setLoading(false); setSnapshot(null); setError('读取超时，请重试'); } }, 8000);
    setLoading(true); setError('');
    Promise.resolve().then(() => loadSnapshot(controller.signal)).then((value) => {
      if (!active || controller.signal.aborted) return;
      if (!value || !Array.isArray(value.shows)) throw new Error('invalid_state');
      setSnapshot(value); setLoading(false);
    }).catch((e) => {
      if (active && !controller.signal.aborted) { setSnapshot(null); setError(errors[e.message] || '连接失败，请重试'); setLoading(false); }
    }).finally(() => clearTimeout(timer));
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [loadSnapshot, refresh]);
  const shows = snapshot?.shows || [];
  const visible = shows.filter((s) => (filter === 'all' || filter === 'active' && s.phase !== 'completed' || filter === 'attention' && needsAttention(s) || filter === 'completed' && s.phase === 'completed') && s.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const current = shows.find((s) => s.id === selected);
  const draft = (prompt) => {
    try { openDraft(prompt); setNotice('已请求打开聊天草稿，尚未发送'); } catch { setNotice('未能打开聊天，请复制请求后重试'); }
  };
  const makeRequest = () => searchRequest({ title, mode, quality, season, episode, requireZh, download });
  const submit = (e) => {
    e.preventDefault(); setFormError('');
    try { draft(makeRequest()); } catch (e) { setFormError(e.message); }
  };
  const copy = async () => {
    setFormError('');
    try { const prompt = makeRequest(); await navigator.clipboard.writeText(prompt); setNotice('请求已复制'); }
    catch (e) { setFormError(e.name === 'NotAllowedError' || e instanceof TypeError ? '无法访问剪贴板，请使用“在聊天中打开”' : e.message); }
  };
  return <div className="anime-panel">
    <header className="anime-heading"><div className="anime-brand"><span className="anime-mark"><Film size={24} /></span><div><h1>动漫搜索与自动追番</h1><div className="anime-eyebrow">NYAA / DSH</div></div></div><button className="anime-icon" aria-label="刷新追番记录" title="刷新追番记录" disabled={loading} onClick={() => setRefresh((n) => n + 1)}><RefreshCw size={18} className={loading ? 'anime-spin' : ''}/></button></header>
    <div className="anime-metrics"><span><strong>{loading ? '—' : shows.filter((s) => s.phase !== 'completed').length}</strong>正在追番</span><span className="anime-attention"><strong>{loading ? '—' : shows.filter(needsAttention).length}</strong>待处理</span><span><strong>{loading ? '—' : shows.filter((s) => s.phase === 'completed').length}</strong>已完结</span><span className="anime-local"><span className="anime-dot" />DSH 本地记录</span></div>
    <div className="anime-layout"><section className="anime-library" aria-label="追番列表">
      <div className="anime-toolbar"><h2><ListVideo size={19}/>追番列表</h2><span className="anime-count">{shows.length} 部</span></div>
      <div className="anime-filters"><div role="tablist" aria-label="记录状态">{[['all', '全部'], ['active', '追番中'], ['attention', '待处理'], ['completed', '已完结']].map(([key, label]) => <button key={key} role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}>{label}</button>)}</div><label className="anime-filter-input"><Search size={16}/><input aria-label="筛选追番" placeholder="筛选作品" value={query} onChange={(e) => setQuery(e.target.value)}/></label></div>
      {error ? <div className="anime-empty" role="alert"><TriangleAlert size={28}/><h3>{error}</h3><button onClick={() => setRefresh((n) => n + 1)}><RefreshCw size={16}/>重试</button></div> : loading ? <div className="anime-empty" role="status"><RefreshCw size={26} className="anime-spin"/><p>正在读取追番记录…</p></div> : !visible.length ? <div className="anime-empty"><ListVideo size={32}/><h3>{shows.length ? '没有匹配的记录' : '暂无 DSH 追番记录'}</h3><button onClick={() => { if (shows.length) { setFilter('all'); setQuery(''); } else titleInput.current?.focus(); }}>{shows.length ? '清除筛选' : '查找动漫'}<ArrowUpRight size={16}/></button></div> : <div className="anime-rows">{visible.map((s) => <button className={`anime-row ${selected === s.id ? 'is-selected' : ''}`} key={s.id} onClick={() => setSelected(selected === s.id ? null : s.id)} aria-expanded={selected === s.id}>
        <span className={`anime-tile ${needsAttention(s) ? 'warn' : s.phase === 'completed' ? 'done' : ''}`}>{s.phase === 'completed' ? <Check size={20}/> : <Film size={20}/>}</span>
        <span className="anime-work"><strong>{s.title}</strong><small>{s.season || '季数未标注'}<span>·</span>{s.total ? `${s.total} 集` : '总集数未确认'}</small></span>
        <span className="anime-progress"><strong>{ep(s.handled)}</strong><small>已交付</small></span>
        <span className={`anime-phase ${needsAttention(s) ? 'warn' : ''}`}>{s.pending ? `待核验 ${s.pending} 项` : s.syncPending ? '待同步' : s.waiting && s.phase === 'airing' ? '等待更新' : phaseText[s.phase]}</span><ChevronRight size={16}/>
      </button>)}</div>}
      {current && !loading && !error && <section className="anime-detail" aria-label="记录详情"><div className="anime-detail-heading"><h3>{current.title}</h3><button className="anime-icon" aria-label="收起详情" title="收起详情" onClick={() => setSelected(null)}><X size={16}/></button></div><dl><div><dt>已交付</dt><dd>{ep(current.handled)}</dd></div><div><dt>下一目标</dt><dd>{ep(current.target)}</dd></div><div><dt>已记录发布</dt><dd>{ep(current.latest)}</dd></div>{current.watchSource === 'bangumi' && <div><dt>Bangumi</dt><dd>{current.collectionType == null ? '待同步' : `${collectionText[current.collectionType]} · ${current.watchedCount} 集`}</dd></div>}</dl><div className="anime-detail-actions"><button disabled={current.target == null || current.phase === 'blocked' || current.pending > 0} onClick={() => draft(trackRequest(current))}><Search size={16}/>查下一集</button>{current.phase !== 'completed' && <button onClick={() => draft(trackRequest(current, 'schedule'))}><CalendarClock size={16}/>设置定时追番</button>}{needsAttention(current) && <button onClick={() => draft(trackRequest(current, 'recover'))}><ShieldCheck size={16}/>检查记录</button>}</div></section>}
    </section><aside className="anime-search"><h2><Search size={19}/>查找资源</h2><form onSubmit={submit}>
      <label>作品名称<input ref={titleInput} maxLength={300} required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="中文名、简称或英文名"/></label>
      <label>检索范围<select value={mode} onChange={(e) => setMode(e.target.value)}>{[['next','追番下一集'],['latest','最新正篇'],['episode','指定集数'],['season','完整一季'],['movie','动画电影']].map(([v,t]) => <option value={v} key={v}>{t}</option>)}</select></label>
      {mode !== 'movie' && <div className="anime-numbers"><label>季数{mode !== 'season' && <span className="anime-optional">（可选）</span>}<input type="number" min="1" max="999" required={mode === 'season'} value={season} onChange={(e) => setSeason(e.target.value)} placeholder="自动识别"/></label>{mode === 'episode' && <label>集数<input type="number" min="1" max="999" required value={episode} onChange={(e) => setEpisode(e.target.value)} placeholder="如 2"/></label>}</div>}
      <fieldset><legend>画质</legend><div className="anime-quality">{Object.entries(qualities).map(([key,text]) => <label key={key} className={quality === key ? 'selected' : ''}><input type="radio" name="anime-quality" value={key} checked={quality === key} onChange={() => setQuality(key)}/>{text}</label>)}</div></fieldset>
      <label className="anime-check"><input type="checkbox" checked={requireZh} onChange={(e) => setRequireZh(e.target.checked)}/><span>必须有中文字幕</span></label>
      <label className="anime-check"><input type="checkbox" checked={download} onChange={(e) => setDownload(e.target.checked)}/><span>合格后提交 qBittorrent</span></label>
      {formError && <p role="alert" className="anime-form-error">{formError}</p>}
      <div className="anime-submit"><button className="anime-primary" type="submit">在聊天中打开<ArrowUpRight size={17}/></button><button type="button" className="anime-icon" aria-label="复制搜索请求" title="复制搜索请求" onClick={copy}><Copy size={17}/></button></div>
    </form></aside></div>
    {notice && <div className="anime-notice" role="status"><Check size={16}/><span>{notice}</span><button className="anime-icon" aria-label="关闭提示" onClick={() => setNotice('')}><X size={15}/></button></div>}
  </div>;
}
