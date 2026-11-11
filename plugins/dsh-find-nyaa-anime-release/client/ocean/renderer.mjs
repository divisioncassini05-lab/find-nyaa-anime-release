import { clamp } from './faunaMotion.mjs';

export function frameAt(meta, seconds) {
  let position = ((seconds * 1000) % meta.duration_ms + meta.duration_ms) % meta.duration_ms;
  for (let i = 0; i < meta.durations.length; i++) { position -= meta.durations[i]; if (position < 0) return i; }
  return meta.frames - 1;
}
export function spriteKey(a) { return a.part === null ? a.variant : `${a.variant}-${a.part}`; }
export async function loadSprites(manifest) {
  const result = new Map();
  for (const [id, meta] of Object.entries(manifest.sprites)) {
    const image = new Image(); image.src = meta.atlas;
    await image.decode(); result.set(id, { ...meta, image });
  }
  return result;
}
export function drawSprite(ctx, meta, frame, x, y, size, { mirror = false, angle = 0, glow = false, alpha = 1, id = '' } = {}) {
  const cell = meta.cell, dimension = size * cell / meta.visible_width;
  const sx = frame % meta.columns * cell, sy = Math.floor(frame / meta.columns) * cell;
  ctx.save(); ctx.translate(x, y); ctx.rotate(angle); ctx.scale(mirror ? -1 : 1, 1); ctx.globalAlpha = alpha;
  if (glow) drawEmission(ctx, meta, frame, dimension, id);
  ctx.drawImage(meta.image, sx, sy, cell, cell, -dimension/2, -dimension/2, dimension, dimension);
  ctx.restore();
}
// Independent emission layer; a future nearby character can consume the same light anchor.
export function drawEmission(ctx, meta, frame, dimension, id) {
  ctx.save();
  if (id === 'anglerfish') {
    const anchor = meta.light_anchors?.[frame];
    if (anchor) {
      const x = (anchor[0]/meta.cell - .5)*dimension, y = (anchor[1]/meta.cell - .5)*dimension;
      const r = Math.max(8, dimension*.10), light = ctx.createRadialGradient(x,y,0,x,y,r);
      light.addColorStop(0,'rgba(255,232,153,.27)'); light.addColorStop(.30,'rgba(246,224,157,.12)'); light.addColorStop(1,'rgba(246,224,157,0)');
      ctx.fillStyle=light; ctx.fillRect(x-r,y-r,2*r,2*r);
    }
  } else {
    ctx.globalAlpha *= .20; ctx.shadowBlur = dimension * .12; ctx.shadowColor = id.includes('pandea') || id.includes('atolla') ? '#ee9bb1' : '#a2d8e7';
    ctx.drawImage(meta.image, frame%4*meta.cell,Math.floor(frame/4)*meta.cell,meta.cell,meta.cell,-dimension/2,-dimension/2,dimension,dimension);
  }
  ctx.restore();
}
export function drawWorld(canvas, world, sprites, { debug = false } = {}) {
  const ctx = canvas.getContext('2d');
  const ratio = canvas.width / world.width;
  ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,world.width,world.height);
  for (const a of [...world.animals].sort((a,b) => a.size-b.size)) {
    const meta = sprites.get(spriteKey(a)); if (!meta) continue;
    const upright = ['jelly','shelter','crawl'].includes(a.spec.style);
    const angle = upright ? 0 : clamp(Math.atan2(a.vy, Math.abs(a.vx)) * a.dir, -.24, .24);
    drawSprite(ctx,meta,frameAt(meta,a.age+a.phase),a.x,a.y,a.size,{ mirror:a.dir!==(meta.native_direction??1) && a.spec.style!=='jelly',angle,glow:world.theme==='night' && (a.spec.style==='jelly'||a.variant==='anglerfish'),id:a.variant });
    if (debug) {
      ctx.strokeStyle=a.fear>.15?'#ba7135':'#208b91';ctx.lineWidth=1;ctx.beginPath();ctx.arc(a.x,a.y,a.radius,0,Math.PI*2);ctx.stroke();
      ctx.font='12px sans-serif';ctx.fillStyle=world.theme==='night'?'#d7eeeb':'#163c45';ctx.fillText(`${a.spec.label} · ${a.state}`,a.x-a.radius,a.y-a.radius-10);
    }
  }
}

export class MotionClock {
  constructor(callback, { element = null } = {}) {
    this.callback=callback;this.running=true;this.visible=!document.hidden;this.intersecting=true;this.last=null;this.elapsed=0;this.handle=0;
    this.media=matchMedia('(prefers-reduced-motion: reduce)');this.reduced=this.media.matches;
    this.visibility=()=>{this.visible=!document.hidden;this.last=null;};
    this.preference=()=>{this.reduced=this.media.matches;this.last=null;};
    document.addEventListener('visibilitychange',this.visibility);this.media.addEventListener('change',this.preference);
    if(element){this.observer=new IntersectionObserver(entries=>{this.intersecting=entries[0].isIntersecting;this.last=null;});this.observer.observe(element);}
    const tick=now=>{const active=this.running&&this.visible&&this.intersecting&&!this.reduced;
      const dt=active&&this.last!==null?Math.min((now-this.last)/1000,.06):0;this.last=active?now:null;
      if(dt){this.elapsed+=dt;this.callback(dt,this.elapsed);}this.handle=requestAnimationFrame(tick);};
    this.handle=requestAnimationFrame(tick);
  }
  setRunning(value){this.running=Boolean(value);this.last=null;}
  dispose(){cancelAnimationFrame(this.handle);document.removeEventListener('visibilitychange',this.visibility);this.media.removeEventListener('change',this.preference);this.observer?.disconnect();}
}
