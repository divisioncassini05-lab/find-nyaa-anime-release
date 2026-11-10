const ease=t=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t);};
// Tip landmarks belong to the decoded candidate, not to a guessed page location.
export const TRACE_GIF_SHA256='9d716c5b86b44c8103267c09e2b83e388001885b1016b56bc2de22c54baf9c5f';
export const TRACE_TIPS=[
 [280,338],[291,316],[306,282],[302,270],[300,265],[287,257],[280,252],[279,252],
 [280,254],[267,257],[257,262],[252,264],[251,268],[250,268],[251,269],[253,269],
 [258,260],[257,261],[257,261],[257,261],[257,261],[258,261],[256,261],[248,262],
 [250,261],[251,261],[257,260],[259,260],[258,260],[258,260],[257,260],[257,261],
 [255,263],[265,258],[268,261],[267,271],[268,279],[278,287],[299,307],[295,338],
 [285,348],[278,352],[272,355],[273,355],[265,352],[264,351],[271,349],[269,337],
];
export const TRACE_DURATIONS=Array.from({length:48},(_,i)=>i<16||i>=32?80:i===31?190:150);
export const TRACE_COVER=[[169,277],[236,291],[301,276],[302,349],[236,355],[178,349]];
export const TRACE_INK={edge:'#101012',body:'#1b1b1e',soft:'#353538'};
export function traceWaterPose(ms){
 if(ms<0||ms>=5000)return null;
 let frame=0,t=ms;while(frame<47&&t>=TRACE_DURATIONS[frame])t-=TRACE_DURATIONS[frame++];
 const [x,y]=TRACE_TIPS[frame];
 return {x,y,frame,behindBook:frame>=3&&frame<=37};
}
export function traceDroplets(ms){
 const pose=traceWaterPose(ms);
 const strength=ease(ms/80)*(1-ease((ms-4020)/440));
 if(!pose||strength<=0)return[];
 return [[1,3,3.8],[10,-3,3.0],[-5,10,2.7]].map(([dx,dy,r],i)=>({
   x:pose.x+dx+.8*Math.sin(ms/360+i*1.8),
   y:pose.y+dy+.9*Math.sin(ms/430+i*1.4),
   radius:r*strength,alpha:.96*strength,behindBook:pose.behindBook,
 }));
}

export function drawTraceInk(ctx,ms){
 ctx.save();
 for(const {x,y,radius:r,alpha} of traceDroplets(ms)){
   if(r<.1)continue;
   ctx.globalAlpha=alpha;
   const gradient=ctx.createLinearGradient(x-r,y-r,x+r,y+r);
   gradient.addColorStop(0,TRACE_INK.soft);
   gradient.addColorStop(.55,TRACE_INK.body);
   gradient.addColorStop(1,TRACE_INK.edge);
   const sway=.16*Math.sin(ms/330+x);
   ctx.beginPath();ctx.moveTo(x-r*.1,y-r*(1.1+sway));
   ctx.bezierCurveTo(x+r*1.4,y-r*.5,x+r,y+r*1.1,x-r*.1,y+r);
   ctx.bezierCurveTo(x-r*1.25,y+r*.85,x-r,y-r*.6,x-r*.1,y-r*(1.1+sway));
   ctx.fillStyle=gradient;ctx.fill();
 }
 // Ink goes behind the near cover with the hand, not over the whale emblem.
 if(traceWaterPose(ms)?.behindBook){
   ctx.globalAlpha=1;ctx.globalCompositeOperation='destination-out';ctx.fillStyle='#000';ctx.beginPath();
   TRACE_COVER.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();
 }
 ctx.restore();
}
