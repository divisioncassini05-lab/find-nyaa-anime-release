export const LIQUID_SIZE = 512;

export function createLiquidCanvas() {
  return document.createElement('canvas');
}

export function liquidCanvas(createCanvas) {
  const canvas = createCanvas();
  canvas.width = canvas.height = LIQUID_SIZE;
  if (!canvas.getContext('2d')) throw new Error('Liquid canvas unavailable');
  return canvas;
}

export function releaseCanvases(canvases) {
  for (const canvas of canvases) canvas.width = canvas.height = 0;
}

export function polygon(ctx, points) {
  ctx.beginPath();
  points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.closePath();
}

// Masks contain only alpha silhouettes, never replacement character pixels.
export function buildLiquidMasks(clip, covers, createCanvas) {
  const masks = [];
  try {
    for (let i = 0; i < clip.frames.length; i++) {
      const canvas = liquidCanvas(createCanvas);
      masks.push(canvas);
      const ctx = canvas.getContext('2d', {willReadFrequently: true});
      ctx.drawImage(clip.frames[i], 0, 0);
      const [left, top, width, height] = covers ? [0, 0, 512, 512] : [220, 245, 155, 165];
      const pixels = ctx.getImageData(left, top, width, height);
      const data = pixels.data;
      for (let p = 0; p < data.length; p += 4) {
        const x = left + (p / 4) % width, y = top + Math.floor(p / 4 / width);
        const skin = data[p] > 150 && data[p] - data[p + 1] > 9 && data[p + 1] - data[p + 2] > 2;
        const inBounds = !covers || (x > 224 && x < 349 && y > 226 && y < 314);
        if (!skin || !inBounds) data[p + 3] = 0;
      }
      ctx.clearRect(0, 0, 512, 512);
      ctx.putImageData(pixels, left, top);
      if (covers) {
        ctx.fillStyle = '#000';
        polygon(ctx, covers[i]);
        ctx.fill();
      }
    }
    return masks;
  } catch (error) {
    releaseCanvases(masks);
    throw error;
  }
}
