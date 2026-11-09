// Offline cross-language lifecycle audit. Never uses the user's profile or credentials.
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createPlanService } from '../host/plans.js';
import { updateBangumiCollection } from '../host/bangumi.js';
import { primaryAction, hasCompletedTask, needsAttention } from '../client/library.mjs';
import { syncLabel } from '../client/presentation.mjs';
import { inboxResult } from '../client/inbox.mjs';

globalThis.fetch = () => { throw new Error('Real network forbidden in audit'); };
const root = fileURLToPath(new URL('../.preview/', import.meta.url));
await mkdir(root, { recursive: true });
const workspace = await mkdtemp(path.join(root, 'lifecycle-audit-'));
const run = promisify(execFile);
const helper = fileURLToPath(new URL('./panel_lifecycle_fixture.py', import.meta.url));
const reports = [];
const read = async (file) => JSON.parse(await readFile(file, 'utf8'));
const write = (file, value) => writeFile(file, JSON.stringify(value));
const check = (scenario, stage, condition, observed) => reports.push({scenario, stage, passed:Boolean(condition), observed});

async function fixture(name, extra = {}) {
  const dir = path.join(workspace, name); await mkdir(dir);
  const file = path.join(dir, 'state.json');
  const cloudFile = path.join(dir, 'fake-cloud.json');
  await writeFile(path.join(dir, 'SYNTHETIC-AUDIT'), 'No real account');
  await writeFile(path.join(dir, 'token'), 'FAKE-TEST-ONLY');
  await write(path.join(dir, 'state.bangumi.json'), {version:1, account_id:7, username:'fake', token_file:path.join(dir,'token')});
  await write(path.join(dir, 'state.setup.json'), {download_directory:path.join(dir,'downloads')});
  await write(cloudFile, {type:1, watched:[], writes:[], rate:8, comment:'Preserve me', tags:['fixture'], offline:false});
  let id; let counter = 0; const tasks = new Map();
  const scheduler = {
    async create(r) {const t={...r,id:`s${++counter}`,kind:r.timing.kind,status:'active',updatedAt:String(counter)};tasks.set(t.id,t);return {...t};},
    async view({id}) {return tasks.has(id)?{...tasks.get(id)}:{code:'schedule_not_found'};},
    async catalog() {return [...tasks.values()];},
    async edit({id,action,patch,expectedUpdatedAt}) {const t=tasks.get(id);if(t.updatedAt!==expectedUpdatedAt)throw Error('conflict');if(action==='delete'){tasks.delete(id);return {id};}const {active,...rest}=patch;Object.assign(t,rest,{updatedAt:String(++counter),...(active===undefined?{}:{status:active?'active':'paused'})});return {...t};},
    async run({id}) {return {...tasks.get(id),executionActive:true};},
  };
  const python = async (action, episode = 0) => {
    const {stdout} = await run('python', ['-X','utf8',helper,dir,action,id,String(episode)], {windowsHide:true,timeout:15000,
      env:{...process.env,ANIME_DSH_HOME:dir,ANIME_DSH_QB_BACKUP_DIR:path.join(dir,'qb-backup'),ANIME_DSH_DOWNLOAD_DIR:path.join(dir,'downloads'),BANGUMI_ACCESS_TOKEN:''}});
    return JSON.parse(stdout);
  };
  const request = async (url, init={}) => {
    const cloud = await read(cloudFile);
    if(cloud.offline)throw Error('fake offline');
    const u=new URL(url);
    if(u.pathname==='/v0/me')return Response.json({id:7});
    if(u.pathname==='/v0/subjects/123')return Response.json({id:123,type:2,eps:3});
    if(init.method==='POST') {const body=JSON.parse(init.body);cloud.type=body.type;cloud.writes.push({source:'button',...body});await write(cloudFile,cloud);return new Response(null,{status:204});}
    if(init.method==='PATCH') {const body=JSON.parse(init.body);cloud.watched=[...new Set([...cloud.watched,...body.episode_id])];cloud.writes.push({source:'button',...body});await write(cloudFile,cloud);return new Response(null,{status:204});}
    if(u.pathname.endsWith('/episodes'))return Response.json({total:3,data:[1,2,3].map(n=>({episode:{id:n,subject_id:123,type:0,sort:n},type:cloud.watched.includes(n)?2:0}))});
    if(u.pathname.endsWith('/collections/123'))return Response.json({...cloud});
    throw Error('Unexpected fake route '+u.pathname);
  };
  const service=createPlanService({file,scheduler:()=>scheduler,evidenceReader:()=>python('snapshot'),
    collectionWriter:(args)=>updateBangumiCollection({...args,request})});
  const saved=await service.mutate('save',{title:'Atlas Chronicle',season:'S01',bangumiSubjectId:123,mode:'next_tracked',tier:'browse',requireZh:false,enqueue:true,intervalHours:4,...extra});
  id=saved.id;
  const get=async()=> {
    const plan=(await service.list()).plans[0]; const cloud=await read(cloudFile);
    const record={title:plan.title,plan,managed:true,phase:'airing',bangumiSubjectId:123,bangumiStatus:cloud.type,watchedCount:cloud.watched.length};
    return {plan,cloud,record,button:primaryAction(record),label:syncLabel(record),completed:hasCompletedTask(record)};
  };
  const action=async(kind,extra={})=>{const {plan}=await get();return service.mutate(kind,{id,revision:plan.revision,...extra});};
  const cloudChange=async(patch)=>write(cloudFile,{...await read(cloudFile),...patch});
  return {name,dir,file,id,tasks,get,action,python,cloudChange,service};
}

