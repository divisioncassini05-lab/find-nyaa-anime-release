import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtemp, readFile, writeFile, rm, stat } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { statePath, projectState, readSnapshot, snapshotHandler, CHANNEL, ENDPOINT } from '../host/snapshot.js';
import { readConfig, saveQbittorrent, testQbittorrent } from '../host/config.js';
import { searchRequest, trackRequest } from '../client/requests.js';

const sample = () => ({ version: 3, shows: [{track_id:'track-1', identity:{title:'Atlas Chronicle',season:'S02'}, progress:{handled_episode:3,latest_release_episode:4,target_episode:4}, lifecycle:{phase:'airing'}, broadcast:{total_episodes:12}, operations:{pending:{status:'prepared'},done:{status:'accepted',committed:true}}, extra:{password:'SECRET'}, outbox:[{token:'SECRET'}]}] });

test('local snapshot RPC works without an optional caller cancellation signal', async () => {
  const handler = snapshotHandler(async () => ({exists:false,shows:[]}));
  const result = await handler('snapshot', {}, undefined, {principal:{kind:'owner'}});
  assert.equal(result.ok,true); assert.deepEqual(result.value.shows,[]);
});
test('snapshot projects only approved fields and never interprets handled as watched', () => {
  const [s] = projectState(sample());
  assert.deepEqual(s,{id:'track-1',title:'Atlas Chronicle',season:'S02',handled:3,latest:4,target:4,total:12,phase:'airing',waiting:false,pending:1});
  assert.ok(!JSON.stringify(s).includes('SECRET'));
});
test('latest release excludes uncommitted receipts and private request fields', () => {
  const data = sample();
  const show = data.shows[0];
  show.operations.done = { status:'accepted', committed:true, episode:3, request:{ source_url:'https://nyaa.si/view/12345', local_path:'PRIVATE' } };
  show.deliveries = [{ operation_id:'done', accepted:true, status:'submitted_verified', checked_at:'2026-11-07T10:00:00Z', secret:'PRIVATE' }];
  assert.deepEqual(projectState(data)[0].latestDelivery, { episode:3, checkedAt:'2026-11-07T10:00:00Z', sourceUrl:'https://nyaa.si/view/12345' });
  assert.ok(!JSON.stringify(projectState(data)).includes('PRIVATE'));
  show.operations.done.request.source_url = 'https://example.com/private';
  assert.equal(projectState(data)[0].latestDelivery.sourceUrl, undefined);
  show.operations.done.committed = false;
  assert.equal(projectState(data)[0].latestDelivery, undefined);
});
test('Bangumi snapshot exposes cloud counts, not tokens or local delivery as viewing', () => {
  const data = sample();
  data.shows[0].bangumi = {watched_episodes:[1,3,3],collection_type:3,token:'SECRET'};
  data.shows[0].outbox.push({kind:'bangumi_watched',status:'pending'});
  const [s] = projectState(data);
  assert.equal(s.watchedCount,2);
  assert.equal(s.watchSource,'bangumi');
  assert.equal(s.syncPending,1);
  assert.equal(s.handled,3);
  assert.equal(s.target,4);
  data.shows[0].bangumi.collection_type = null;
  assert.equal(projectState(data)[0].target,4);
  assert.ok(!JSON.stringify(s).includes('SECRET'));
});
test('legacy, malformed, duplicate, oversized and inconsistent completed states are refused', () => {
  assert.throws(() => projectState({version:2,shows:[]}), /migration_required/);
  for (const modify of [d=>d.shows.push(d.shows[0]), d=>d.shows[0].progress.target_episode=0, d=>d.shows[0].lifecycle.phase='completed', d=>d.shows[0].identity.title='', d=>d.shows=Array(501).fill(d.shows[0])]) {
    const d=sample(); modify(d); assert.throws(()=>projectState(d),/invalid_state/);
  }
});
test('DSH paths are independent from Codex and work across platforms', () => {
  assert.equal(statePath({LOCALAPPDATA:'C:\\Users\\A\\AppData\\Local',ANIME_TRACKING_STATE:'C:\\private.json'},'win32','C:\\Users\\A'),'C:\\Users\\A\\AppData\\Local\\DSH\\AnimeRelease\\airing_watch_state.json');
  assert.equal(statePath({},'darwin','/Users/a'),'/Users/a/Library/Application Support/DSH/AnimeRelease/airing_watch_state.json');
  assert.equal(statePath({XDG_DATA_HOME:'/data'},'linux','/home/a'),'/data/dsh/anime-release/airing_watch_state.json');
  assert.equal(statePath({ANIME_DSH_HOME:'~/custom'},'linux','/home/a'),'/home/a/custom/airing_watch_state.json');
  assert.throws(()=>statePath({ANIME_DSH_HOME:'relative'},'linux','/home/a'),/invalid_data_directory/);
});
test('read-only snapshot does not create state, enforces byte cap and supports cancellation', async () => {
  const dir=await mkdtemp(path.join(os.tmpdir(),'anime-ui-')); const file=path.join(dir,'state.json');
  try {
    assert.deepEqual(await readSnapshot({file}),{exists:false,shows:[]});
    await assert.rejects(stat(file),{code:'ENOENT'});
    await writeFile(file,JSON.stringify(sample()));
    const before=await readFile(file); assert.equal((await readSnapshot({file})).shows.length,1);
    assert.deepEqual(await readFile(file),before);
    await assert.rejects(readSnapshot({file,signal:AbortSignal.abort()}),{name:'AbortError'});
    await writeFile(file,'['); await assert.rejects(readSnapshot({file}));
    await writeFile(file,Buffer.alloc(4*1024*1024+1)); await assert.rejects(readSnapshot({file}),/state_too_large/);
  } finally { await rm(dir,{recursive:true,force:true}); }
});
test('host configuration stores qBittorrent preferences without returning the password', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'anime-config-')); const file = path.join(dir, 'state.json');
  try {
    await saveQbittorrent({ file, values: { qbittorrent_exe: 'C:\\Apps\\qbittorrent.exe', download_directory: 'D:\\Anime', web_url: 'http://127.0.0.1:8080', web_username: 'anime', web_password: 'SECRET' } });
    const config = await readConfig({ file });
    assert.equal(config.qbittorrent.configured, true);
    assert.equal(config.qbittorrent.password_configured, true);
    assert.ok(!JSON.stringify(config).includes('SECRET'));
  } finally { await rm(dir, { recursive: true, force: true }); }
});
test('qB connection test authenticates and reads version without adding downloads', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'anime-qb-test-'));
  try {
    const calls = [];
    const request = async (url, options) => {
      calls.push(url);
      assert.equal(options.redirect, 'error');
      if (url.endsWith('/auth/login')) return new Response('Ok.', {headers:{'set-cookie':'SID=fixture; HttpOnly'}});
      assert.equal(options.headers.Cookie, 'SID=fixture');
      return new Response('v5.2.3');
    };
    const file = path.join(dir, 'state.json');
    const result = await testQbittorrent({file, values:{web_url:'http://localhost:8080',web_password:'SECRET'},request});
    assert.deepEqual(result,{status:'connected',version:'v5.2.3'});
    assert.equal(calls.length,2);
    assert.ok(calls.every((url)=>!url.includes('torrents')));
    await assert.rejects(testQbittorrent({file,values:{web_url:'http://user:password@localhost:8080'},request}), /invalid_qb_url/);
    await assert.rejects(testQbittorrent({file,values:{web_url:'http://localhost:8080'},request:async()=>new Response('Fails.')}), /qb_auth_failed/);
  } finally { await rm(dir,{recursive:true,force:true}); }
});
test('RPC is owner-only, accepts no paths and does not leak filesystem errors', async () => {
  let calls=0; const handler=snapshotHandler(async()=>{calls++;throw new Error('C:\\private\\secret');});
  const signal=new AbortController().signal;
  for(const peer of [undefined,{principal:{kind:'guest'}}]) assert.equal((await handler(ENDPOINT,{},signal,peer)).error.code,'forbidden');
  const owner={principal:{kind:'owner'},signal};
  assert.equal((await handler('other',{},signal,owner)).error.code,'not_found');
  for(const payload of [null,[],{file:'secret'},'x']) assert.equal((await handler(ENDPOINT,payload,signal,owner)).error.code,'invalid_request');
  assert.equal(calls,0);
  assert.equal((await handler(ENDPOINT,{},signal,owner)).error.code,'state_read_failed');
  assert.equal((await handler(ENDPOINT,{},signal,{...owner,signal:AbortSignal.abort()})).error.code,'cancelled');
  assert.equal(calls,1);
});
test('requests preserve scope, defaults and explicit download consent', () => {
  const form={title:'Atlas',mode:'episode',quality:'normal',episode:'2',season:'3',requireZh:true,download:false};
  const request=searchRequest(form);
  for(const t of ['第 3 季','第 2 集','普通观看','必须有中文字幕','不提交下载','不推进交付进度']) assert.ok(request.includes(t));
  assert.ok(searchRequest({...form,download:true}).includes('提交 qBittorrent'));
  assert.ok(searchRequest({...form,mode:'movie'}).includes('动画电影'));
  assert.ok(!searchRequest({...form,mode:'movie'}).includes('第 3 季'));
  for(const override of [{title:''},{mode:'invalid'},{mode:'season',season:''},{episode:'1.5'},{quality:'invalid'}]) assert.throws(()=>searchRequest({...form,...override}));
  const track=projectState(sample())[0];
  assert.ok(trackRequest(track).includes('重新读取'));
  assert.ok(trackRequest(track).includes('track-1'));
  assert.ok(!trackRequest(track).includes('第 4 集'));
  assert.ok(trackRequest(track,'schedule').includes('不要重复建任务'));
});
test('native bundle registers DSH slots, shares React and hands off an unsent appended draft', async () => {
  const req=createRequire(import.meta.url); let client; const requested=[];
  const code=await readFile(new URL('../lib/client.js',import.meta.url),'utf8');
  let styles=0; const cleanups=[]; const slots=[]; let draft; const rpcCalls=[];
  vm.runInNewContext(code,{window:{__ModuleLoader__:{load(module){assert.equal(module.id,'dsh-find-nyaa-anime-release');client=module.factory((id)=>{requested.push(id);return req(id);});}}},document:{head:{append(){styles++;}},createElement(){return {dataset:{},remove(){styles--;}};}}});
  const ctx={effect(fn){const d=fn();if(d)cleanups.push(d);},locale:{register(){return ()=>{};},bind(){return ()=> '动漫追番';}},slots:{inject(_name,fn){fn();},register(meta,Component){slots.push({meta,Component});}},connection:{rpc:{async call(...args){rpcCalls.push(args);return {ok:true,value:{shows:[]}};}}},uiWorkspace:{startSession(id,options){draft={id,options};}}};
  client.apply(ctx); assert.equal(styles,1); assert.ok(requested.every(x=>x==='react'));
  assert.equal(slots.length,2); assert.equal(slots[0].meta.key,slots[1].meta.id);
  assert.equal(draft,undefined); assert.equal(rpcCalls.length,0);
  const props=slots[0].meta.inject();const signal=new AbortController().signal;
  await props.loadSnapshot(signal);assert.deepEqual(rpcCalls[0].slice(0,2),['/api',`anime-release/${ENDPOINT}`]);
  props.openDraft('test request');assert.equal(draft.options.prompt,'test request');assert.equal(draft.options.whenDraftExists,'append');
  for(const dispose of cleanups)await dispose(); assert.equal(styles,0);
});
