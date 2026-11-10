import ink from '../assets/ocean/whale/ambient/ink-study.gif';
import water from '../assets/ocean/whale/ambient/palm-study.gif';
import manifest from '../assets/ocean/whale/ambient/manifest.json';
import arm from '../assets/ocean/whale/ambient/arm-manifest.json';
import palms from '../assets/ocean/whale/ambient/palm-motion.json';
import {createLiquidPlayer} from './whale-liquid-depth.mjs';

const sources = {'reading-trace': ink, 'idle-droplet': water};

export function createNativeLiquid(options = {}) {
  return createLiquidPlayer({...options, sources, manifest, landmarks: arm.landmarks, palms});
}
