import React, { useEffect, useRef, useState } from 'react';
import { X, ExternalLink, Settings2, Link2, Download, CalendarDays, ListVideo, SlidersHorizontal, CircleHelp, Check, Cable, Folder } from 'lucide-react';
import ScheduleFields from './ScheduleFields.jsx';
import { scheduleFor } from '../host/schedule.js';
import { scopeMode, wholeWork } from '../host/scopes.js';

export function Modal({ title, children, onClose, busy = false }) {
  const Icon = title.includes('Bangumi') ? Link2 : title.includes('qBittorrent') ? Download : title.includes('定时') ? CalendarDays : title.includes('说明') ? CircleHelp : title.includes('追番') ? ListVideo : Settings2;
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  const busyRef = useRef(busy);
  closeRef.current = onClose;
  busyRef.current = busy;
  useEffect(() => {
    const previous = document.activeElement;
    const root = ref.current;
    root.querySelector('input, select, button')?.focus();
    const keydown = (event) => {
      if (event.key === 'Escape' && !busyRef.current) closeRef.current();
      if (event.key !== 'Tab') return;
      const nodes = [...root.querySelectorAll('button:not(:disabled), input:not(:disabled), select, a[href]')].filter((node) => node.getClientRects().length);
      if (!nodes.length) return;
      if (event.shiftKey && document.activeElement === nodes[0]) { event.preventDefault(); nodes.at(-1).focus(); }
      else if (!event.shiftKey && document.activeElement === nodes.at(-1)) { event.preventDefault(); nodes[0].focus(); }
    };
    root.addEventListener('keydown', keydown);
    return () => { root.removeEventListener('keydown', keydown); previous?.focus?.(); };
  }, []);
  return <div className="anime-modal-backdrop"><section ref={ref} className="anime-modal" role="dialog" aria-modal="true" aria-label={title}>
    <header><h2><span className="anime-modal-symbol"><Icon size={20} aria-hidden="true"/></span>{title}</h2><button type="button" className="anime-icon" title="关闭" aria-label="关闭" disabled={busy} onClick={onClose}><X size={17}/></button></header>{children}
  </section></div>;
}

function FormSection({ title, icon: Icon, children }) {
  return <fieldset className="anime-form-section"><legend><Icon size={14} aria-hidden="true"/>{title}</legend>{children}</fieldset>;
}

export function PlanForm({ record, busy, error, onSave, onClose, defaultEnqueue = false }) {
  const plan = record?.plan;
  const [form, setForm] = useState({ title: plan?.title || record?.title || '', season: (plan ? plan.season || '' : record?.season || '').replace(/^S0*/u, ''),
    mode: scopeMode(plan?.mode), tier: plan?.tier || 'browse', requireZh: plan?.requireZh || false,
    enqueue: plan?.enqueue ?? defaultEnqueue, schedule: scheduleFor(plan) });
  const field = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const catchup = wholeWork(form.mode);
  const packageMode = plan?.mode === 'movie' || ['Movie', '剧场版'].includes(record?.type) ? 'movie' : 'season_batch';
  const submit = (event) => {
    event.preventDefault();
    onSave({ ...(plan ? { id: plan.id, revision: plan.revision } : {}), ...form,
      season: form.season ? `S${String(Number(form.season)).padStart(2, '0')}` : null,
      trackId: record?.trackId || (record?.managed && !plan ? record.id : null),
      bangumiSubjectId: record?.bangumiSubjectId || null, intervalHours: form.schedule.kind === 'interval' ? form.schedule.hours : 0 });
  };
  return <Modal title={plan ? '修改追番计划' : '添加追番'} onClose={onClose} busy={busy}><form className="anime-modal-form" onSubmit={submit}>
    {error && <p role="alert" className="anime-form-error">{error}</p>}
    <FormSection title="作品与范围" icon={ListVideo}>
    <div className="anime-identity-fields">
    <label>作品名<input required maxLength={200} value={form.title} onChange={(e) => field('title', e.target.value)}/></label>
    <label>季数（可选）<input type="number" min="1" max="999" value={form.season} onChange={(e) => field('season', e.target.value)}/></label>
    </div>
    <label>查找范围<select aria-label="查找范围" value={form.mode} onChange={(e) => { const mode = e.target.value; setForm((old) => ({ ...old, mode, schedule: wholeWork(mode) && old.schedule.kind !== 'once' ? { kind: 'manual' } : old.schedule })); }}>
      <option value={packageMode}>{packageMode === 'movie' ? '整部剧场版（一次性）' : '整季合集（老番，一次性）'}</option>
      <option value="latest_regular">最新一集（新番）</option>
      <option value="missing_episodes">补齐未记录集数（截至最新已播）</option>
    </select></label>
    </FormSection>
    <FormSection title="资源要求" icon={SlidersHorizontal}>
    <label>画质<select value={form.tier} onChange={(e) => field('tier', e.target.value)}><option value="browse">轻量观看</option><option value="watch">普通观看</option><option value="premium">高画质</option></select></label>
    <label className="anime-check"><input type="checkbox" checked={form.requireZh} onChange={(e) => field('requireZh', e.target.checked)}/>必须有中文字幕</label>
    <label className="anime-check"><input type="checkbox" checked={form.enqueue} onChange={(e) => field('enqueue', e.target.checked)}/>合格后自动提交 qBittorrent</label>
    </FormSection>
    <FormSection title="运行安排" icon={CalendarDays}>
    <ScheduleFields value={form.schedule} catchup={catchup} immediate={catchup && !plan} onChange={(value) => field('schedule', value)}/>
    </FormSection>
    <div className="anime-modal-actions"><button type="button" onClick={onClose} disabled={busy}>取消</button><button className="anime-primary" disabled={busy}><Check size={16} aria-hidden="true"/>{busy ? '提交中…' : catchup && !plan ? '提交补番任务' : '保存计划'}</button></div>
  </form></Modal>;
}

