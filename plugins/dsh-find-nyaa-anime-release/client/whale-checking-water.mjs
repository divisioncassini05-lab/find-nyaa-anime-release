import {frameAt,total} from './whale-checking-fish.mjs';

// A fixed registration affects only the generated effect, never the character.
export const registration={scaleX:.78,scaleY:.76,x:116,y:85};
export function waterFrame(clip,age,duration) {
  if(age<0||age>=duration)return -1;
  return frameAt(clip.durations,age/duration*total(clip.durations),false);
}
export function drawWaterGif(ctx,clip,age,duration) {
  const frame=waterFrame(clip,age,duration);
  if(frame<0)return;
  const fade=Math.min(1,age/150,(duration-age)/180);
  ctx.save();ctx.globalAlpha=Math.max(0,fade);
  ctx.translate(registration.x,registration.y);
  ctx.scale(registration.scaleX,registration.scaleY);
  ctx.drawImage(clip.frames[frame],0,0);ctx.restore();
}

const smooth=value=>{const t=Math.max(0,Math.min(1,value));return t*t*(3-2*t);};

export function drawDeparture(ctx,item,now) {
  const age=(now-item.swimAt)/1000;if(age<0||age>1.3)return;
  const opacity=(1-smooth(age/1.3))*.5;
  ctx.save();ctx.translate(item.x,item.y);ctx.rotate(item.angle);ctx.globalAlpha=opacity;
  for(let i=0;i<3;i++) {
    ctx.beginPath();ctx.ellipse(-item.size*(.37+age*.08+i*.05),Math.sin(age*5+i*1.5)*1.8,.7,1.0,0,0,Math.PI*2);
    ctx.fillStyle='#8edbd6';ctx.fill();
  }
  ctx.restore();
}
