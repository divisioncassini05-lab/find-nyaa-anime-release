import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { coverUrl, libraryItem, readBangumiLibrary, readBangumiMetadata, updateBangumiCollection, bangumiHandler } from '../host/bangumi.js';
import { connectBangumi, disconnectBangumi, readConfig } from '../host/config.js';

const image = 'https://lain.bgm.tv/pic/cover/c/aa/bb/123.jpg';
const row = { subject_id: 123, type: 3, ep_status: 2, rate: 8, subject: { id: 123, type: 2, name: 'Atlas', eps: 12, date: '2026-07-03', images: { common: image } } };
test('offline refresh preserves same-account cache without claiming freshness', () => fixture(async (file, root) => {
  const first = await readBangumiLibrary({ file, request: async () => Response.json({ data: [row], total: 1 }) });
  const bytes = await readFile(path.join(root, 'state.bangumi-library.json'), 'utf8');
  const stale = await readBangumiLibrary({ file, refresh: true, request: async () => { throw new Error('offline'); } });
  assert.equal(stale.status, 'stale'); assert.equal(stale.warning, 'bangumi_network_unavailable');
  assert.equal(stale.checked_at, first.checked_at); assert.equal(stale.items.length, 1);
  assert.equal(await readFile(path.join(root, 'state.bangumi-library.json'), 'utf8'), bytes);
  await assert.rejects(readBangumiLibrary({ file, refresh: true, request: async () => new Response(null, { status: 401 }) }), /bangumi_http_401/);
}));

test('broken optional caches rebuild; incomplete pages never replace the complete list', () => fixture(async (file, root) => {
  await writeFile(path.join(root, 'state.bangumi-library.json'), '{');
  await writeFile(path.join(root, 'state.bangumi-subjects.json'), '{');
  const first = await readBangumiLibrary({ file, request: async () => Response.json({ data: [row], total: 1 }) });
  assert.equal(first.status, 'ready'); assert.equal(first.items.length, 1);
  const stale = await readBangumiLibrary({ file, refresh: true, request: async () => Response.json({ data: [], total: 2 }) });
  assert.equal(stale.status, 'stale'); assert.equal(stale.warning, 'bangumi_library_incomplete'); assert.equal(stale.items.length, 1);
}));

test('disconnect during refresh cannot resurrect library or personal metadata', () => fixture(async (file, root) => {
  let release; let entered;
  const started = new Promise((resolve) => { entered = resolve; });
  const fetching = readBangumiLibrary({ file, request: async () => { entered(); return new Promise((resolve) => { release = resolve; }); } });
  await started; await disconnectBangumi({ file }); release(Response.json({ data: [row], total: 1 }));
  await assert.rejects(fetching, /bangumi_connection_changed/);
  await assert.rejects(readFile(path.join(root, 'state.bangumi-library.json')), { code: 'ENOENT' });
  assert.equal((await readBangumiLibrary({ file })).status, 'not_configured');
}));

test('token replacement is verified before commit and disconnect preserves plans', () => fixture(async (file, root) => {
  const plan = path.join(root, 'state.plans.json'); await writeFile(plan, '{"keep":true}');
  const request = async () => Response.json({ id: 7, username: 'fixture' });
  await connectBangumi({ file, token: 'FAKE-NEW', request });
  const saved = JSON.parse(await readFile(path.join(root, 'state.bangumi.json'), 'utf8'));
  assert.equal(await readFile(saved.token_file, 'utf8'), 'FAKE-NEW');
  await assert.rejects(connectBangumi({ file, token: 'FAKE-BAD', request: async () => new Response(null, { status: 401 }) }), /bangumi_http_401/);
  assert.equal(JSON.parse(await readFile(path.join(root, 'state.bangumi.json'), 'utf8')).token_file, saved.token_file);
  assert.ok(!JSON.stringify(await readConfig({ file })).includes('FAKE'));
  await disconnectBangumi({ file }); await assert.rejects(readFile(saved.token_file), { code: 'ENOENT' });
  assert.equal(await readFile(plan, 'utf8'), '{"keep":true}');
}));

