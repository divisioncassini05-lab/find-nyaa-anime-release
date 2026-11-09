import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createPlanService, plansHandler, validatePlan, planPrompt } from '../host/plans.js';

function scheduler() {
  const tasks = new Map(); let counter = 0;
  return { tasks,
    async create(request) { const task = { ...request, id: `s${++counter}`, kind: request.timing.kind, status: 'active', updatedAt: String(counter), scheduledAt: '2026-12-01T00:00:00Z' }; tasks.set(task.id, task); return { ...task }; },
    async view({ id }) { return tasks.has(id) ? { ...tasks.get(id) } : { code: 'schedule_not_found' }; },
    async catalog() { return [...tasks.values()]; },
    async edit({ id, action, patch, expectedUpdatedAt }) { const task = tasks.get(id); if (!task) return { code: 'schedule_not_found' }; if (expectedUpdatedAt !== task.updatedAt) return { code: 'schedule_conflict' }; if (action === 'delete') { tasks.delete(id); return { id }; } const {active, ...rest} = patch; Object.assign(task, rest, { updatedAt: String(++counter), ...(active === undefined ? {} : {status:active ? 'active' : 'paused'}) }); return { ...task }; },
    async run({ id }) { const task = tasks.get(id); task.executionActive = true; return { ...task }; },
  };
}
const values = { title: 'Atlas Chronicle', season: 'S02', mode: 'next_tracked', tier: 'browse', requireZh: false, enqueue: false, intervalHours: 0 };
test('three scopes use latest or explicit gaps, never next recorded + 1', () => {
  assert.equal(validatePlan(values).mode, 'latest_regular');
  assert.equal(validatePlan({...values,mode:'missing_episodes',intervalHours:24}).mode, 'missing_episodes');
  assert.match(planPrompt({...values,id:'legacy'}), /"intent":"latest_regular"/);
  assert.match(planPrompt({...values,id:'gaps',mode:'missing_episodes'}), /targets --through N/);
  assert.match(planPrompt({...values,id:'gaps',mode:'missing_episodes'}), /specific_episode/);
});
async function fixture(run) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'anime-plans-')); const file = path.join(root, 'state.json');
  const host = scheduler(); const service = createPlanService({ file, scheduler: () => host, evidenceReader: async () => ({}) });
  try { await run(service, host, file); } finally { await rm(root, { recursive: true, force: true }); }
}

test('verified season package completes search without download or cloud write', () => fixture(async (base, host, file) => {
  await base.mutate('save',{...values,mode:'season_batch'});
  const [p] = (await base.list()).plans;
  let cloudCalls=0;let downloads=0;
  const service = createPlanService({file,scheduler:()=>host,collectionWriter:async()=>{cloudCalls++;},
    downloadWriter:async()=>{downloads++;return {status:'download_submitted'};},
    evidenceReader:async()=>({[p.id]:{foundPackage:true,latestPackage:{infoHash:'a'.repeat(40),canDownload:true},completedDownloads:0}})});
  host.tasks.get(p.runId).executionActive=true;
  assert.equal((await service.list()).plans[0].searchComplete,true);
  assert.equal(host.tasks.get(p.runId).status,'active','do not interrupt a current delivery');
  host.tasks.get(p.runId).executionActive=false;
  const [done]=(await service.list()).plans;
  assert.equal(done.searchComplete,true);assert.equal(done.paused,false);
  assert.notEqual(host.tasks.get(p.runId).status,'active');
  assert.equal(cloudCalls,0);assert.equal(downloads,0);
  await service.mutate('download',{id:p.id,revision:p.revision,infoHash:'a'.repeat(40)});
  assert.equal(downloads,1);assert.equal((await service.list()).plans.length,1);
}));

