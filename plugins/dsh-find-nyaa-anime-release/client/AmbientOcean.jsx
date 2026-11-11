import React, { useEffect, useRef } from 'react';
import { SPECIES, OceanWorld } from './ocean/faunaMotion.mjs';
import { loadSprites, drawWorld, MotionClock } from './ocean/renderer.mjs';
import { WaterAtmosphere, loadAtmosphereAssets, drawAtmosphere } from './ocean/waterAtmosphere.mjs';
import { seedAmbient, floorFit } from './ocean/scene.mjs';
import { environmentManifest } from './ocean/assets.mjs';

export function AmbientOcean({ running }) {
  const root = useRef(null), fish = useRef(null), waterCanvas = useRef(null);
  const engine = useRef(null), playing = useRef(running);
  playing.current = running;
  useEffect(() => { engine.current?.setRunning(running); }, [running]);
  useEffect(() => {
    const element = root.current, panel = element.closest('.anime-panel');
    let disposed = false, generation = 0, world, water, sprites, waterAssets, clock;
    let theme = '', width = 0, height = 0;
    const readTheme = () => getComputedStyle(element.parentElement).getPropertyValue('--ap-environment-theme').trim() === 'night' ? 'night' : 'day';
    const available = new Set(Object.keys(environmentManifest.clips));
    function draw(dt = 0) {
      if (!world || !sprites || !waterAssets) return;
      world.step(dt);
      drawAtmosphere(waterCanvas.current, water, waterAssets, world.time);
      drawWorld(fish.current, world, sprites);
      element.dataset.time = world.time.toFixed(2);
      element.dataset.count = String(world.animals.length);
    }
    function resize() {
      const rect = element.getBoundingClientRect();
      width = Math.max(1, rect.width); height = Math.max(1, rect.height);
      const ratio = Math.min(2, devicePixelRatio || 1);
      for (const canvas of [fish.current, waterCanvas.current]) {
        canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      }
      world?.resize(width, height);
      water = new WaterAtmosphere({ width, height, theme });
      water.details.fit = floorFit(width, height);
      // Environmental fish avoid the actor without changing her component or her fish.
      const actor = panel?.querySelector('.anime-whale')?.getBoundingClientRect();
      if (world) world.safeZones = actor ? [{ x:actor.left - rect.left, y:actor.top - rect.top, width:actor.width, height:actor.height }] : [];
      draw();
    }
    async function refreshTheme() {
      const next = readTheme();
      if (next === theme) return;
      theme = next;
      const request = ++generation;
      element.dataset.theme = theme; element.dataset.state = 'loading';
      clock?.dispose(); clock = null; engine.current = null; sprites = null;
      resize();
      const variants = new Set(SPECIES.filter(s => s.theme === theme).flatMap(s => s.variants.map(v => v[0])));
      const selected = Object.fromEntries(Object.entries(environmentManifest.sprites).filter(([id]) => [...variants].some(v => id === v || id.startsWith(`${v}-`))));
      try {
        const [loaded, assets] = await Promise.all([loadSprites({ sprites:selected }), loadAtmosphereAssets(environmentManifest)]);
        if (disposed || request !== generation) return;
        sprites = loaded; waterAssets = assets;
        world = new OceanWorld({ width, height, theme, available, seed:22 });
        seedAmbient(world); resize();
        clock = new MotionClock(draw, { element }); engine.current = clock;
        clock.setRunning(playing.current);
        element.dataset.state = 'ready';
      } catch {
        if (!disposed && request === generation) element.dataset.state = 'unavailable';
      }
    }
    const observer = new ResizeObserver(resize); observer.observe(element);
    const themes = new MutationObserver(refreshTheme);
    for (const target of [document.documentElement, document.body]) themes.observe(target, { attributes:true, attributeFilter:['class','data-theme','data-ds-dark-theme'] });
    refreshTheme();
    return () => { disposed = true; generation++; clock?.dispose(); observer.disconnect(); themes.disconnect(); engine.current = null; };
  }, []);
  return <div ref={root} className="anime-environment" aria-hidden="true" inert="">
    <canvas ref={waterCanvas} className="anime-environment-water"/>
    <canvas ref={fish} className="anime-environment-fauna"/>
  </div>;
}
