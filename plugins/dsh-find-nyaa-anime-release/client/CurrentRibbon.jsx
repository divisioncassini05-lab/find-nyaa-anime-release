import React, { useEffect, useId, useRef, useState } from 'react';
import { WhaleMascot } from './WhaleMascot.jsx';

// A separate foreground ornament; the painted ocean assets stay unchanged.
export function CurrentRibbon({ enabled = true, reduced = false, check }) {
  const id = useId().replace(/:/g, '');
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
  const running = enabled && !reduced && visible && onScreen;
  return <div ref={ref} className="anime-current" data-running={running}>
    <svg className="anime-current-thread" aria-hidden="true" viewBox="0 0 1200 72" preserveAspectRatio="none" fill="none">
      <defs><linearGradient id={`${id}-thread`} x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
        <stop stopColor="var(--ap-current-edge)" stopOpacity=".1"/>
        <stop offset=".25" stopColor="var(--ap-current-edge)" stopOpacity=".7"/>
        <stop offset=".72" stopColor="var(--ap-current-lilac)" stopOpacity=".65"/>
        <stop offset="1" stopColor="var(--ap-current-edge)" stopOpacity=".1"/>
      </linearGradient></defs>
      <path d="M0 42C150 60 245 16 410 29S675 60 860 38 1070 33 1200 40" stroke={`url(#${id}-thread)`} strokeWidth="1.2"/>
      <path d="M0 45C150 63 245 19 410 32S675 63 860 41 1070 36 1200 43" stroke="var(--ap-current-glint)" strokeOpacity=".25" strokeWidth=".7"/>
    </svg>
    <div className="anime-current-rest">
      <svg aria-hidden="true" viewBox="0 0 220 72" preserveAspectRatio="none" fill="none">
        <defs>
          <linearGradient id={`${id}-body`} x1="110" y1="24" x2="110" y2="52" gradientUnits="userSpaceOnUse">
            <stop stopColor="var(--ap-current-glint)" stopOpacity=".5"/>
            <stop offset=".42" stopColor="var(--ap-current-fill)" stopOpacity=".22"/>
            <stop offset=".75" stopColor="var(--ap-current-edge)" stopOpacity=".16"/>
            <stop offset="1" stopColor="var(--ap-current-glint)" stopOpacity=".04"/>
          </linearGradient>
          <linearGradient id={`${id}-rim`} x1="8" y1="0" x2="212" y2="0" gradientUnits="userSpaceOnUse">
            <stop stopColor="var(--ap-current-edge)" stopOpacity="0"/>
            <stop offset=".28" stopColor="var(--ap-current-edge)" stopOpacity=".8"/>
            <stop offset=".6" stopColor="var(--ap-current-glint)"/>
            <stop offset=".85" stopColor="var(--ap-current-lilac)" stopOpacity=".65"/>
            <stop offset="1" stopColor="var(--ap-current-edge)" stopOpacity="0"/>
          </linearGradient>
        </defs>
        <path d="M8 37C35 37 48 24 75 27C91 29 99 33 111 33C124 33 132 28 149 27C176 26 192 35 212 37C187 39 174 48 148 48C129 48 121 45 111 45C96 45 80 51 58 46C36 42 22 38 8 37Z" fill={`url(#${id}-body)`}/>
        <path d="M8 37C35 37 48 24 75 27C91 29 99 33 111 33C124 33 132 28 149 27C176 26 192 35 212 37" stroke={`url(#${id}-rim)`} strokeWidth="1.4"/>
        <path d="M30 39C53 46 73 49 96 44M130 45C153 50 176 43 194 39" stroke="var(--ap-current-edge)" strokeOpacity=".3" strokeWidth=".7"/>
        <path d="M35 35C52 31 63 30 78 32M145 32C160 30 173 33 185 36M55 40C66 43 79 42 88 41M143 41C153 43 166 41 174 39" stroke="var(--ap-current-glint)" strokeOpacity=".65" strokeWidth=".85" strokeLinecap="round"/>
        <path d="M87 34C98 38 124 38 136 34" stroke="var(--ap-current-glint)" strokeOpacity=".7" strokeWidth=".8"/>
      </svg>
      <span className="anime-current-seat" aria-hidden="true"/>
      <WhaleMascot running={enabled && !reduced && visible} visible={onScreen} check={check}/>
    </div>
  </div>;
}
