import enter from '../assets/ocean/whale/checking/checking-enter.gif';
import guide from '../assets/ocean/whale/checking/checking-loop.gif';
import exit from '../assets/ocean/whale/checking/checking-exit.gif';
import success from '../assets/ocean/whale/checking/success.gif';
import attention from '../assets/ocean/whale/checking/attention.gif';
import birth from '../assets/ocean/whale/checking/fish-birth.gif';
import swim from '../assets/ocean/whale/checking/fish-swim.gif';
import water from '../assets/ocean/whale/checking/water-gather.gif';
import metadata from '../assets/ocean/whale/checking/manifest.json';
import { loadWhaleChecking } from './whale-checking.mjs';

export const checkingSources = { enter, guide, exit, success, attention, birth, swim, water };
export const checkingManifest = metadata;

// The bundler inlines these GIFs, just like the existing whale clips.
export function prepareWhaleChecking(options) {
  return loadWhaleChecking({ ...options, sources: checkingSources, metadata });
}
