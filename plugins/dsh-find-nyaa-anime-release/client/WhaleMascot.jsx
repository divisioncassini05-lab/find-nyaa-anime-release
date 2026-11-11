import React, { useEffect, useRef, useState } from 'react';
import idle from '../assets/ocean/whale/ambient/idle-character.gif';
import book from '../assets/ocean/whale/ambient/book-loop.gif';
import feet from '../assets/ocean/whale/ambient/idle-feet.gif';
import sleeve from '../assets/ocean/whale/ambient/idle-sleeve.gif';
import droplet from '../assets/ocean/whale/ambient/idle-droplet.gif';
import trace from '../assets/ocean/whale/ambient/reading-trace.gif';
import think from '../assets/ocean/whale/ambient/reading-think.gif';
import ambient from '../assets/ocean/whale/ambient/manifest.json';
import receive from '../assets/ocean/whale/receive.gif';
import reading from '../assets/ocean/whale/reading.gif';
import putBack from '../assets/ocean/whale/return.gif';
import poster from '../assets/ocean/whale/idle-poster.png';
import { decodeWhaleClips, closeWhaleClips } from './whale-timeline.mjs';
import { WhaleAmbientTimeline, clipFrame } from './whale-ambient-timeline.mjs';
import { createNativeLiquid } from './whale-native-liquid.mjs';
import { prepareWhaleChecking } from './whale-checking-assets.mjs';
import { WhaleCheckHandoff } from './whale-check-handoff.mjs';
import { prepareReadingRetreat } from './whale-reading-retreat.mjs';
import { ReadingRetreatHandoff } from './whale-reading-handoff.mjs';

const sources = {idle, receive, reading, return: putBack};
const actionSources={'idle-feet':feet,'idle-sleeve':sleeve,'idle-droplet':droplet,'reading-trace':trace,'reading-think':think};