test('missing mode can submit an earlier saved result, not only its latest episode', () => fixture(async(base,host,file)=>{
  await base.mutate('save',{...values,mode:'missing_episodes'});
  const [p]=(await base.list()).plans;
  const selected=[];
  const service=createPlanService({file,scheduler:()=>host,downloadWriter:async(file,id,hash)=>{selected.push(hash);return {status:'download_submitted'};},
    evidenceReader:async()=>({[p.id]:{latestFound:{episode:5,infoHash:'e'.repeat(40),canDownload:true},
      resources:[{episode:2,infoHash:'b'.repeat(40),canDownload:true}]}})});
  await service.mutate('download',{id:p.id,revision:p.revision,infoHash:'b'.repeat(40)});
  assert.deepEqual(selected,['b'.repeat(40)]);
}));
test('reading plans never creates a state file or a schedule', () => fixture(async (service, host, file) => {
  assert.equal((await service.list()).plans.length, 0); assert.equal(host.tasks.size, 0); await assert.rejects(stat(file), { code: 'ENOENT' });
}));

test('plan projection separates running, queued, stopped and unavailable scheduler', () => fixture(async (service, host, file) => {
  await service.mutate('save', values);
  let [plan] = (await service.list()).plans;
  assert.equal(plan.checkStatus, 'idle');
  await service.mutate('check', { id:plan.id, revision:plan.revision });
  [plan] = (await service.list()).plans; assert.equal(plan.checkStatus, 'queued');
  host.tasks.get(plan.runId).executionActive = true;
  [plan] = (await service.list()).plans; assert.equal(plan.checkStatus, 'running');
  const offline = createPlanService({file,evidenceReader:async()=>({})});
  [plan] = (await offline.list()).plans;
  assert.equal(plan.scheduleActive,null); assert.equal(plan.checkStatus,'unknown'); assert.equal(plan.scheduleError,'scheduler_unavailable');
  assert.equal(plan.paused,false);
}));

test('missing recurring job is actionable rather than displayed as a manual plan', () => fixture(async(service,host)=>{
  await service.mutate('save',{...values,intervalHours:4});
  let [plan] = (await service.list()).plans;
  host.tasks.delete(plan.scheduleId);
  [plan] = (await service.list()).plans;
  assert.equal(plan.scheduleError,'schedule_missing'); assert.equal(plan.scheduleActive,null);
}));
test('manual plan stores intent without auto-search or download', () => fixture(async (service, host) => {
  await service.mutate('save', values); const [plan] = (await service.list()).plans;
  assert.equal(host.tasks.size, 0); assert.equal(plan.enqueue, false); assert.ok(plan.trackId);
  await service.mutate('check', { id: plan.id, revision: plan.revision });
  const task = [...host.tasks.values()][0]; assert.equal(task.kind, 'after'); assert.match(task.prompt, /"enqueue_qbittorrent":false/);
}));

test('weekly schedule can be edited and paused without duplicating or executing it', () => fixture(async(service,host)=>{
  const schedule = {kind:'weekly',weekdays:[5,7],time:'22:30',timeZone:'Asia/Shanghai'};
  await service.mutate('save',{...values,schedule});
  let [p] = (await service.list()).plans;
  const id = p.scheduleId;
  assert.deepEqual(host.tasks.get(id).timing,{kind:'weekly',weekly:{time:'22:30:00',time_zone:'Asia/Shanghai',weekdays:[5,7]}});
  assert.equal(p.checkStatus,'idle'); assert.equal(p.runId,undefined);
  await service.mutate('schedulePause',{id:p.id,revision:p.revision,paused:true});
  [p] = (await service.list()).plans;
  await service.mutate('save',{...values,id:p.id,revision:p.revision,schedule:{...schedule,time:'23:00'}});
  [p] = (await service.list()).plans;
  assert.equal(p.scheduleId,id); assert.equal(host.tasks.size,1); assert.equal(p.scheduleActive,false);
  assert.equal(host.tasks.get(id).timing.weekly.time,'23:00:00');
}));

test('catch-up reservation queues only the requested date and never an immediate task', () => fixture(async(service,host)=>{
  await service.mutate('save',{...values,mode:'season_batch',schedule:{kind:'once',date:'2099-12-01',time:'22:00',timeZone:'UTC'}});
  const [p] = (await service.list()).plans;
  assert.equal(host.tasks.size,1); assert.equal(p.runId,undefined);
  assert.equal(host.tasks.get(p.scheduleId).timing.kind,'at'); assert.equal(p.checkStatus,'idle');
  assert.throws(()=>validatePlan({...values,mode:'movie',schedule:{kind:'weekly',weekdays:[1],time:'20:00',timeZone:'UTC'}}));
}));

