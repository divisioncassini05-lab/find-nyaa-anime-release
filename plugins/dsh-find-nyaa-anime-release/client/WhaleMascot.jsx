import React, { useEffect, useRef, useState } from 'react';
import idle from '../assets/ocean/whale/ambient/idle-character.gif';
import book from '../assets/ocean/whale/ambient/book-loop.gif';
import feet from '../assets/ocean/whale/ambient/idle-feet.gif';
import sleeve from '../assets/ocean/whale/ambient/idle-sleeve.gif';
import droplet from '../assets/ocean/whale/ambient/idle-droplet.gif';
import trace from '../assets/ocean/whale/ambient/reading-trace.gif';
import think from '../assets/ocean/whale/ambient/reading-think.gif';
import ambient from '../assets/ocean/whale/ambient/manifest.json';
import palm from '../assets/ocean/whale/ambient/palm-motion.json';
import receive from '../assets/ocean/whale/receive.gif';
import reading from '../assets/ocean/whale/reading.gif';
import putBack from '../assets/ocean/whale/return.gif';
import poster from '../assets/ocean/whale/idle-poster.png';
import { decodeWhaleClips, closeWhaleClips } from './whale-timeline.mjs';
import { WhaleAmbientTimeline, clipFrame } from './whale-ambient-timeline.mjs';
import { drawTraceLiquid, drawPalmLiquid } from './whale-liquid.mjs';

const sources = {idle, receive, reading, return: putBack};
const actionSources={'idle-feet':feet,'idle-sleeve':sleeve,'idle-droplet':droplet,'reading-trace':trace,'reading-think':think};

// Visual-only companion: no host services, tracking state or network access.
export function WhaleMascot({ running }) {
  const [greeting, setGreeting] = useState(false);
  const timer = useRef(null);
  const canvas = useRef(null);
  const button = useRef(null);
  const engine = useRef(null);
  const playing = useRef(running);
  const requested = useRef('auto');
  playing.current = running;
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    engine.current?.setRunning(running);
    if (!running) { clearTimeout(timer.current); timer.current = null; setGreeting(false); }
  }, [running]);
  useEffect(() => {
    let disposed = false, clips = null, raf = 0, last = null;
    let loading=null, cached=null;
    const failed=new Set();
    const context = canvas.current.getContext('2d');
    const surface = canvas.current;
    const control = button.current;
    if (!context) { control.dataset.playback = 'poster'; return; }
    let timeline;
    const effects=document.createElement('canvas');effects.width=effects.height=512;
    const fx=effects.getContext('2d');
    async function prepare(id) {
      if(!id||loading||clips[id]||failed.has(id))return;
      loading=id;
      try {
        const loaded=await decodeWhaleClips({[id]:actionSources[id]},()=>disposed,globalThis.ImageDecoder,{[id]:ambient.actions[id].frames});
        if(disposed){closeWhaleClips(loaded);return;}
        if(cached&&cached!==timeline.action){closeWhaleClips({[cached]:clips[cached]});delete clips[cached];}
        Object.assign(clips,loaded);cached=id;
      } catch {failed.add(id);} finally {loading=null;}
    }
    function draw() {
        context.clearRect(0, 0, 512, 512);
        context.drawImage(clips[timeline.stage].frames[timeline.frame], 0, 0);
        if(timeline.parent==='idle'){
          const elapsed=timeline.bookElapsed%clips.book.durations.reduce((a,b)=>a+b,0);
          context.drawImage(clips.book.frames[clipFrame(clips.book.durations,elapsed)],0,0);
        }
        if(fx){
          fx.clearRect(0,0,512,512);
          if(timeline.action==='reading-trace')drawTraceLiquid(fx,timeline.elapsed);
          if(timeline.action==='idle-droplet')drawPalmLiquid(fx,palm,timeline.elapsed);
          context.drawImage(effects,0,0);
        }
        surface.dataset.stage = timeline.stage;
        surface.dataset.parent = timeline.parent;
        surface.dataset.frame = String(timeline.frame);
        surface.dataset.elapsed = String(timeline.totalElapsed);
        surface.dataset.bookElapsed=String(timeline.bookElapsed);
    }
    function tick(now) {
      if (disposed || !playing.current) return;
      if (last !== null) timeline.advance(Math.max(0, now-last));
      if(failed.has(timeline.pendingAction))timeline.pendingAction=null;
      prepare(timeline.pendingAction);
      last = now;
      draw();
      raf = requestAnimationFrame(tick);
    }
    const controller = {
      request(mode) { requested.current = mode; timeline?.request(mode); },
      setRunning(value) {
        timeline?.setRunning(value);
        cancelAnimationFrame(raf);
        last = null;
        if (value && timeline && !disposed) raf = requestAnimationFrame(tick);
      },
      get stage() { return timeline?.stage || 'idle'; },
    };
    engine.current = controller;
    decodeWhaleClips({...sources,book}, () => disposed,globalThis.ImageDecoder,{idle:16,receive:16,reading:16,return:16,book:16}).then((loaded) => {
      if (disposed) { closeWhaleClips(loaded); return; }
      clips = loaded;
      timeline = new WhaleAmbientTimeline(Object.fromEntries(Object.entries(clips).map(([key, value]) => [key, value.durations])),ambient.actions,{ready:id=>Boolean(clips[id])});
      timeline.request(requested.current);
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
      closeWhaleClips(clips);
      if (engine.current === controller) engine.current = null;
    };
  }, []);
  const greet = () => {
    const readingNext = requested.current === 'auto'
      ? ['idle', 'return'].includes(engine.current?.stage || 'idle') : requested.current === 'idle';
    engine.current?.request(readingNext ? 'reading' : 'idle');
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
      onClick={greet} draggable={false} onDragStart={(event) => event.preventDefault()}>
      <span className="anime-whale-float" aria-hidden="true">
        <img className="anime-whale-poster" src={poster} alt="" draggable={false}/>
        <canvas ref={canvas} className="anime-whale-canvas" width="512" height="512"/>
      </span>
    </button>
    <span className="anime-whale-announcement" role="status">{greeting ? '小鲸鱼轻轻回应了你。' : ''}</span>
  </div>;
}