test('owner RPC supports absent optional cancellation signal', async () => {
  const handler = bangumiHandler(async () => ({ status: 'not_configured', items: [] }));
  assert.equal((await handler('bangumi/library', {}, undefined, { principal: { kind: 'owner' } })).ok, true);
});
async function fixture(run) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'anime-library-')); const file = path.join(root, 'state.json');
  await writeFile(path.join(root, 'token'), 'FAKE');
  await writeFile(path.join(root, 'state.bangumi.json'), JSON.stringify({ version: 1, account_id: 7, username: 'fixture', token_file: path.join(root, 'token') }));
  try { await run(file, root); } finally { await rm(root, { recursive: true, force: true }); }
}
test('SlimSubject cover survives projection; missing platform is unknown, not a guessed TV', () => {
  const item = libraryItem(row); assert.equal(item.cover_url, image); assert.equal(item.type, null); assert.equal(item.date, '2026-07-03');
  for (const url of ['file:///private', 'https://evil.test/a', 'https://user:pass@lain.bgm.tv/pic/cover/a', 'https://lain.bgm.tv.evil.test/pic/cover/a']) assert.equal(coverUrl({ common: url }), null);
  assert.equal(coverUrl({ common: image.replace('https:', 'http:') }), image);
});
test('old library cache refreshes once; details supplement platform and reuse cache without network', () => fixture(async (file, root) => {
  await writeFile(path.join(root, 'state.bangumi-library.json'), JSON.stringify({ version: 1, account_id: 7, checked_at: new Date().toISOString(), items: [] }));
  let calls = 0;
  const request = async (url) => { calls++; return Response.json(url.includes('/collections?') ? { data: [row], total: 1 } : { id: 123, type: 2, platform: 'Web', date: '2026-07-03', images: { common: image } }); };
  const first = await readBangumiLibrary({ file, request }); assert.equal(first.items[0].cover_url, image); assert.equal(calls, 1);
  const meta = await readBangumiMetadata({ file, ids: [123], request }); assert.equal(meta.items[0].type, 'Web');
  await readBangumiMetadata({ file, ids: [123], request });
  const cached = await readBangumiLibrary({ file, request }); assert.equal(calls, 2); assert.equal(cached.items[0].type, 'Web');
  assert.equal(cached.items[0].watched_count, 2); assert.equal(cached.items[0].metadata_checked, true);
  await assert.rejects(readBangumiMetadata({ file, ids: [999], request }), /invalid_request/);
}));
test('detail failure preserves collections and returns unresolved metadata', () => fixture(async (file) => {
  await readBangumiLibrary({ file, request: async () => Response.json({ data: [row] }) });
  const result = await readBangumiMetadata({ file, ids: [123], request: async () => { throw new Error('offline'); } });
  assert.deepEqual(result, { items: [], unresolved: [123] });
  assert.equal((await readBangumiLibrary({ file })).items.length, 1);
}));
test('collection writes touch only status and verify identity, account and readback', () => fixture(async (file) => {
  const writes = [];
  const request = async (url, init) => {
    if (url.endsWith('/me')) return Response.json({ id: 7 });
    if (url.includes('/subjects/')) return Response.json({ id: 123, type: 2 });
    if (init.method === 'POST') { writes.push(JSON.parse(init.body)); return new Response(null, { status: 204 }); }
    return Response.json({ type: 4, rate: 8, comment: 'preserved' });
  };
  assert.equal((await updateBangumiCollection({ file, subjectId: 123, collectionType: 4, request })).status, 'bangumi_collection_updated');
  assert.deepEqual(writes, [{ type: 4 }]);
  await assert.rejects(updateBangumiCollection({ file, subjectId: 123, collectionType: 5, request }), /bangumi_write_not_confirmed/);
  await assert.rejects(updateBangumiCollection({ file, subjectId: 123, collectionType: 4, request: async () => Response.json({ id: 8 }) }), /bangumi_account_conflict/);
}));
test('metadata RPC rejects guest, oversized batches and arbitrary paths', async () => {
  const signal = new AbortController().signal; const handler = bangumiHandler();
  assert.equal((await handler('bangumi/metadata', { ids: [1] }, signal, { principal: { kind: 'guest' } })).error.code, 'forbidden');
  for (const payload of [{ ids: Array(25).fill(1) }, { ids: ['1'] }, { ids: [] }, { ids: [1], url: 'x' }]) {
    assert.equal((await handler('bangumi/metadata', payload, signal, { principal: { kind: 'owner' } })).error.code, 'invalid_request');
  }
});

for (const scenario of ['success', 'unknown', 'missing', 'failure', 'wrong_readback', 'wrong_subject']) {
  test(`mark watched fills only verified regular episodes: ${scenario}`, () => fixture(async (file) => {
    const writes = []; let patched = false;
    const request = async (url, init) => {
      if (url.endsWith('/me')) return Response.json({ id: 7 });
      if (url.includes('/subjects/')) return Response.json({ id:123, type:2, eps:scenario === 'unknown' ? 0 : 2 });
      if (init.method === 'POST') { writes.push(JSON.parse(init.body)); return new Response(null, {status:204}); }
      if (init.method === 'PATCH') {
        writes.push(JSON.parse(init.body));
        if (scenario === 'failure') throw new Error('offline');
        patched = true; return new Response(null, {status:204});
      }
      if (url.includes('/episodes?')) return Response.json({total:2, data:(scenario === 'missing' ? [1] : [1,2]).map((id) => ({episode:{id, subject_id:scenario === 'wrong_subject' ? 999 : 123, type:0}, type:id === 1 || (patched && scenario !== 'wrong_readback') ? 2 : 0}))});
      return Response.json({type:2, rate:8, comment:'preserved'});
    };
    const result = await updateBangumiCollection({file, subjectId:123, collectionType:2, request});
    const expected = {success:'synced',unknown:'unknown_total',missing:'coverage_unconfirmed',failure:'pending',wrong_readback:'pending',wrong_subject:'coverage_unconfirmed'};
    assert.equal(result.progress, expected[scenario]);
    assert.deepEqual(writes[0], {type:2});
    if (['success','failure','wrong_readback'].includes(scenario)) assert.deepEqual(writes[1], {episode_id:[2], type:2});
    else assert.equal(writes.length, 1);
    if (scenario === 'success') {
      writes.length = 0;
      assert.equal((await updateBangumiCollection({file,subjectId:123,collectionType:2,request})).progress,'synced');
      assert.deepEqual(writes,[{type:2}], 'retry must not rewrite already-watched episodes');
    }
  }));
}