test('editing conditions cannot rearm an ended reservation; choosing a new date can', () => fixture(async(service,host)=>{
  const schedule = {kind:'once',date:'2099-12-01',time:'22:00',timeZone:'UTC'};
  await service.mutate('save',{...values,schedule});
  let [p] = (await service.list()).plans;
  host.tasks.get(p.scheduleId).status='ended';
  await service.mutate('save',{...values,id:p.id,revision:p.revision,requireZh:true});
  [p] = (await service.list()).plans;
  assert.deepEqual(p.schedule,schedule); assert.equal(p.scheduleStatus,'ended');
  await service.mutate('save',{...values,id:p.id,revision:p.revision,schedule:{...schedule,date:'2099-12-02'}});
  [p] = (await service.list()).plans;
  assert.equal(host.tasks.size,1); assert.equal(p.scheduleStatus,'active');
}));

test('rejected past-date creation leaves no stranded plan or dispatch', () => fixture(async(service,host)=>{
  host.create=async()=>({code:'not_future'});
  await assert.rejects(service.mutate('save',{...values,schedule:{kind:'once',date:'2000-01-01',time:'22:00',timeZone:'UTC'}}),/not_future/);
  assert.equal((await service.list()).plans.length,0); assert.equal(host.tasks.size,0);
}));

test('resuming a plan never reactivates its already executed reservation', () => fixture(async(service,host)=>{
  await service.mutate('save',{...values,schedule:{kind:'once',date:'2099-12-01',time:'22:00',timeZone:'UTC'}});
  let [p] = (await service.list()).plans;
  host.tasks.get(p.scheduleId).status='ended';
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:true});
  [p] = (await service.list()).plans;
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:false});
  [p] = (await service.list()).plans;
  assert.equal(p.paused,false); assert.equal(p.scheduleStatus,'ended');
  await assert.rejects(service.mutate('schedulePause',{id:p.id,revision:p.revision,paused:false}),/not_future/);
  assert.equal(host.tasks.size,1); assert.equal(host.tasks.get(p.scheduleId).status,'ended');
}));
test('schedule create edit pause resume delete operate on the same owned task', () => fixture(async (service, host) => {
  await service.mutate('save', { ...values, intervalHours: 4, requireZh: true });
  let [plan] = (await service.list()).plans; const id = plan.scheduleId;
  assert.equal(plan.scheduleActive, true); assert.equal(host.tasks.get(id).timing.every_seconds, 14400);
  await service.mutate('pause', { id: plan.id, revision: plan.revision, paused: true });
  [plan] = (await service.list()).plans; assert.equal(plan.paused, true); assert.equal(plan.scheduleActive, false);
  await service.mutate('pause', { id: plan.id, revision: plan.revision, paused: false });
  [plan] = (await service.list()).plans; assert.equal(plan.scheduleId, id);
  await service.mutate('delete', { id: plan.id, revision: plan.revision });
  assert.equal((await service.list()).plans.length, 0); assert.equal(host.tasks.size, 0);
}));
test('stale edit and ambiguous duplicate are rejected', () => fixture(async (service) => {
  await service.mutate('save', values); const [plan] = (await service.list()).plans;
  await assert.rejects(service.mutate('save', values), /plan_exists/);
  await assert.rejects(service.mutate('delete', { id: plan.id, revision: plan.revision - 1 }), /plan_conflict/);
}));
test('external task ownership change prevents destructive edits', () => fixture(async (service, host) => {
  await service.mutate('save', { ...values, intervalHours: 4 }); const [plan] = (await service.list()).plans;
  host.tasks.get(plan.scheduleId).prompt = 'unrelated task';
  await assert.rejects(service.mutate('delete', { id: plan.id, revision: plan.revision }), /schedule_ownership_conflict/);
  assert.equal(host.tasks.size, 1);
}));
test('explicit sync uses latest found despite gaps and no download; no agent task is created', () => fixture(async (original, host, file) => {
  await original.mutate('save', { ...values, intervalHours: 4, bangumiSubjectId:123 }); const [plan] = (await original.list()).plans;
  const service = createPlanService({ file, scheduler:()=>host, evidenceReader:async()=>({[plan.id]:{latestFound:{episode:5}}}),
    collectionWriter:async (request)=> { assert.equal(request.throughEpisode,5); assert.equal(request.collectionType,3); return {progress:'synced',collectionType:3}; } });
  const result = await service.mutate('sync', { id: plan.id, revision: plan.revision });
  assert.equal(result.status,'collection_synced'); assert.equal(host.tasks.size,1);
  assert.equal((await service.list()).plans[0].syncedEpisode,5);
}));
test('strict validation and owner-only RPC', async () => {
  assert.throws(() => validatePlan({ ...values, requireZh: 'yes' }), /invalid_request/);
  assert.throws(() => validatePlan({ ...values, intervalHours: -1 }), /invalid_request/);
  assert.equal((await plansHandler()('plans/list', {}, undefined, { principal: { kind: 'guest' } })).error.code, 'forbidden');
});
test('pending one-shot cannot be duplicated and ended tasks are replaced', () => fixture(async (service, host) => {
  await service.mutate('save', values);
  let [plan] = (await service.list()).plans;
  await service.mutate('check', {id:plan.id, revision:plan.revision});
  [plan] = (await service.list()).plans;
  await assert.rejects(service.mutate('check', {id:plan.id, revision:plan.revision}), /schedule_execution_pending/);
  host.tasks.get(plan.runId).status = 'ended';
  await service.mutate('check', {id:plan.id, revision:plan.revision});
  assert.equal(host.tasks.size, 1);
}));
test('schedule resume cannot bypass paused plan', () => fixture(async (service) => {
  await service.mutate('save', {...values, intervalHours:4});
  let [plan] = (await service.list()).plans;
  await service.mutate('pause', {id:plan.id, revision:plan.revision, paused:true});
  [plan] = (await service.list()).plans;
  await assert.rejects(service.mutate('schedulePause', {id:plan.id, revision:plan.revision, paused:false}), /plan_paused/);
}));

