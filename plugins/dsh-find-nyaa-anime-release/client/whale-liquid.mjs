import {traceWaterPose, TRACE_COVER} from './whale-trace-ink.mjs';

const clamp=t=>Math.max(0,Math.min(1,t));
const ease=t=>{t=clamp(t);return t*t*(3-2*t);};
const mix=(a,b,t)=>a+(b-a)*t;
const rgba=(rgb,a)=>`rgba(${rgb.map(Math.round).join(',')},${a})`;
const blend=(a,b,t)=>a.map((v,i)=>mix(v,b[i],t));

// The dark core spreads through the same liquid; it never swaps sprites.
export function inkState(ms){
  const tip=traceWaterPose(ms);
  const strength=ease(ms/180)*(1-ease((ms-4100)/400));
  return tip&&strength>0 ? {...tip,strength,ink:ease((ms-800)/1550)} : null;
}

function lens(ctx,x,y,rx,ry,angle,time,ink,alpha){
  if(alpha<=0||rx<=0)return;
  const edge=blend([55,137,167],[16,16,19],ink);
  const middle=blend([98,183,205],[27,27,30],ink);
  ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.globalAlpha=alpha;
  const w=.07*Math.sin(time/350);
  ctx.beginPath();ctx.moveTo(-rx*.24,-ry);
  ctx.bezierCurveTo(rx*.26,-ry*(1.05+w),rx*.93,-ry*.58,rx,ry*.04);
  ctx.bezierCurveTo(rx*1.08,ry*.76,rx*.32,ry*1.08,-rx*.15,ry*.72);
  ctx.bezierCurveTo(-rx*.39,ry*.52,-rx*.9,ry*.84,-rx,ry*.15);
  ctx.bezierCurveTo(-rx*1.04,-ry*.52,-rx*.69,-ry*.95,-rx*.24,-ry);
  const fill=ctx.createLinearGradient(-rx*.2,-ry,rx*.3,ry);
  fill.addColorStop(0,rgba(blend([194,236,243],[51,51,55],ink),.78));
  fill.addColorStop(.38,rgba(middle,mix(.46,.94,ink)));
  fill.addColorStop(.72,rgba(middle,mix(.5,.97,ink)));
  fill.addColorStop(1,rgba(edge,mix(.82,1,ink)));
  ctx.fillStyle=fill;ctx.fill();
  ctx.strokeStyle=rgba(edge,mix(.8,.9,ink));ctx.lineWidth=.7;ctx.stroke();
  ctx.beginPath();ctx.moveTo(-rx*.73,-ry*.28);
  ctx.bezierCurveTo(-rx*.48,-ry*.78,rx*.18,-ry*.75,rx*.48,-ry*.4);
  ctx.strokeStyle=rgba(blend([233,254,255],[69,69,73],ink),mix(.88,.24,ink));
  ctx.lineWidth=.9;ctx.lineCap='round';ctx.stroke();ctx.restore();
}

export function drawTraceLiquid(ctx,ms){
  const p=inkState(ms);if(!p)return;
  ctx.save();
  const specs=[[2,-2,6.3,3.8],[11,2,3.5,2.6],[-5,8,2.8,2.2]];
  for(let i=0;i<specs.length;i++){
    const [dx,dy,rx,ry]=specs[i];
    const a=.15*Math.sin(ms/440+i),x=p.x+dx+.6*Math.sin(ms/380+i),y=p.y+dy+.6*Math.cos(ms/460+i);
    lens(ctx,x,y,rx*p.strength,ry*p.strength,a,ms+i*190,p.ink,p.strength);
    // Local pigmentation trails the main body, rather than a global colour flash.
    if(p.ink>.03&&p.ink<.98){
      lens(ctx,x+rx*.13,y+ry*.17,rx*.68*p.ink,ry*.63*p.ink,a,ms,1,p.ink*.65*p.strength);
    }
  }
  if(p.behindBook){
    ctx.globalCompositeOperation='destination-out';ctx.fillStyle='#000';ctx.beginPath();
    TRACE_COVER.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.fill();
  }
  ctx.restore();
}

export function palmAt(spec,ms){
  let i=0,t=ms;while(i<spec.durations.length-1&&t>=spec.durations[i])t-=spec.durations[i++];
  return {index:i,x:spec.palms[i][0],y:spec.palms[i][1]};
}