export function ScheduleForm({ record, busy, error, onSave, onClose }) {
  const p = record.plan;
  const [schedule, setSchedule] = useState(scheduleFor(p));
  return <Modal title="定时安排" busy={busy} onClose={onClose}><form className="anime-modal-form" onSubmit={(event) => {
    event.preventDefault();
    onSave({ id: p.id, revision: p.revision, schedule });
  }}>
    <strong className="anime-dialog-work">{record.title}</strong>
    {error && <p role="alert" className="anime-form-error">{error}</p>}
    <ScheduleFields value={schedule} catchup={['season_batch', 'movie'].includes(p.mode)} onChange={setSchedule}/>
    {(p.paused || p.schedulePaused || p.scheduleStatus === 'paused') && <p>当前已暂停；保存时间不会恢复任务。</p>}
    <div className="anime-modal-actions"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="anime-primary" disabled={busy}>保存定时</button></div>
  </form></Modal>;
}

export function RequirementsForm({ record, busy, error, onSave, onClose }) {
  const p = record.plan;
  const [form, setForm] = useState({ mode: scopeMode(p.mode), tier: p.tier, requireZh: p.requireZh, enqueue: p.enqueue });
  const field = (key, value) => setForm((old) => ({ ...old, [key]: value }));
  return <Modal title="资源要求" busy={busy} onClose={onClose}><form className="anime-modal-form" onSubmit={(e) => { e.preventDefault(); onSave({ id: p.id, revision: p.revision, ...form }); }}>
    <strong className="anime-dialog-work">{record.title} {p.season}</strong>
    {error && <p role="alert" className="anime-form-error">{error}</p>}
    {!wholeWork(p.mode) && <label>查找范围<select aria-label="查找范围" value={form.mode} onChange={(e) => field('mode', e.target.value)}><option value="latest_regular">最新一集（新番）</option><option value="missing_episodes">补齐未记录集数（截至最新已播）</option></select></label>}
    <label>画质<select value={form.tier} onChange={(e) => field('tier', e.target.value)}><option value="browse">轻量观看</option><option value="watch">普通观看</option><option value="premium">高画质</option></select></label>
    <label className="anime-check"><input type="checkbox" checked={form.requireZh} onChange={(e) => field('requireZh', e.target.checked)}/>必须有中文字幕</label>
    <label className="anime-check"><input type="checkbox" checked={form.enqueue} onChange={(e) => field('enqueue', e.target.checked)}/>找到后自动提交 qBittorrent</label>
    <div className="anime-modal-actions"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="anime-primary" disabled={busy}>保存资源要求</button></div>
  </form></Modal>;
}