test('condition edits never resume a separately paused schedule', () => fixture(async (service, host) => {
  await service.mutate('save', {...values, intervalHours:4});
  let [p] = (await service.list()).plans;
  await service.mutate('schedulePause', {id:p.id, revision:p.revision, paused:true});
  [p] = (await service.list()).plans;
  await service.mutate('save', {...values, intervalHours:12, requireZh:true, id:p.id, revision:p.revision});
  [p] = (await service.list()).plans;
  assert.equal(p.paused,false); assert.equal(p.scheduleActive,false);
  assert.equal(host.tasks.get(p.scheduleId).timing.every_seconds,43200);
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:true});
  [p] = (await service.list()).plans;
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:false});
  [p] = (await service.list()).plans;
  assert.equal(p.scheduleActive,false);
  await service.mutate('schedulePause',{id:p.id,revision:p.revision,paused:false});
  assert.equal((await service.list()).plans[0].scheduleActive,true);
}));

test('pause cancels queued one-shot work and keeps it stopped after resume', () => fixture(async (service, host) => {
  await service.mutate('save', values);
  let [p] = (await service.list()).plans;
  await service.mutate('check',{id:p.id,revision:p.revision});
  [p] = (await service.list()).plans;
  const id = p.runId;
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:true});
  assert.equal(host.tasks.get(id).status,'paused');
  [p] = (await service.list()).plans;
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:false});
  assert.equal(host.tasks.get(id).status,'paused');
}));

test('recurring execution and a queued one-shot cannot trigger duplicate checks', () => fixture(async (service, host) => {
  await service.mutate('save', {...values, intervalHours:4});
  let [p] = (await service.list()).plans;
  await service.mutate('check',{id:p.id,revision:p.revision});
  [p] = (await service.list()).plans;
  await assert.rejects(service.mutate('check',{id:p.id,revision:p.revision}), /schedule_execution_pending/);
  assert.equal(host.tasks.size,2);
  assert.notEqual(p.runId,p.scheduleId);
  assert.equal(host.tasks.get(p.scheduleId).executionActive,undefined);
}));