// Visual-only companion: no host services, tracking state or network access.
export function WhaleMascot({ running, visible = true, check }) {
  const [greeting, setGreeting] = useState(false);
  const timer = useRef(null);
  const canvas = useRef(null);
  const button = useRef(null);
  const magic = useRef(null);
  const engine = useRef(null);
  const playing = useRef(running);
  const onScreen = useRef(visible);
  const checkSignal = useRef(check);
  const requested = useRef('auto');
  playing.current = running;
  onScreen.current = visible;
  checkSignal.current = check;
  useEffect(() => { engine.current?.check(check); }, [check]);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    engine.current?.setRunning(running);
    if (!running) { clearTimeout(timer.current); timer.current = null; setGreeting(false); }
  }, [running]);
  useEffect(() => {
    let disposed = false, clips = null, raf = 0, last = null;
    let loading=null, cached=null, liquids=null, checking=null, handoff=null;
    let checkingLoad=null, checkingFailed=false, wanted=false, pendingStart=false, pendingResult=null;
    let retreat=null, retreatAssets=null, retreatLoad=null, retreatFailed=false, checkAfterRetreat=false;
    const failed=new Set();
    const context = canvas.current.getContext('2d');
    const surface = canvas.current;
    const control = button.current;
    if (!context) { control.dataset.playback = 'poster'; return; }
    let timeline;
    const panel=control.closest('.anime-panel');
    const fish=document.createElement('canvas');
    fish.className='anime-summoned-fish';fish.setAttribute('aria-hidden','true');
    panel?.append(fish);
    const fishContext=fish.getContext('2d'), magicContext=magic.current.getContext('2d');
    function geometry() {
      const area=panel?.getBoundingClientRect(), actor=surface.getBoundingClientRect();
      if(!area?.width||!area.height||!actor.width)return null;
      const dpr=Math.min(2,window.devicePixelRatio||1);
      const width=Math.round(area.width*dpr),height=Math.round(area.height*dpr);
      if(fish.width!==width||fish.height!==height){fish.width=width;fish.height=height;}
      fishContext?.setTransform(dpr,0,0,dpr,0,0);
      return {width:area.width,height:area.height,left:actor.left-area.left,top:actor.top-area.top,
        characterWidth:actor.width,viewTop:Math.max(0,-area.top),
        viewBottom:Math.max(0,Math.min(area.height,window.innerHeight-area.top)),visible:onScreen.current};
    }
    async function prepareChecking() {
      if(!clips||checkingLoad||checking||checkingFailed||!pendingStart||retreat?.busy)return;
      checkingLoad=prepareWhaleChecking({idle:clips.idle,book:clips.book,cancelled:()=>disposed});
      try {
        const loaded=await checkingLoad;
        if(disposed){loaded.dispose();return;}
        checking=loaded;
        timeline.setBlocked(false);
        handoff=new WhaleCheckHandoff(timeline,checking);
        if(pendingStart)handoff.start();
        if(pendingResult!==null){
          handoff.finish(pendingResult);
          if(wanted)handoff.start();
        }
      } catch { checkingFailed=true;timeline?.setBlocked(false); }
      finally { checkingLoad=null; }
    }
    async function prepareRetreat() {
      if(retreatAssets||retreatLoad||retreatFailed||!clips)return;
      retreatLoad=prepareReadingRetreat({reading:clips.reading,cancelled:()=>disposed});
      try {
        const loaded=await retreatLoad;
        if(disposed){loaded.dispose();return;}
        retreatAssets=loaded;
      } catch {retreatFailed=true;retreat?.fail();}
      finally {retreatLoad=null;}
    }
    function beginChecking() {
      checkAfterRetreat=false;requested.current='idle';
      if(handoff)handoff.start();
      else if(!checkingFailed){timeline?.request('idle');timeline?.setBlocked(true);prepareChecking();}
    }
    async function prepare(id) {
      if(!id||loading||clips[id]||failed.has(id))return;
      loading=id;
      let loaded;
      try {
        loaded=await decodeWhaleClips({[id]:actionSources[id]},()=>disposed,globalThis.ImageDecoder,{[id]:ambient.actions[id].frames});
        if(disposed){closeWhaleClips(loaded);return;}
        await liquids?.load(id,loaded[id]);
        if(disposed){closeWhaleClips(loaded);return;}
        if(cached&&cached!==timeline.action){closeWhaleClips({[cached]:clips[cached]});delete clips[cached];}
        Object.assign(clips,loaded);cached=id;
      } catch {closeWhaleClips(loaded);failed.add(id);} finally {loading=null;}
    }
    function draw() {
        magicContext?.clearRect(0,0,768,768);
        const retreatOwns=retreat?.ownsCharacter;
        if(retreatOwns)retreatAssets.drawCharacter(context,retreat.actor);
        const ownsCharacter=retreatOwns||checking?.drawCharacter(context,timeline.bookElapsed);
        if(!ownsCharacter){
          context.clearRect(0, 0, 512, 512);
          context.drawImage(clips[timeline.stage].frames[timeline.frame], 0, 0);
        }
        if(!ownsCharacter&&timeline.parent==='idle'){
          const elapsed=timeline.bookElapsed%clips.book.durations.reduce((a,b)=>a+b,0);
          context.drawImage(clips.book.frames[clipFrame(clips.book.durations,elapsed)],0,0);
        }
        if(!ownsCharacter)liquids?.draw(context,timeline.action,timeline.elapsed,timeline.frame);
        checking?.drawFish(fishContext);checking?.drawMagic(magicContext);
        if(retreatOwns){magicContext?.clearRect(0,0,768,768);retreatAssets.drawMagic(magicContext,retreat.actor);}
        surface.dataset.stage = retreatOwns ? `reading-retreat-${retreat.state}` : ownsCharacter ? `checking-${checking.state}` : timeline.stage;
        surface.dataset.parent = timeline.parent;
        surface.dataset.frame = String(retreatOwns?retreat.actor.sample().character.frame:timeline.frame);
        surface.dataset.elapsed = String(timeline.totalElapsed);
        surface.dataset.bookElapsed=String(timeline.bookElapsed);
        surface.dataset.checking=checking?.state || (pendingStart&&!checkingFailed?'loading':'idle');
        surface.dataset.readingRetreat=retreat?.state||'idle';
        surface.dataset.retreatClip=retreatOwns?retreat.actor.sample().character.clip:'';
        surface.dataset.retreatCompleted=String(retreat?.completed||0);
        fish.dataset.count=String(checking?.school.items.length||0);
        fish.dataset.waterBottom=String(checking?.school.waterBottom||0);
    }
    function tick(now) {
      if (disposed || !playing.current) return;
      const delta=last===null?0:Math.min(100,Math.max(0,now-last));
      const bounds=geometry();
      const retreatAdvanced=onScreen.current&&retreat?.advance(delta);
      if(checkAfterRetreat&&!retreat?.busy)beginChecking();
      if(retreatAdvanced){
        if(bounds)checking?.update(delta,bounds);
      }else if(handoff){
        if(bounds){
          if(onScreen.current||handoff.needsIdle)handoff.advance(delta,bounds);
          else checking.update(delta,bounds);
        }
      }
      else if(onScreen.current)timeline.advance(delta);
      if(failed.has(timeline.pendingAction))timeline.pendingAction=null;
      prepare(timeline.pendingAction);
      last = now;
      draw();
      raf = requestAnimationFrame(tick);
    }
    const controller = {
      request(mode) { requested.current = mode; timeline?.request(mode); },
      tapReading(mode) {
        if(!playing.current||!onScreen.current||retreatFailed||wanted||handoff?.needsIdle)return false;
        return retreat?.tap(mode)||false;
      },
      check(value) {
        if(!value)return;
        if(value.checking&&!wanted){
          wanted=true;pendingStart=true;
          // Keep the first committed result while loading; wanted queues the restart.
          if(handoff||pendingResult==='cancelled')pendingResult=null;
          retreat?.cancelPending();
          if(retreat?.busy)checkAfterRetreat=true;
          else beginChecking();
        }else if(!value.checking&&wanted){
          wanted=false;
          const result=value.result||'cancelled';
          if(handoff)handoff.finish(result);
          else if(pendingResult===null)pendingResult=result;
        }
      },
      setRunning(value) {
        timeline?.setRunning(value);
        if(!value)retreat?.clearClicks();
        cancelAnimationFrame(raf);
        last = null;
        if (value && timeline && !disposed) raf = requestAnimationFrame(tick);
      },
      get stage() { return timeline?.stage || 'idle'; },
      get checking() { return wanted||checking?.needsIdle||Boolean(checkingLoad); },
    };
    engine.current = controller;
    decodeWhaleClips({...sources,book}, () => disposed,globalThis.ImageDecoder,{idle:16,receive:16,reading:16,return:16,book:16}).then((loaded) => {
      if (disposed) { closeWhaleClips(loaded); return; }
      clips = loaded;
      timeline = new WhaleAmbientTimeline(Object.fromEntries(Object.entries(clips).map(([key, value]) => [key, value.durations])),ambient.actions,{ready:id=>Boolean(clips[id])});
      retreat=new ReadingRetreatHandoff(timeline,{ready:()=>retreatAssets,load:prepareRetreat,
        single:mode=>controller.request(mode)});
      liquids=createNativeLiquid({cancelled:()=>disposed});
      timeline.request(requested.current);
      controller.check(checkSignal.current);
      if(pendingStart){timeline.setBlocked(true);prepareChecking();}
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      draw();
      control.dataset.playback = 'decoded';
      controller.setRunning(playing.current);
    }).catch(() => {
      closeWhaleClips(clips); clips = null;
      if (!disposed) control.dataset.playback = 'poster';
    });
    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      checking?.dispose();retreatAssets?.dispose();liquids?.dispose();fish.remove();
      closeWhaleClips(clips);
      if (engine.current === controller) engine.current = null;
    };
  }, []);
  const greet = () => {
    if(engine.current?.checking)return;
    const readingNext = requested.current === 'auto'
      ? ['idle', 'return'].includes(engine.current?.stage || 'idle') : requested.current === 'idle';
    const mode=readingNext?'reading':'idle';
    if(!engine.current?.tapReading(mode))engine.current?.request(mode);
    clearTimeout(timer.current);
    setGreeting(true);
    timer.current = setTimeout(() => { setGreeting(false); timer.current = null; }, 1800);
  };
  return <div className={`anime-whale-seat${greeting ? ' is-greeting' : ''}`}>
    <span className="anime-whale-water" aria-hidden="true">
      <span className="anime-whale-contact"/>
      <span className="anime-whale-ripple anime-whale-ripple-inner"/>
      <span className="anime-whale-ripple anime-whale-ripple-outer"/>
    </span>
    <button ref={button} type="button" className="anime-whale" data-playback="loading" title="轻轻碰一下小鲸鱼" aria-label="轻轻碰一下小鲸鱼"
      onClick={greet} onKeyDown={event=>{if(event.repeat&&['Enter',' '].includes(event.key))event.preventDefault();}} draggable={false} onDragStart={(event) => event.preventDefault()}>
      <span className="anime-whale-float" aria-hidden="true">
        <img className="anime-whale-poster" src={poster} alt="" draggable={false}/>
        <canvas ref={canvas} className="anime-whale-canvas" width="512" height="512"/>
        <canvas ref={magic} className="anime-whale-magic" width="768" height="768"/>
      </span>
    </button>
    <span className="anime-whale-announcement" role="status">{greeting ? '小鲸鱼轻轻回应了你。' : ''}</span>
  </div>;
}
