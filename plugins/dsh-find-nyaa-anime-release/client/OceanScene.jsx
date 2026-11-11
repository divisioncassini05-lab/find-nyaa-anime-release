import React, { useEffect, useRef, useState } from 'react';
import lightWater from '../assets/ocean/water-light.webp';
import darkWater from '../assets/ocean/water-dark.webp';
import starfish from '../assets/ocean/carved-starfish.webp';
import bubbles from '../assets/ocean/overlays/bubble-trail.webp';
import currents from '../assets/ocean/overlays/current-traces.webp';
import { JellyfishLight } from './JellyfishLight.jsx';
import { chooseEncounter } from './oceanFauna.mjs';
import { FAUNA_ASSETS } from './oceanFaunaAssets.js';

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

function FaunaPass({ theme }) {
  const [pass, setPass] = useState(() => ({ ...chooseEncounter(theme), cycle: 0 }));
  const next = (event) => {
    if (event.target !== event.currentTarget || event.animationName !== 'anime-fauna-pass') return;
    setPass((previous) => ({ ...chooseEncounter(theme), cycle: previous.cycle + 1 }));
  };
  return <div className={`anime-${theme}-fauna anime-fauna-lane`}>
    <div key={pass.cycle} className="anime-fauna-pass" data-species={pass.id}
      data-variant={pass.variant} data-count={pass.count} data-kind={pass.kind}
      data-movement={pass.movement} data-cycle={pass.cycle} onAnimationEnd={next}
      style={{ '--fauna-width': `${pass.width}px`, '--fauna-height': `${pass.height}px`,
        '--fauna-duration': `${pass.duration}s`, '--fauna-delay': pass.cycle === 0 ? `${-pass.duration * .28}s` : '0s' }}>
      <div className="anime-fauna-body">
        {pass.kind === 'jelly' ? <JellyfishLight src={FAUNA_ASSETS[pass.variant]}/>
          : <img src={FAUNA_ASSETS[pass.variant]} alt="" draggable="false"/>}
      </div>
    </div>
  </div>;
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
    {['surface', 'floor'].map((layer) => <React.Fragment key={layer}>
      <img className={`anime-water anime-water-${layer} anime-water-light`} src={lightWater} alt="" draggable="false"/>
      <img className={`anime-water anime-water-${layer} anime-water-dark`} src={darkWater} alt="" draggable="false"/>
    </React.Fragment>)}
    <img className="anime-starfish" src={starfish} alt="" draggable="false"/>
    <div className="anime-water-lighting"/>
    <img className="anime-current-traces" src={currents} alt="" draggable="false"/>
    <FaunaPass theme="day"/>
    <FaunaPass theme="night"/>
    <img className="anime-bubble-trail" src={bubbles} alt="" draggable="false"/>
  </div>;
}