test('inbox resource requirements and calendar endpoints cannot edit each other', () => fixture(async(service,host)=>{
  const schedule={kind:'weekly',weekdays:[5],time:'22:00',timeZone:'Asia/Shanghai'};
  await service.mutate('save',{...values,schedule});
  let [p]=(await service.list()).plans;
  await assert.rejects(service.mutate('requirements',{id:p.id,revision:p.revision,mode:p.mode,tier:'watch',requireZh:true,enqueue:true,schedule}),/invalid_request/);
  await service.mutate('requirements',{id:p.id,revision:p.revision,mode:p.mode,tier:'watch',requireZh:true,enqueue:true});
  [p]=(await service.list()).plans;
  assert.deepEqual(p.schedule,schedule);assert.equal(p.tier,'watch');assert.equal(p.runId,undefined);
  await assert.rejects(service.mutate('schedule',{id:p.id,revision:p.revision,schedule,tier:'browse'}),/invalid_request/);
  await service.mutate('schedule',{id:p.id,revision:p.revision,schedule:{...schedule,time:'23:30'}});
  [p]=(await service.list()).plans;
  assert.equal(p.tier,'watch');assert.equal(p.requireZh,true);assert.equal(host.tasks.size,1);
}));

test('automatic off still permits a one-shot and leaves the reservation paused', () => fixture(async(service,host)=>{
  await service.mutate('save',{...values,intervalHours:24});
  let [p]=(await service.list()).plans;
  await service.mutate('schedulePause',{id:p.id,revision:p.revision,paused:true});
  [p]=(await service.list()).plans;
  await service.mutate('check',{id:p.id,revision:p.revision});
  [p]=(await service.list()).plans;
  assert.equal(p.paused,false);assert.equal(p.schedulePaused,true);
  assert.equal(host.tasks.get(p.scheduleId).status,'paused');
  assert.equal(host.tasks.get(p.runId).timing.kind,'after');
  assert.match(host.tasks.get(p.scheduleId).prompt,/--scheduled/);
  assert.doesNotMatch(host.tasks.get(p.runId).prompt,/--scheduled/);
}));

test('inbox download is exact-hash native retry, never a new agent search', () => fixture(async(original,host,file)=>{
  await original.mutate('save',values);
  let [p]=(await original.list()).plans;const hash='a'.repeat(40);let calls=0;
  const service=createPlanService({file,scheduler:()=>host,
    evidenceReader:async()=>({[p.id]:{latestFound:{episode:5,infoHash:hash,canDownload:true}}}),
    downloadWriter:async(f,id,h)=>{assert.equal(f,file);assert.equal(id,p.id);assert.equal(h,hash);calls++;return {status:calls===1?'download_pending':'download_submitted'};},
    collectionWriter:async()=>assert.fail('download action cannot write watched')});
  await assert.rejects(service.mutate('download',{id:p.id,revision:p.revision,infoHash:'b'.repeat(40)}),/resource_review_required/);
  assert.equal((await service.mutate('download',{id:p.id,revision:p.revision,infoHash:hash})).status,'download_pending');
  [p]=(await service.list()).plans;
  assert.equal((await service.mutate('download',{id:p.id,revision:p.revision,infoHash:hash})).status,'download_submitted');
  assert.equal(calls,2);assert.equal(host.tasks.size,0);
}));

test('queued check prevents adding a second recurring task', () => fixture(async (service, host) => {
  await service.mutate('save', values);
  let [p] = (await service.list()).plans;
  await service.mutate('check',{id:p.id,revision:p.revision});
  [p] = (await service.list()).plans;
  await assert.rejects(service.mutate('save',{...values,id:p.id,revision:p.revision,intervalHours:4}), /schedule_execution_pending/);
  assert.equal(host.tasks.size,1);
}));

