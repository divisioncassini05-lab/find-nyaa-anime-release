import React from 'react';
import lantern from '../assets/ocean/overlays/jellyfish-lantern.webp';

// Self-contained source light; it never changes nearby content or the mascot.
export function JellyfishLight({ src = lantern }) {
  return <span className="anime-jellyfish-light" aria-hidden="true">
    <img className="anime-jellyfish-glow" src={src} alt="" draggable="false"/>
    <img className="anime-jellyfish-body" src={src} alt="" draggable="false"/>
  </span>;
}
