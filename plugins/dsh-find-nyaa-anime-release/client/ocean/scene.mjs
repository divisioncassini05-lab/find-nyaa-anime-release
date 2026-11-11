// The DSH panel anchors the full-size floor painting at its bottom-right edge.
export function floorFit(width, height) {
  const scale = Math.max(width, 780) / 1536;
  return { scale, x:width - 1536 * scale, y:height - 1024 * scale };
}

export function seedAmbient(world) {
  const { width, height, theme } = world;
  const compact = width <= 600, medium = width < 1000;
  const put = (id, options) => world.spawn(id, options);
  if (theme === 'day') {
    put('sardines', {x:width * (compact ? .78 : .58), y:height * .36, dir:1, count:compact ? 8 : 10});
    put('anchovies', {x:width * (compact ? .25 : .42), y:height * .53, dir:-1, count:compact ? 6 : medium ? 9 : 10});
    if (!medium) put('sardines', {x:width * .88, y:height * .62, dir:1, count:9});
    put('clownfish', {x:width * .78, y:height * .66, dir:-1, count:1});
    put('butterflyfish', {x:width * .25, y:height * .72, dir:1});
    put('blue-spotted-ray', {x:width * .70, y:height * .87, dir:-1});
    if (!compact) put('seahorse', {x:width * .16, y:height * .86, dir:1});
    if (!medium) {
      put('clownfish', {variant:'clownfish-black', x:width * .62, y:height * .78, dir:-1, count:1});
      put('porcupinefish', {x:width * .43, y:height * .66, dir:1});
      put('octopus', {x:width * .44, y:height * .88, dir:1});
    }
  } else {
    put('lanternfish', {x:width * (compact ? .82 : .50), y:height * .42, dir:1, count:compact ? 5 : 6});
    put('lanternfish', {x:width * (compact ? .22 : .64), y:height * .66, dir:-1, count:compact ? 3 : medium ? 5 : 6});
    if (!medium) put('lanternfish', {x:width * .86, y:height * .74, dir:1, count:4});
    put('hatchetfish', {x:width * .87, y:height * .57, dir:-1});
    put('barreleye', {x:width * .30, y:height * .78, dir:1});
    put('jelly-solmissus', {x:width * .18, y:height * .60, dir:1});
    if (!compact) {
      put('dumbo-octopus', {x:width * .83, y:height * .83, dir:-1});
      put('jelly-crossota', {x:width * .68, y:height * .35, dir:-1});
    }
    if (!medium) put('hatchetfish', {x:width * .56, y:height * .64, dir:1});
  }
  world.nextSpawn = 3;
}