for (const failure of ['missing', 'view', 'edit']) {
test(`scheduler ${failure} outage retains stop and pending status without cloud writes`, () => fixture(async (original, host, file) => {
  await original.mutate('save', {...values, intervalHours:4, bangumiSubjectId:123});
  let [p] = (await original.list()).plans;
  const broken = failure === 'missing' ? null : {...host, [failure]:async()=>{throw Object.assign(new Error('scheduler_unavailable'),{code:'scheduler_unavailable'});}};
  const service = createPlanService({file,scheduler:()=>broken,evidenceReader:async()=>({}),
    collectionWriter:async()=>assert.fail('no cloud write until schedule stopped')});
  await assert.rejects(service.mutate('pause',{id:p.id,revision:p.revision,paused:true}), /scheduler_unavailable/);
  [p] = (await service.list()).plans;
  assert.equal(p.paused,true);
  await assert.rejects(service.mutate('collection',{id:p.id,revision:p.revision,collectionType:5}), /scheduler_unavailable/);
  [p] = (await service.list()).plans;
  assert.equal(p.paused,true);
  assert.equal(p.collectionType,5);
  assert.equal(p.collectionSync,'pending');
}));
}

test('host schedule pause survives plan pause and resume without a condition edit', () => fixture(async (service, host) => {
  await service.mutate('save', {...values, intervalHours:4});
  let [p] = (await service.list()).plans;
  host.tasks.get(p.scheduleId).status = 'paused';
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:true});
  [p] = (await service.list()).plans;
  assert.equal(p.schedulePaused,true);
  await service.mutate('pause',{id:p.id,revision:p.revision,paused:false});
  [p] = (await service.list()).plans;
  assert.equal(p.paused,false);
  assert.equal(host.tasks.get(p.scheduleId).status,'paused');
}));

test('regular and catch-up histories cannot be repurposed by editing mode', () => fixture(async (service) => {
  await service.mutate('save', values);
  const [p] = (await service.list()).plans;
  await assert.rejects(service.mutate('save',{...values,id:p.id,revision:p.revision,mode:'season_batch'}), /plan_identity_change/);
  await service.mutate('save',{...values,id:p.id,revision:p.revision,mode:'latest_regular'});
  assert.equal((await service.list()).plans[0].mode,'latest_regular');
}));

test('catch-up submission queues one complete-package check, never a recurring job', () => fixture(async (service, host) => {
  const saved = await service.mutate('save', { ...values, mode: 'season_batch' });
  assert.equal(saved.status, 'queued'); assert.equal(host.tasks.size, 1);
  const task = [...host.tasks.values()][0]; assert.equal(task.kind, 'after');
  assert.match(task.prompt, /"intent":"season_batch"/); assert.match(task.prompt, /禁止拿任意单集/);
  assert.match(task.prompt, /"bangumi_sync":"start_watching_only"/);
  assert.match(task.prompt, /dsh_panel_run.py/);
  assert.throws(() => validatePlan({ ...values, mode: 'season_batch', intervalHours: 4 }), /invalid_request/);
  assert.match(planPrompt({ ...values, mode: 'movie' }), /整部剧场版/);
}));

test('on-hold stops both recurring and queued checks before write, retaining plan on failure', () => fixture(async (original, host, file) => {
  const service = createPlanService({ file, scheduler: () => host, collectionWriter: async () => { assert.ok([...host.tasks.values()].every((t) => t.status === 'paused')); throw new Error('offline'); } });
  await original.mutate('save', { ...values, bangumiSubjectId: 123, intervalHours: 4 });
  const [plan] = (await original.list()).plans;
  const result = await service.mutate('collection', { id: plan.id, revision: plan.revision, collectionType: 4 });
  assert.equal(result.status, 'collection_sync_pending');
  const [held] = (await service.list()).plans; assert.equal(held.paused, true); assert.equal(held.collectionType, 4); assert.equal(held.collectionSync, 'pending');
  const retry = createPlanService({ file, scheduler: () => host, collectionWriter: async () => ({ status: 'ok' }) });
  assert.equal((await retry.mutate('collection', { id: held.id, revision: held.revision, collectionType: 5 })).status, 'collection_synced');
  assert.equal((await retry.list()).plans.length, 1); assert.equal((await retry.list()).plans[0].paused, true);
}));