export function BangumiForm({ config, checkedAt, busy, loading, libraryStatus, count, error, onConnect, onDisconnect, onRefresh, onClose }) {
  const [token, setToken] = useState('');
  return <Modal title="连接 Bangumi" onClose={onClose} busy={busy}><form className="anime-modal-form" onSubmit={(e) => { e.preventDefault(); const value = token; setToken(''); onConnect(value); }}>
    {error && <p role="alert" className="anime-form-error">{error}</p>}
    <div className="anime-connection-summary" data-connected={config?.connected ? 'true' : 'false'}>
      <div>当前账号：{config?.connected ? config.username : '未连接'}</div>
      <div role="status">番单：{loading ? '正在读取…' : libraryStatus === 'stale' ? `显示上次缓存 · ${count} 部` : libraryStatus === 'ready' ? `已读取 ${count} 部` : '尚未读取'}</div>
      <div>最近读取：{checkedAt ? new Date(checkedAt).toLocaleString('zh-CN') : '尚未读取'}</div>
    </div>
    <label>Access Token<input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="仅保存在本机"/></label>
    <a href="https://next.bgm.tv/demo/access-token" target="_blank" rel="noreferrer">Bangumi 官方 Token 页面 <ExternalLink size={14}/></a>
    <div className="anime-modal-actions">{config?.connected && <><button type="button" disabled={busy || loading} onClick={onRefresh}>刷新番单</button><button type="button" disabled={busy} onClick={onDisconnect}>断开连接</button></>}<button className="anime-primary" disabled={busy || !token.trim()}><Link2 size={16} aria-hidden="true"/>验证并连接</button></div>
  </form></Modal>;
}

export function QbForm({ config, busy, error, onSave, onTest, onClose }) {
  const [form, setForm] = useState({ client: config?.client || 'webapi', qbittorrent_exe: config?.executable || '', download_directory: config?.download_directory || '',
    web_url: config?.web_url || 'http://127.0.0.1:8080', web_username: config?.username || '', web_password: '', auto_submit: config?.auto_submit || false });
  const [connection, setConnection] = useState('未测试');
  const field = (key, value) => { setConnection('未测试'); setForm((old) => ({ ...old, [key]: value })); };
  const values = () => { const result = { ...form }; if (!result.web_password) delete result.web_password; return result; };
  return <Modal title="配置 qBittorrent" onClose={onClose} busy={busy}><form className="anime-modal-form" onSubmit={(e) => { e.preventDefault(); onSave(values()); }}>
    {error && <p role="alert" className="anime-form-error">{error}</p>}
    <FormSection title="下载器连接" icon={Cable}>
    <label>连接方式<select value={form.client} onChange={(e) => field('client', e.target.value)}><option value="webapi">Web API</option><option value="desktop">本机桌面客户端</option></select></label>
    {form.client === 'webapi' ? <>
      <label>Web API 地址<input required type="url" value={form.web_url} onChange={(e) => field('web_url', e.target.value)}/></label>
      <div className="anime-form-columns"><label>用户名<input autoComplete="off" value={form.web_username} onChange={(e) => field('web_username', e.target.value)}/></label>
      <label>密码<input type="password" autoComplete="new-password" value={form.web_password} onChange={(e) => field('web_password', e.target.value)} placeholder={config?.password_configured ? '已保存，留空不修改' : ''}/></label>
      </div>
      <div className="anime-connection-test"><div role="status">连接状态：{connection}</div>
      <button type="button" disabled={busy} onClick={async () => { const v = values(); setConnection('测试中…'); try { const result = await onTest({ web_url: v.web_url, web_username: v.web_username, ...(v.web_password ? { web_password: v.web_password } : {}) }); setConnection(`已连接 ${result.version}`); } catch { setConnection('连接失败'); } }}><Cable size={15} aria-hidden="true"/>测试连接</button></div>
    </> : <label>程序位置<input value={form.qbittorrent_exe} onChange={(e) => field('qbittorrent_exe', e.target.value)}/></label>}
    </FormSection>
    <FormSection title="下载设置" icon={Folder}>
    <label>默认下载目录<input value={form.download_directory} onChange={(e) => field('download_directory', e.target.value)}/></label>
    <label className="anime-check"><input type="checkbox" checked={form.auto_submit} onChange={(e) => field('auto_submit', e.target.checked)}/>新计划默认勾选自动提交</label>
    </FormSection>
    <div className="anime-modal-actions"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="anime-primary" disabled={busy}>保存配置</button></div>
  </form></Modal>;
}
