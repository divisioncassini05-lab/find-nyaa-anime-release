import {frameAt,sum} from './whale-retreat-timeline.mjs';
const ease=t=>{t=Math.min(1,Math.max(0,t));return t*t*(3-2*t);};
function mix(ctx,a,b,t,x,y,size){
 ctx.save();ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1-t;ctx.drawImage(a,x,y,size,size);
 ctx.globalCompositeOperation='lighter';ctx.globalAlpha=t;ctx.drawImage(b,x,y,size,size);ctx.restore();
}
let buffer;
export function drawWater(ctx,clips,timeline,manifest,core){
 const s=timeline.stage,t=timeline.elapsed;
 if(!['rise','covered','reveal'].includes(s))return;
 const key={rise:'rise',covered:'hold',reveal:'reveal'}[s],clip=clips[key];
 const f=frameAt(clip.durations,t),begin=clip.durations.slice(0,f).reduce((a,b)=>a+b,0);
 const local=t%sum(clip.durations)-begin;
 let previous=clip.frames[Math.max(0,f-1)],current=clip.frames[f];
 if(s==='covered'&&f===0)previous=t<sum(clip.durations)?clips.rise.frames.at(-1):clip.frames.at(-1);
 if(s==='reveal'&&f===0)previous=clips.hold.frames[frameAt(clips.hold.durations,timeline.durations.covered-1)];
 const blend=ease(local/Math.min(130,clip.durations[f]));
 const coreOpacity=s==='covered'?1:s==='rise'?ease((t-950)/550):1-ease(t/500);
 if(coreOpacity>0){ctx.save();ctx.globalAlpha=coreOpacity;ctx.drawImage(core,manifest.effect_origin,manifest.effect_origin,manifest.effect_size,manifest.effect_size);ctx.restore();}
 buffer??=new OffscreenCanvas(768,768);const b=buffer.getContext('2d');b.clearRect(0,0,768,768);
 mix(b,previous,current,blend,manifest.effect_origin,manifest.effect_origin,manifest.effect_size);
 ctx.drawImage(buffer,0,0);
 // Only the effect eases in/out; the original reading cel is never cross-faded.
 const opacity=s==='rise'?ease(t/180):s==='reveal'?1-ease((t-(timeline.durations.reveal-450))/450):1;
 if(opacity<1){ctx.save();ctx.globalCompositeOperation='destination-in';ctx.fillStyle=`rgba(0,0,0,${opacity})`;ctx.fillRect(0,0,768,768);ctx.restore();}
}