test('complete choice pauses a one-shot without deleting its plan', () => fixture(async (original, host, file) => {
  const service = createPlanService({ file, scheduler: () => host, collectionWriter: async () => ({}) });
  await service.mutate('save', { ...values, mode: 'movie', bangumiSubjectId: 123 });
  const [plan] = (await service.list()).plans;
  await service.mutate('collection', { id: plan.id, revision: plan.revision, collectionType: 2 });
  assert.equal(host.tasks.get(plan.runId).status, 'paused');
  const [kept] = (await service.list()).plans; assert.equal(kept.collectionType, 2); assert.equal(kept.collectionSync, 'synced');
  await assert.rejects(service.mutate('collection', { id: kept.id, revision: kept.revision, collectionType: 0 }), /invalid_request/);
}));

test('partial progress remains retryable; hidden collection choices are rejected', () => fixture(async (original, host, file) => {
  const service = createPlanService({file,scheduler:()=>host,collectionWriter:async ({collectionType})=>({progress:collectionType === 2 ? 'pending' : 'not_requested'})});
  await service.mutate('save',{...values,intervalHours:4,bangumiSubjectId:123});
  let [p] = (await service.list()).plans;
  const result = await service.mutate('collection',{id:p.id,revision:p.revision,collectionType:2});
  assert.equal(result.status,'collection_partial');
  [p] = (await service.list()).plans;
  assert.equal(p.collectionSync,'partial'); assert.equal(p.scheduleActive,false);
  await assert.rejects(service.mutate('collection',{id:p.id,revision:p.revision,collectionType:3}), /invalid_request/);
  await assert.rejects(service.mutate('collection',{id:p.id,revision:p.revision,collectionType:1}), /invalid_request/);
  [p] = (await service.list()).plans;
  assert.equal(p.paused,true); assert.equal(p.scheduleActive,false); assert.equal(host.tasks.size,1);
}));

test('finale sync marks watched before downloads finish and pauses first', () => fixture(async (original, host, file) => {
  await original.mutate('save',{...values,intervalHours:4,bangumiSubjectId:123});
  const [p] = (await original.list()).plans;
  const service = createPlanService({file,scheduler:()=>host,evidenceReader:async()=>({[p.id]:{latestFound:{episode:12,finalEpisode:12},completedDownloads:0}}),
    collectionWriter:async (r)=>{assert.equal(r.collectionType,2);assert.equal(r.throughEpisode,12);assert.equal(host.tasks.get(p.scheduleId).status,'paused');return {collectionType:2,progress:'synced'};}});
  await service.mutate('sync',{id:p.id,revision:p.revision});
  const [kept] = (await service.list()).plans;
  assert.equal(kept.paused,true);assert.equal(kept.syncedEpisode,12);assert.equal(kept.evidence.completedDownloads,0);
}));

test('unknown found evidence does not synchronize broadcast latest or next target', () => fixture(async (service) => {
  await service.mutate('save',values);const [p] = (await service.list()).plans;
  await assert.rejects(service.mutate('sync',{id:p.id,revision:p.revision}),/no_found_episode/);
}));

test('old panel prompt upgrades without resuming a paused schedule', () => fixture(async (service, host) => {
  await service.mutate('save', {...values, intervalHours:4});
  let [p] = (await service.list()).plans;
  await service.mutate('pause', {id:p.id, revision:p.revision, paused:true});
  const task = host.tasks.get(p.scheduleId);
  task.prompt = `[anime-plan:${p.id}]\nold automatic progress workflow`;
  [p] = (await service.list()).plans;
  assert.equal(host.tasks.size, 1);
  assert.equal(task.status, 'paused');
  assert.equal(p.paused, true);
  assert.match(task.prompt, /dsh_panel_run.py/);
}));

