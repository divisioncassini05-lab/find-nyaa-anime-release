// Encounter weights are art direction, NOT measured wild population frequencies.
// Camouflage states and regional color morphs stay within natural palettes.
const variant = (id, weight = 100) => ({ id, weight });
const animal = (id, weight, movement, width, height, variants = [variant(id)], count = 1) =>
  ({ id, weight, movement, width, height, variants, count, kind: 'animal' });
const jelly = (id, weight, width, height) =>
  ({ ...animal(id, weight, 'pulse', width, height), kind: 'jelly' });

export const DAY_FAUNA = [
  animal('sardines', 30, 'school', 220, 108, [variant('fish-silver')], 3),
  animal('anchovies', 22, 'school', 220, 100, [variant('fish-jade')], 3),
  animal('clownfish', 14, 'swim', 150, 102, [variant('clownfish-orange', 90), variant('clownfish-black', 10)]),
  animal('butterflyfish', 10, 'swim', 140, 100),
  animal('porcupinefish', 7, 'hover', 220, 138),
  animal('blue-spotted-ray', 6, 'glide', 210, 110),
  animal('seahorse', 5, 'hover', 80, 132, [variant('seahorse-brown', 65), variant('seahorse-gold', 35)]),
  animal('octopus', 5, 'pulse', 150, 108, [variant('octopus-russet', 60), variant('octopus-sand', 40)]),
  { ...animal('whale', 1, 'glide', 140, 104, [variant('whale-easter-egg')]), fantasy: true },
];

export const DEEP_FAUNA = [
  animal('lanternfish', 60, 'school', 190, 95),
  animal('hatchetfish', 25, 'swim', 150, 104),
  animal('barreleye', 9, 'hover', 150, 104),
  animal('dumbo-octopus', 6, 'pulse', 115, 116),
];

export const JELLY_FAUNA = [
  jelly('jelly-solmissus', 40, 140, 108),
  jelly('jelly-atolla', 25, 90, 138),
  jelly('jelly-pandea', 18, 84, 138),
  jelly('jelly-crossota', 12, 112, 124),
  jelly('jelly-phantom', 5, 92, 140),
];

export const NIGHT_FAUNA = [
  ...DEEP_FAUNA.map((entry) => ({ ...entry, weight: entry.weight * .6 })),
  ...JELLY_FAUNA.map((entry) => ({ ...entry, weight: entry.weight * .4 })),
];

export function weightedPick(entries, random = Math.random) {
  const total = entries.reduce((sum, entry) => sum + entry.weight, 0);
  let cursor = Math.max(0, Math.min(1 - Number.EPSILON, random())) * total;
  for (const entry of entries) {
    cursor -= entry.weight;
    if (cursor < 0) return entry;
  }
  return entries.at(-1);
}

export function chooseEncounter(theme, random = Math.random) {
  const species = weightedPick(theme === 'night' ? NIGHT_FAUNA : DAY_FAUNA, random);
  const color = weightedPick(species.variants, random);
  const duration = { school: 26, swim: 32, glide: 38, hover: 44, pulse: 40 }[species.movement];
  return { ...species, variant: color.id, duration };
}
