import React, { useCallback, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Panel } from './Panel.jsx';
import css from './panel.css';
import { marketLibrary, marketShows, marketPlans } from './market-fixture.mjs';

const style = document.createElement('style'); style.textContent = css; document.head.append(style);
const params = new URLSearchParams(location.search);
const market = params.get('state') === 'market';
if (params.get('theme') === 'dark') document.documentElement.dataset.theme = 'dark';
const fixture = [
  { id:'demo-1', bangumiSubjectId:101, title:'葬送的芙莉莲', season:'S02', handled:5, latest:5, target:6, total:12, phase:'airing', waiting:false, pending:0, latestDelivery:{episode:5, checkedAt:'2026-11-07T10:00:00Z', sourceUrl:'https://nyaa.si/view/123456'} },
  { id:'demo-2', title:'Re:从零开始的异世界生活', season:'S04', handled:3, latest:3, target:4, total:null, phase:'airing', waiting:true, pending:0 },
  { id:'demo-3', title:'示例作品：等待核验的交付', season:'S01', handled:7, latest:8, target:8, total:12, phase:'blocked', waiting:false, pending:1 },
  { id:'demo-4', bangumiSubjectId:102, title:'紫罗兰永恒花园', season:'S01', handled:13, latest:13, target:null, total:13, phase:'completed', waiting:false, pending:0 },
];
if (params.get('state') === 'bangumi') Object.assign(fixture[0], {watchSource:'bangumi', watchedCount:10, collectionType:4, syncPending:1});
async function loadSnapshot(signal) {
  if (market) return {exists:true, shows:marketShows};
  await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 180); signal.addEventListener('abort', () => {clearTimeout(timer); reject(new DOMException('Aborted','AbortError'));}, {once:true}); });
  if (params.get('state') === 'error') throw new Error('state_read_failed');
  return { exists: true, shows: params.get('state') === 'empty' ? [] : fixture };
}
async function loadBangumi() {
  if (market) return {status:'ready', cached:true, checked_at:'2026-11-11T02:00:00Z', items:marketLibrary};
  if (params.get('state') === 'slow-library') await new Promise((resolve) => setTimeout(resolve, 2500));
  if (params.get('state') === 'connection' && !demoConnected) return { status:'not_configured', items:[] };
  if (params.get('state') === 'offline') throw new Error('bangumi_network_unavailable');
  return { status: params.get('state') === 'empty' ? 'not_configured' : 'ready', cached: true, items: params.get('state') === 'empty' ? [] : [
    { subject_id: 101, title: '葬送的芙莉莲', original_title: 'Sousou no Frieren', collection_type: 3, watched_count: params.get('state') === 'actions' ? 1 : 10, episode_count: 28, rating: 9, comment: '节奏很舒服。', tags: ['奇幻', '冒险'], type: 'TV', date:'2023-09-29', cover_url:'/fixture-cover.png', collection_date: '2026-01-08T10:00:00Z', updated_at: '2026-11-01T10:00:00Z' },
    { subject_id: 102, title: '紫罗兰永恒花园', original_title: 'Violet Evergarden', collection_type: params.get('state') === 'actions' ? 3 : 2, watched_count: 13, episode_count: 13, rating: 10, comment: '', tags: ['京都动画'], type: 'TV', collection_date: '2025-02-12T10:00:00Z', updated_at: '2025-03-01T10:00:00Z' },
    { subject_id: 103, title: '示例剧场版', original_title: 'Example Movie', collection_type: 1, watched_count: 0, episode_count: 1, rating: null, comment: '', tags: ['剧场版'], type: 'Movie', collection_date: '2026-05-02T10:00:00Z', updated_at: '2026-05-02T10:00:00Z' },
  ] };
}
async function loadConfig() {
  return { bangumi: { connected: params.get('state') === 'connection' ? demoConnected : true, username: 'preview-user', account_id: 1 }, qbittorrent: { configured: true, executable: 'qbittorrent.exe', download_directory: 'D:/Anime', web_url: null, username: null, password_configured: false } };
}
let demoConnected = false;
let demoPlans = params.get('state') === 'empty' ? [] : [{ id:'preview-plan', revision:1, trackId:'demo-1', title:'葬送的芙莉莲', season:'S02', mode:'next_tracked', tier:'browse', requireZh:false, enqueue:false, intervalHours:24, scheduleId:'preview-task', scheduleActive:true, nextCheck:'2026-11-09T10:00:00Z' }];
if (demoPlans.length) demoPlans[0].evidence = {latestFound:{episode:5,infoHash:'a'.repeat(40),canDownload:true,title:'[Example] Frieren S02E05 1080p WEB-DL',size:'1.5 GiB',checkedAt:'2026-11-07T10:00:00Z',sourceUrl:'https://nyaa.si/view/123456'}, download:{status:'not_submitted'},completedDownloads:2,completedEpisodes:[1,2]};
if (params.get('state') === 'identity') Object.assign(demoPlans[0], {title:'芙莉莲', season:null});
if (params.get('state') === 'actions') demoPlans.push({id:'completed-plan', revision:1, trackId:'demo-4', title:'紫罗兰永恒花园', mode:'season_batch', tier:'browse', requireZh:false, enqueue:false, intervalHours:0,evidence:{latestPackage:{scope:'season',infoHash:'b'.repeat(40),canDownload:true},download:{status:'completed',progress:1},foundPackage:true,completedPackage:true,completedDownloads:1,completedEpisodes:[]}});
if (params.get('state') === 'missing') {
  demoPlans[0].mode='missing_episodes';
  demoPlans[0].evidence.recordedEpisodes=[1,2,3,4,5];
  demoPlans[0].evidence.resources=[1,2,3,4,5].map(episode=>({...demoPlans[0].evidence.latestFound,episode,infoHash:String(episode).repeat(40),download:{status:episode<=2?'completed':'not_submitted'}}));
  demoPlans.push({id:'found-package',revision:1,trackId:'demo-4',title:'紫罗兰永恒花园',mode:'season_batch',tier:'browse',enqueue:false,intervalHours:0,evidence:{foundPackage:true,completedDownloads:0,latestPackage:{scope:'season',infoHash:'b'.repeat(40),canDownload:true},download:{status:'not_submitted'}}});
}
async function loadPlans() { return { plans: structuredClone(market ? marketPlans : demoPlans), schedulerAvailable:true }; }
async function saveConfig(endpoint, payload) {
  if (market) throw new Error('Documentation preview is read-only');
  if (endpoint === 'plans/download') { const p=demoPlans.find(p=>p.id===payload.id); const resource=p.evidence.resources?.find(r=>r.infoHash===payload.infoHash); if(resource) resource.download={status:'downloading',progress:.43}; else p.evidence.download={status:'downloading',progress:.43};p.revision++;return {status:'download_submitted'}; }
  if (endpoint === 'plans/requirements' || endpoint === 'plans/schedule') { const p=demoPlans.find(p=>p.id===payload.id);Object.assign(p,payload,{revision:p.revision+1});if(payload.schedule) {p.scheduleId=payload.schedule.kind==='manual'?null:'preview-task';p.scheduleActive=payload.schedule.kind!=='manual'&&!p.schedulePaused;}return {status:'saved'}; }
  if (endpoint === 'plans/schedulePause') { const p=demoPlans.find(p=>p.id===payload.id);p.schedulePaused=payload.paused;p.scheduleActive=!payload.paused;p.revision++;return {status:'saved'}; }
  if (endpoint === 'config/bangumi/connect') { demoConnected = true; return {status:'connected',username:'preview-user',account_id:1}; }
  if (endpoint === 'config/bangumi/disconnect') { demoConnected = false; return {status:'disconnected'}; }
  if (endpoint === 'plans/check') { const plan=demoPlans.find(p=>p.id===payload.id); plan.checkStatus='queued'; plan.revision++; return {status:'queued'}; }
  if (endpoint === 'plans/sync') {const plan=demoPlans.find(p=>p.id===payload.id);Object.assign(plan,{syncedEpisode:plan.evidence.latestFound.episode,collectionSync:'synced',collectionType:3,revision:plan.revision+1});return {status:'collection_synced'};}
  if (endpoint === 'plans/collection') { const plan = demoPlans.find((p) => p.id === payload.id); Object.assign(plan, {collectionType:payload.collectionType, collectionSync:'synced', paused:[2,4,5].includes(payload.collectionType) || plan.paused, revision:plan.revision+1}); return {status:'collection_synced'}; }
  if (endpoint === 'plans/save') { const old = demoPlans.find((p) => p.id === payload.id); if (old && (old.title !== payload.title || old.season !== payload.season)) throw new Error('plan_identity_change'); if (old) Object.assign(old, payload, { revision:old.revision+1 }); else demoPlans.push({ ...payload, id:`preview-${demoPlans.length+1}`, revision:1 }); }
  if (endpoint === 'plans/pause') { const plan = demoPlans.find((p) => p.id === payload.id); plan.paused = payload.paused; plan.revision++; }
  if (endpoint === 'plans/delete') demoPlans = demoPlans.filter((p) => p.id !== payload.id);
  return { status: endpoint === 'plans/save' && ['movie','season_batch'].includes(payload.mode) && (!payload.schedule || payload.schedule.kind === 'manual') ? 'queued' : 'saved', version:'v5.2.3' };
}
function Preview() {
  const [draft, setDraft] = useState('');
  const [reviewRevision,setReviewRevision]=useState(0);
  const reviewPlans=useCallback(()=>loadPlans(),[reviewRevision]);
  const review=params.get('state')==='whale-review';
  function reviewCheck(result) {
    const plan=demoPlans[0];
    plan.checkStatus=result==='start'?'running':'idle';
    if(result!=='start')plan.evidence.lastSearch={status:result,checkedAt:new Date().toISOString()};
    setReviewRevision(value=>value+1);
  }
  return <><div className="preview-label">DSH 插件界面预览 · 示例数据 · 不连接宿主、不下载</div><div className="preview-content"><Panel loadSnapshot={loadSnapshot} loadBangumi={loadBangumi} loadConfig={loadConfig} loadPlans={review?reviewPlans:loadPlans} saveConfig={saveConfig}/></div>
    {review&&<div style={{position:'fixed',bottom:8,left:8,zIndex:20,display:'flex',flexWrap:'wrap',gap:8,maxWidth:'95%',background:'#fff',padding:8,color:'#19383f'}}>
      <button onClick={()=>reviewCheck('start')}>测试：开始检查</button>
      <button onClick={()=>reviewCheck('found')}>测试：找到资源</button>
      <button onClick={()=>reviewCheck('needs_confirmation')}>测试：待处理</button>
      <button onClick={()=>reviewCheck('no_nyaa_release_for_target')}>测试：暂无更新</button>
    </div>}
  </>;
}
createRoot(document.getElementById('root')).render(<Preview/>);