test('identity edits cannot reuse found progress or alter schedules; condition edits preserve history', () => fixture(async (original, host, file) => {
  await original.mutate('save', {...values, intervalHours:4, bangumiSubjectId:123});
  const [p] = (await original.list()).plans;
  const evidence = {[p.id]: {latestFound:{episode:5}, completedDownloads:2, completedEpisodes:[1,5]}};
  const service = createPlanService({file, scheduler:()=>host, evidenceReader:async()=>evidence,
    collectionWriter:async()=>({progress:'synced',collectionType:3})});
  await service.mutate('sync', {id:p.id, revision:p.revision});
  let [plan] = (await service.list()).plans;
  const before = await readFile(file.replace(/\.json$/u,'.plans.json'),'utf8');
  const tasks = structuredClone([...host.tasks]);
  for(const change of [{title:'Different Work'}, {season:'S03'}, {trackId:'another-track'}, {bangumiSubjectId:456}]) {
    await assert.rejects(service.mutate('save', {...values, intervalHours:4, bangumiSubjectId:123, id:plan.id, revision:plan.revision, ...change}), /plan_identity_change/);
    assert.equal(await readFile(file.replace(/\.json$/u,'.plans.json'),'utf8'), before);
    assert.deepEqual([...host.tasks], tasks);
  }
  await service.mutate('save', {...values, intervalHours:12, tier:'watch', requireZh:true, id:plan.id, revision:plan.revision});
  [plan] = (await service.list()).plans;
  assert.equal(plan.bangumiSubjectId,123);
  assert.equal(plan.trackId,p.trackId);
  assert.equal(plan.syncedEpisode,5);
  assert.deepEqual(plan.evidence,evidence[p.id]);
  assert.equal(plan.intervalHours,12);
  assert.equal(plan.requireZh,true);
}));

test('missing Bangumi binding can only be filled from the same plan evidence', () => fixture(async (original, host, file) => {
  await original.mutate('save',values);
  const [p] = (await original.list()).plans;
  const service = createPlanService({file,scheduler:()=>host,evidenceReader:async()=>({[p.id]:{bangumiSubjectId:123}})});
  await assert.rejects(service.mutate('save',{...values,id:p.id,revision:p.revision,bangumiSubjectId:456}),/plan_identity_change/);
  await service.mutate('save',{...values,id:p.id,revision:p.revision,bangumiSubjectId:123,tier:'watch'});
  assert.equal((await service.list()).plans[0].bangumiSubjectId,123);
}));

for (const [collectionSync, syncedAt, startedAt, expected] of [
  ['synced','2026-11-08T01:02:00Z','2026-11-08T01:00:00Z','synced'],
  ['partial','2026-11-08T01:02:00Z','2026-11-08T01:00:00Z','synced'],
  ['synced','2026-11-08T01:02:00Z','2026-11-08T01:03:00Z','pending'],
  ['pending','2026-11-08T01:02:00Z','2026-11-08T01:00:00Z','pending'],
  ['synced',null,'2026-11-08T01:00:00Z','pending'],
  ['synced','2026-11-08T01:02:00Z',null,'pending'],
]) {
  test(`only a confirmed later button write clears stale start failure: ${collectionSync}/${syncedAt}/${startedAt}`, () => fixture(async (original, host, file) => {
    await original.mutate('save',{...values,bangumiSubjectId:123});
    const [p] = (await original.list()).plans;
    const store = file.replace(/\.json$/u,'.plans.json');
    const data = JSON.parse(await readFile(store,'utf8'));
    Object.assign(data.plans[0],{collectionSync,collectionSyncedAt:syncedAt,collectionType:3});
    await writeFile(store,JSON.stringify(data));
    const evidence = {[p.id]:{startSync:'pending',startedAt,latestFound:{episode:1}}};
    const service = createPlanService({file,scheduler:()=>host,evidenceReader:async()=>evidence});
    const before = await readFile(store,'utf8');
    const [plan] = (await service.list()).plans;
    assert.equal(plan.evidence.startSync,expected);
    assert.equal(plan.collectionSync,collectionSync);
    assert.equal(evidence[p.id].startSync,'pending', 'projection never rewrites the failed-attempt evidence');
    assert.equal(await readFile(store,'utf8'), before, 'readback never rewrites plan progress');
  }));
}