{
  const f=await fixture('airing',{schedule:{kind:'weekly',weekdays:[5],time:'22:30',timeZone:'Asia/Shanghai'}});let s=await f.get();
  check(f.name,'add: no cloud writes; sync disabled',s.cloud.writes.length===0&&s.button.disabled,{writes:s.cloud.writes,button:s.button});
  check(f.name,'weekly reservation: one owned task, no early search',f.tasks.size===1&&f.tasks.get(s.plan.scheduleId).timing.weekly.time==='22:30:00'&&s.plan.checkStatus==='idle'&&!s.plan.evidence.latestFound,{timing:f.tasks.get(s.plan.scheduleId).timing,status:s.plan.checkStatus});
  await f.action('check');await f.python('execute');s=await f.get();
  check(f.name,'execution: watching, no watched progress',s.cloud.type===3&&s.cloud.watched.length===0,{type:s.cloud.type,watched:s.cloud.watched});
  check(f.name,'no result: no found progress or completion',!s.plan.evidence.latestFound&&s.button.disabled&&!s.completed,{evidence:s.plan.evidence,button:s.button});
  await f.python('find',1);s=await f.get();
  check(f.name,'found: sync enabled before download, no auto progress',!s.button.disabled&&!s.completed&&s.cloud.watched.length===0,{button:s.button,completed:s.completed,watched:s.cloud.watched});
  await f.python('partial',1);s=await f.get();
  check(f.name,'preallocation: not completed',!s.completed,s.plan.evidence);
  await f.python('download',1);s=await f.get();
  check(f.name,'download: retained history, still no auto sync',s.completed&&s.cloud.watched.length===0,{evidence:s.plan.evidence,watched:s.cloud.watched});
  await f.action('sync');s=await f.get();
  check(f.name,'sync: episode 1, disabled primary, schedule active',s.cloud.watched.join()==='1'&&s.button.disabled&&s.plan.scheduleActive&&s.completed,{watched:s.cloud.watched,button:s.button,schedule:s.plan.scheduleActive});
  await f.python('find',2);await f.python('download',2);s=await f.get();
  check(f.name,'next find: one grouped history, sync enabled',!s.button.disabled&&s.plan.evidence.completedEpisodes.join()==='1,2'&&(await f.service.list()).plans.length===1,s.plan.evidence);
  await f.python('finale',3);await f.action('sync');s=await f.get();
  check(f.name,'finale sync before download: watched, paused, history retained',s.cloud.type===2&&s.cloud.watched.join()==='1,2,3'&&s.plan.paused&&!s.plan.scheduleActive&&s.completed&&s.button.disabled,{type:s.cloud.type,watched:s.cloud.watched,completed:s.plan.evidence.completedEpisodes,paused:s.plan.paused,button:s.button});
  await f.python('download',3);s=await f.get();
  check(f.name,'final download after sync still recorded',s.plan.evidence.completedEpisodes.join()==='1,2,3',s.plan.evidence.completedEpisodes);
  check(f.name,'ratings/comments/tags untouched',s.cloud.rate===8&&s.cloud.comment==='Preserve me'&&s.cloud.tags.join()==='fixture',{rate:s.cloud.rate,comment:s.cloud.comment,tags:s.cloud.tags});
}
{
  const f=await fixture('hold-resume');await f.python('find',1);await f.python('download',1);
  await f.cloudChange({offline:true});await f.action('collection',{collectionType:4});let s=await f.get();
  check(f.name,'offline hold: stopped locally, pending, history retained',s.plan.paused&&!s.plan.scheduleActive&&s.plan.collectionSync==='pending'&&s.completed,{paused:s.plan.paused,pending:s.plan.collectionSync,completed:s.completed});
  await f.cloudChange({offline:false});await f.action('collection',{collectionType:4});s=await f.get();
  check(f.name,'retry hold: remains stopped',s.cloud.type===4&&s.plan.paused&&s.completed,{type:s.cloud.type,paused:s.plan.paused,completed:s.completed});
  await f.action('pause',{paused:false});await f.python('execute');s=await f.get();
  check(f.name,'resume execution: back to watching, no manual in-watching menu',s.cloud.type===3&&s.plan.collectionType===3&&!s.plan.paused,{cloudType:s.cloud.type,displayType:s.plan.collectionType,paused:s.plan.paused});
}
{
  const f=await fixture('start-retry');await f.cloudChange({offline:true});await f.python('find',1);await f.cloudChange({offline:false});await f.action('sync');const s=await f.get();
  check(f.name,'successful button retry clears stale sync state, not unrelated review warnings',s.cloud.watched.join()==='1'&&s.plan.evidence.startSync==='synced'&&s.plan.collectionSync==='synced'&&s.label.tone==='success',{watched:s.cloud.watched,startSync:s.plan.evidence.startSync,collectionSync:s.plan.collectionSync,label:s.label,needsAttention:needsAttention(s.record)});
}
{
  const f=await fixture('catchup',{mode:'season_batch',intervalHours:0});await f.python('package',0);await f.python('download',0);let s=await f.get();
  check(f.name,'catchup: completed package, Mark watched, no recurring schedule',s.completed&&s.button.kind==='watched'&&!s.plan.scheduleId,{evidence:s.plan.evidence,button:s.button,scheduleId:s.plan.scheduleId});
  await f.action('collection',{collectionType:2});s=await f.get();
  check(f.name,'catchup Mark watched: full progress and retained history',s.cloud.type===2&&s.cloud.watched.length===3&&s.completed&&s.button.disabled,{type:s.cloud.type,watched:s.cloud.watched,completed:s.completed,button:s.button});
}
{
  const f=await fixture('already-watched');await f.cloudChange({type:2,watched:[1,2,3]});await f.python('find',1);const s=await f.get();
  check(f.name,'executing watched work never regresses',s.cloud.type===2&&s.cloud.writes.length===0,{type:s.cloud.type,writes:s.cloud.writes});
}
{
  const f=await fixture('edit-identity');await f.python('find',2);await f.action('sync');
  const {plan}=await f.get();
  // Same payload as changing only the season in the real edit form: the old
  // track and Bangumi binding are retained by the form.
  let rejected = false;
  try {
    await f.service.mutate('save',{id:plan.id,revision:plan.revision,title:plan.title,season:'S02',trackId:plan.trackId,bangumiSubjectId:plan.bangumiSubjectId,mode:plan.mode,tier:plan.tier,requireZh:plan.requireZh,enqueue:plan.enqueue,intervalHours:plan.intervalHours});
  } catch (error) { if (error.code !== 'plan_identity_change') throw error; rejected = true; }
  const s=await f.get();
  check(f.name,'editing season must reject or isolate previous season evidence',rejected&&s.plan.season==='S01'&&s.plan.evidence.latestFound?.episode===2&&s.plan.syncedEpisode===2,{rejected,title:s.plan.title,season:s.plan.season,bangumiSubjectId:s.plan.bangumiSubjectId,latestFound:s.plan.evidence.latestFound,syncedEpisode:s.plan.syncedEpisode,button:s.button});
}
{
  const f=await fixture('reserved-catchup',{mode:'season_batch',intervalHours:0,schedule:{kind:'once',date:'2099-12-01',time:'20:00',timeZone:'Asia/Shanghai'}});
  let s=await f.get();
  const task=f.tasks.get(s.plan.scheduleId);
  check(f.name,'future date: no immediate job, cloud write or download',f.tasks.size===1&&task.kind==='at'&&!s.plan.runId&&s.cloud.writes.length===0&&!s.completed,{timing:task.timing,runId:s.plan.runId,writes:s.cloud.writes});
  // Simulate DSH delivery of the due task, not an elapsed-time evaluator.
  await f.python('package');task.status='ended';s=await f.get();
  check(f.name,'one-time run: search completed, no download or automatic watched sync',s.plan.evidence.foundPackage&&s.completed&&s.plan.evidence.completedDownloads===0&&s.cloud.type===3&&s.cloud.watched.length===0,{evidence:s.plan.evidence,type:s.cloud.type});
  const p=s.plan;
  await f.service.mutate('save',{id:p.id,revision:p.revision,title:p.title,season:p.season,trackId:p.trackId,bangumiSubjectId:p.bangumiSubjectId,mode:p.mode,tier:'watch',requireZh:p.requireZh,enqueue:p.enqueue,intervalHours:0,schedule:p.schedule});
  s=await f.get();
  check(f.name,'editing conditions after reservation ends does not repeat it',s.plan.scheduleStatus==='ended'&&f.tasks.size===1,{status:s.plan.scheduleStatus,tasks:f.tasks.size});
  await f.python('download');await f.action('collection',{collectionType:2});s=await f.get();
  check(f.name,'reserved catchup: explicit watched retains downloaded history',s.completed&&s.cloud.type===2&&s.cloud.watched.length===3&&(await f.service.list()).plans.length===1,{type:s.cloud.type,completed:s.completed,watched:s.cloud.watched});
}
{
  const f=await fixture('inbox-controls',{schedule:{kind:'weekly',weekdays:[6],time:'21:00',timeZone:'Asia/Shanghai'}});
  let s=await f.get(); const scheduleId=s.plan.scheduleId;
  const timing=JSON.stringify(f.tasks.get(scheduleId).timing);
  await f.action('schedulePause',{paused:true});
  await f.action('requirements',{mode:'next_tracked',tier:'watch',requireZh:true,enqueue:false});
  s=await f.get();
  check(f.name,'resource requirements leave timing and automatic OFF unchanged',!s.plan.paused&&s.plan.schedulePaused&&!s.plan.scheduleActive&&JSON.stringify(f.tasks.get(scheduleId).timing)===timing,{scheduleId:s.plan.scheduleId,timing:f.tasks.get(scheduleId).timing,paused:s.plan.paused,automatic:s.plan.scheduleActive});
  await f.action('check'); s=await f.get();
  check(f.name,'run once while automatic OFF creates a separate job without cloud writes',s.plan.runId!==scheduleId&&f.tasks.size===2&&!s.plan.scheduleActive&&s.cloud.writes.length===0,{runId:s.plan.runId,scheduleId,automatic:s.plan.scheduleActive,writes:s.cloud.writes});
  await f.python('find',2); s=await f.get();
  check(f.name,'manual result enables sync while recurring task stays OFF',!s.button.disabled&&!s.plan.scheduleActive&&s.cloud.watched.length===0,{button:s.button,automatic:s.plan.scheduleActive,cloud:s.cloud.watched});
  await f.action('sync'); s=await f.get();
  check(f.name,'sync covers found gaps without downloaded/completed claims',s.cloud.watched.join()==='1,2'&&!s.completed&&inboxResult(s.record).download.status!=='completed'&&s.button.disabled,{watched:s.cloud.watched,completed:s.completed,result:inboxResult(s.record).text});
  await f.action('schedule',{schedule:{kind:'weekly',weekdays:[7],time:'22:00',timeZone:'Asia/Shanghai'}});s=await f.get();
  check(f.name,'schedule-only editor preserves resource rules and OFF state',s.plan.tier==='watch'&&s.plan.requireZh&&!s.plan.enqueue&&!s.plan.scheduleActive,{tier:s.plan.tier,requireZh:s.plan.requireZh,enqueue:s.plan.enqueue,automatic:s.plan.scheduleActive});
}
const result={network:'blocked; fake account only',workspace,passed:reports.filter(r=>r.passed).length,failed:reports.filter(r=>!r.passed).length,checks:reports};
await write(path.join(workspace,'report.json'),result);
console.log(JSON.stringify(result,null,2));
if(result.failed)process.exitCode=1;
