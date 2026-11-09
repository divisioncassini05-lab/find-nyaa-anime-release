import React, { useEffect, useRef, useState } from 'react';
import idle from '../assets/ocean/whale/idle.gif';
import receive from '../assets/ocean/whale/receive.gif';
import reading from '../assets/ocean/whale/reading.gif';
import putBack from '../assets/ocean/whale/return.gif';
import poster from '../assets/ocean/whale/idle-poster.png';
import { WhaleTimeline, decodeWhaleClips, closeWhaleClips } from './whale-timeline.mjs';

const sources = {idle, receive, reading, return: putBack};

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
    let disposed = false, clips = null, raf = 0, last = null, drawKey = '';
    const context = canvas.current.getContext('2d');
    const surface = canvas.current;
    const control = button.current;
    if (!context) { control.dataset.playback = 'poster'; return; }
    let timeline;
    function draw() {
      const key = timeline.stage + ':' + timeline.frame;
      if (key !== drawKey) {
        context.clearRect(0, 0, 512, 512);
        context.drawImage(clips[timeline.stage].frames[timeline.frame], 0, 0);
        surface.dataset.stage = timeline.stage;
        surface.dataset.frame = String(timeline.frame);
        surface.dataset.elapsed = String(timeline.totalElapsed);
        drawKey = key;
      }
    }
    function tick(now) {
      if (disposed || !playing.current) return;
      if (last !== null) timeline.advance(Math.max(0, now-last));
      last = now;
      draw();
      raf = requestAnimationFrame(tick);
    }
    const controller = {
      request(mode) { requested.current = mode; timeline?.request(mode); },
      setRunning(value) {
        cancelAnimationFrame(raf);
        last = null;
        if (value && timeline && !disposed) raf = requestAnimationFrame(tick);
      },
      get stage() { return timeline?.stage || 'idle'; },
    };
    engine.current = controller;
    decodeWhaleClips(sources, () => disposed).then((loaded) => {
      if (disposed) { closeWhaleClips(loaded); return; }
      clips = loaded;
      timeline = new WhaleTimeline(Object.fromEntries(Object.entries(clips).map(([key, value]) => [key, value.durations])));
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