function ribbon(ctx,from,to,progress,time,width,alpha){
  if(progress<=0||alpha<=0)return;
  const p=ease(progress),x=mix(from.x,to.x,p),y=mix(from.y,to.y,p);
  const curl=12*Math.sin(time/540),bend=(from.x+x)/2+curl;
  ctx.save();ctx.globalAlpha=alpha;
  ctx.beginPath();ctx.moveTo(from.x-2,from.y);
  ctx.bezierCurveTo(bend-20,from.y-20,x-width,y+18,x,y);
  ctx.bezierCurveTo(x+width,y+18,bend-13,from.y-19,from.x+2,from.y);
  const g=ctx.createLinearGradient(from.x,from.y,x,y);
  g.addColorStop(0,'rgba(115,206,216,.04)');g.addColorStop(.45,'rgba(83,174,198,.25)');g.addColorStop(1,'rgba(169,231,237,.45)');
  ctx.fillStyle=g;ctx.fill();
  ctx.beginPath();ctx.moveTo(from.x,from.y);ctx.bezierCurveTo(bend-17,from.y-20,x-1,y+18,x,y);
  ctx.strokeStyle='rgba(182,239,245,.76)';ctx.lineWidth=1.3;ctx.lineCap='round';ctx.stroke();
  ctx.restore();
}

export function palmLiquidState(spec,ms){
  const total=spec.durations.reduce((a,b)=>a+b,0);
  if(ms<80||ms>=4700||ms>=total)return null;
  const palm=palmAt(spec,ms),birth=ease((ms-80)/570),drain=ease((ms-4110)/590);
  const play=ease((ms-600)/400)*(1-ease((ms-3900)/300));
  const phase=(ms-600)/720,reach=Math.sin(phase)*play;
  return {palm,birth,drain,play,strength:birth*(1-drain),
    x:palm.x+4+reach*10,y:palm.y-16-(.5+.5*Math.sin(phase*.8))*9*play,
    rx:18+4*Math.sin(phase)*play,ry:10-2*Math.sin(phase)*play,
    angle:-.22+.18*Math.sin(phase*.7)*play};
}

export function drawPalmLiquid(ctx,spec,ms){
  const p=palmLiquidState(spec,ms);if(!p)return;
  const {x,y,rx,ry,strength:s,play,drain,birth,angle}=p;
  const seat={x:337,y:396},body={x,y};
  ctx.save();
  // A narrow branch lifts from the seat; only the local liquid remains while playing.
  if(ms<1050)ribbon(ctx,seat,body,(ms-80)/570,ms,4,.8*(1-ease((ms-650)/400)));
  if(drain>0)ribbon(ctx,body,seat,drain,ms,3,(1-drain)*.75);
  const lift=ease((birth-.18)/.82)*(1-drain);
  lens(ctx,x,y,rx*lift,ry*lift,angle,ms,0,.92*s);
  // A bead stretches out from a liquid neck, separates, then merges back.
  const excursion=(1-Math.cos((ms-650)/460))* .5*play;
  const bx=x+17+excursion*15,by=y-2-excursion*8;
  if(play>0){
    const neck=1-ease((excursion-.1)/.55);
    ctx.beginPath();ctx.moveTo(x+rx*.55,y);
    ctx.bezierCurveTo(x+rx+5,y+4,bx-6,by+3,bx,by);
    ctx.strokeStyle=`rgba(132,217,229,${neck*.6*play})`;ctx.lineWidth=2.2*neck;ctx.stroke();
    lens(ctx,bx,by,(3.1+1.4*excursion)*play,3.1*play,-.3,ms+200,0,.85*s);
  }
  // A small flow crease travels through the body without moving the character.
  if(lift>.1){
    ctx.save();ctx.translate(x,y);ctx.rotate(angle);ctx.beginPath();
    const shift=Math.sin(ms/440)*rx*.2;
    ctx.moveTo(-rx*.35+shift,ry*.1);ctx.quadraticCurveTo(shift,ry*.36,rx*.42+shift,ry*.06);
    ctx.strokeStyle=`rgba(220,251,254,${.38*s})`;ctx.lineWidth=.65;ctx.stroke();ctx.restore();
  }
  ctx.restore();
}
