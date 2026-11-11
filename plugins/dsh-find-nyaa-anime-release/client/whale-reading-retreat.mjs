import character from '../assets/ocean/whale/reading-retreat/character.gif';
import recover from '../assets/ocean/whale/reading-retreat/recover.gif';
import rise from '../assets/ocean/whale/reading-retreat/rise.gif';
import hold from '../assets/ocean/whale/reading-retreat/hold.gif';
import reveal from '../assets/ocean/whale/reading-retreat/reveal.gif';
import waterCore from '../assets/ocean/whale/reading-retreat/water-core.png';
import metadata from '../assets/ocean/whale/reading-retreat/manifest.json';
import {decodeWhaleClips,closeWhaleClips} from './whale-timeline.mjs';
import {drawWater} from './whale-retreat-water.mjs';

// Decode only on the first confirmed reading triple-click; nothing is fetched externally.
export async function prepareReadingRetreat({reading,cancelled=()=>false}) {
  let clips,core;
  try {
    const expected=Object.fromEntries(Object.entries(metadata.clips).map(([key,value])=>[key,value.frames]));
    clips=await decodeWhaleClips({character,recover,rise,hold,reveal},cancelled,globalThis.ImageDecoder,expected);
    const bytes=Uint8Array.from(atob(waterCore.split(',')[1]),c=>c.charCodeAt(0));
    core=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
    if(cancelled())throw Error('Reading retreat unmounted');
    const shared={...clips,reading};
    return {
      durations:Object.fromEntries(Object.entries(shared).map(([key,value])=>[key,value.durations])),
      drawCharacter(context,timeline){
        const sample=timeline.sample();context.clearRect(0,0,512,512);
        context.drawImage(shared[sample.character.clip].frames[sample.character.frame],0,0);
      },
      drawMagic(context,timeline){drawWater(context,shared,timeline,metadata,core);},
      dispose(){closeWhaleClips(clips);core.close();},
    };
  } catch(error) {closeWhaleClips(clips);core?.close();throw error;}
}
