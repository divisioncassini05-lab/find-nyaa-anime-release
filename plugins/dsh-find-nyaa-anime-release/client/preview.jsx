import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Panel } from './Panel.jsx';
import css from './panel.css';

const style = document.createElement('style'); style.textContent = css; document.head.append(style);
const params = new URLSearchParams(location.search);
if (params.get('theme') === 'dark') document.documentElement.dataset.theme = 'dark';
const fixture = [
  { id:'demo-1', title:'葬送的芙莉莲', season:'S02', handled:5, latest:5, target:6, total:12, phase:'airing', waiting:false, pending:0 },
  { id:'demo-2', title:'Re:从零开始的异世界生活', season:'S04', handled:3, latest:3, target:4, total:null, phase:'airing', waiting:true, pending:0 },
  { id:'demo-3', title:'示例作品：等待核验的交付', season:'S01', handled:7, latest:8, target:8, total:12, phase:'blocked', waiting:false, pending:1 },
  { id:'demo-4', title:'紫罗兰永恒花园', season:'S01', handled:13, latest:13, target:null, total:13, phase:'completed', waiting:false, pending:0 },
];
if (params.get('state') === 'bangumi') Object.assign(fixture[0], {watchSource:'bangumi', watchedCount:10, collectionType:4, syncPending:1});
async function loadSnapshot(signal) {
  await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 180); signal.addEventListener('abort', () => {clearTimeout(timer); reject(new DOMException('Aborted','AbortError'));}, {once:true}); });
  if (params.get('state') === 'error') throw new Error('state_read_failed');
  return { exists: true, shows: params.get('state') === 'empty' ? [] : fixture };
}
function Preview() {
  const [draft, setDraft] = useState('');
  return <><div className="preview-label">DSH 插件界面预览 · 示例数据 · 不连接宿主、不下载</div><div className="preview-content"><Panel loadSnapshot={loadSnapshot} openDraft={setDraft}/></div>{draft && <div className="preview-draft" role="dialog" aria-modal="true" aria-label="聊天草稿预览"><h2>聊天草稿预览</h2><textarea aria-label="请求内容" readOnly value={draft}/><button autoFocus onClick={() => setDraft('')}>关闭预览</button></div>}</>;
}
createRoot(document.getElementById('root')).render(<Preview/>);