for (const scenario of ['success', 'missing_number', 'duplicate_number', 'wrong_readback', 'already_watched', 'finale_retry']) {
  test(`sync latest found fills gaps without touching specials: ${scenario}`,()=>fixture(async(file)=>{
    const writes=[];let patched=false;let collectionType=['already_watched','finale_retry'].includes(scenario)?2:3;
    const request=async(url,init)=>{
      if(url.endsWith('/me')) return Response.json({id:7});
      if(url.includes('/subjects/')) return Response.json({id:123,type:2,eps:12});
      if(init.method==='POST'){writes.push(JSON.parse(init.body));collectionType=JSON.parse(init.body).type;return new Response(null,{status:204});}
      if(init.method==='PATCH'){writes.push(JSON.parse(init.body));patched=true;return new Response(null,{status:204});}
      if(url.includes('/episodes?')) {
        const data=[1,2,3,4,5,6].filter(n=>scenario!=='missing_number'||n!==3).map(n=>({episode:{id:100+n,subject_id:123,type:0,sort:n},type:(n===1||patched&&scenario!=='wrong_readback'&&n<=5)?2:0}));
        data.push({episode:{id:999,subject_id:123,type:1,sort:1},type:0});
        if(scenario==='duplicate_number') data.push({episode:{id:888,subject_id:123,type:0,sort:3},type:0});
        return Response.json({total:data.length,data});
      }
      return Response.json({type:collectionType});
    };
    const r=await updateBangumiCollection({file,subjectId:123,collectionType:scenario==='finale_retry'?2:3,throughEpisode:5,preserveWatched:true,request});
    if(['already_watched','finale_retry'].includes(scenario)){
      assert.equal(r.collectionType,2);assert.equal(r.progress,'synced');assert.equal(r.syncedEpisode,5);
      assert.deepEqual(writes,[{episode_id:[102,103,104,105],type:2}]);
      writes.length=0;
      assert.equal((await updateBangumiCollection({file,subjectId:123,collectionType:3,throughEpisode:5,preserveWatched:true,request})).progress,'synced');
      assert.deepEqual(writes,[]);return;
    }
    assert.equal(r.progress,['success','finale_retry'].includes(scenario)?'synced':scenario==='wrong_readback'?'pending':'coverage_unconfirmed');
    if(['success','wrong_readback','finale_retry'].includes(scenario)) assert.deepEqual(writes[1],{episode_id:[102,103,104,105],type:2});
    else assert.equal(writes.length,1);
  }));
}

test('startup preserves watched without silently filling episode progress',()=>fixture(async(file)=>{
  const routes=[];
  const request=async(url,init)=>{
    assert.equal(init.method,undefined);routes.push(url);
    if(url.endsWith('/me'))return Response.json({id:7});
    if(url.includes('/subjects/'))return Response.json({id:123,type:2,eps:12});
    return Response.json({type:2});
  };
  const result=await updateBangumiCollection({file,subjectId:123,collectionType:3,preserveWatched:true,request});
  assert.equal(result.progress,'not_requested');assert.equal(result.collectionType,2);
  assert.equal(routes.some(url=>url.includes('/episodes')),false);
}));

test('watched collection cannot turn failed episode readback into success',()=>fixture(async(file)=>{
  const request=async(url,init)=>{
    assert.notEqual(init.method,'POST','never downgrade or rewrite watched');
    if(url.endsWith('/me'))return Response.json({id:7});
    if(url.includes('/subjects/'))return Response.json({id:123,type:2,eps:12});
    if(init.method==='PATCH')return new Response(null,{status:204});
    if(url.includes('/episodes?'))return Response.json({total:2,data:[1,2].map(n=>({episode:{id:100+n,subject_id:123,type:0,sort:n},type:0}))});
    return Response.json({type:2});
  };
  const result=await updateBangumiCollection({file,subjectId:123,collectionType:3,throughEpisode:2,preserveWatched:true,request});
  assert.equal(result.collectionType,2);assert.equal(result.progress,'pending');assert.equal(result.syncedEpisode,undefined);
}));
