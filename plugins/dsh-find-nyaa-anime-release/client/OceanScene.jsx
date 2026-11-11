import React, { useEffect, useRef, useState } from 'react';
import lightWater from '../assets/ocean/water-light.webp';
import darkWater from '../assets/ocean/water-dark.webp';
import starfish from '../assets/ocean/carved-starfish.webp';
import { AmbientOcean } from './AmbientOcean.jsx';
import environmentCss from './oceanAmbient.css';

export const MOTION_KEY = 'anime-panel-ocean-motion';

export function useOceanMotion() {
  const [enabled, setEnabled] = useState(() => {
    try { return localStorage.getItem(MOTION_KEY) !== 'off'; } catch { return true; }
  });
  const [reduced, setReduced] = useState(() => globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false);
  useEffect(() => {
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    try { localStorage.setItem(MOTION_KEY, enabled ? 'on' : 'off'); } catch { /* Storage is optional. */ }
  }, [enabled]);
  return { enabled, reduced, toggle: () => setEnabled((value) => !value) };
}

export function OceanScene({ enabled, reduced }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(!document.hidden);
  const [onScreen, setOnScreen] = useState(true);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', update);
    const observer = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting));
    observer.observe(ref.current);
    return () => { document.removeEventListener('visibilitychange', update); observer.disconnect(); };
  }, []);
  return <div ref={ref} className="anime-ocean" aria-hidden="true"
    data-static={!enabled || reduced} data-running={enabled && !reduced && visible && onScreen}>
    <style>{environmentCss}</style>
    {['surface', 'floor'].map((layer) => <React.Fragment key={layer}>
      <img className={`anime-water anime-water-${layer} anime-water-light`} src={lightWater} alt="" draggable="false"/>
      <img className={`anime-water anime-water-${layer} anime-water-dark`} src={darkWater} alt="" draggable="false"/>
    </React.Fragment>)}
    <img className="anime-starfish" src={starfish} alt="" draggable="false"/>
    <div className="anime-water-lighting"/>
    <AmbientOcean running={enabled && !reduced && visible && onScreen}/>
  </div>;
}
