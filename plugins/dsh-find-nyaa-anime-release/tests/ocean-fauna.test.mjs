import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { DAY_FAUNA, DEEP_FAUNA, JELLY_FAUNA, NIGHT_FAUNA, weightedPick, chooseEncounter } from '../client/oceanFauna.mjs';

test('fauna pools stay sparse, distinct and locally packaged', () => {
  assert.equal(DAY_FAUNA.filter((s) => !s.fantasy).length + DEEP_FAUNA.length, 12);
  assert.equal(JELLY_FAUNA.length, 5);
  for (const pool of [DAY_FAUNA, NIGHT_FAUNA, DEEP_FAUNA, JELLY_FAUNA]) {
    assert.ok(Math.abs(pool.reduce((sum, s) => sum + s.weight, 0) - 100) < 1e-9);
    assert.equal(new Set(pool.map((s) => s.id)).size, pool.length);
    for (const s of pool) {
      assert.ok(s.count >= 1 && s.count <= 3);
      for (const v of s.variants) {
        assert.ok(v.weight > 0);
        assert.ok(fs.statSync(new URL(`../assets/ocean/overlays/${v.id}.webp`, import.meta.url)).size > 100);
      }
    }
  }
  assert.ok(DAY_FAUNA.find((s) => s.id === 'whale').weight < DAY_FAUNA.find((s) => s.id === 'seahorse').weight);
  assert.ok(JELLY_FAUNA.find((s) => s.id === 'jelly-phantom').weight < JELLY_FAUNA.find((s) => s.id === 'jelly-solmissus').weight);
});

test('natural color variants are selected independently from the species', () => {
  const pick = (species, color) => {
    const values = [species, color];
    return chooseEncounter('day', () => values.shift());
  };
  assert.equal(pick(.6, .1).variant, 'clownfish-orange');
  assert.equal(pick(.6, .95).variant, 'clownfish-black');
  assert.equal(pick(.9, .2).variant, 'seahorse-brown');
  assert.equal(pick(.9, .9).variant, 'seahorse-gold');
  assert.equal(pick(.96, .2).variant, 'octopus-russet');
  assert.equal(pick(.96, .8).variant, 'octopus-sand');
});

test('weighted boundaries cover all entries without adding multiple encounters', () => {
  assert.equal(weightedPick(DAY_FAUNA, () => 0).id, 'sardines');
  assert.equal(weightedPick(DAY_FAUNA, () => 1).id, 'whale');
  for (const pool of [DAY_FAUNA, NIGHT_FAUNA]) {
    let start = 0;
    for (const entry of pool) {
      assert.equal(weightedPick(pool, () => (start + entry.weight / 2) / 100).id, entry.id);
      start += entry.weight;
    }
  }
  assert.equal(chooseEncounter('night', () => .7).kind, 'jelly');
  assert.equal(chooseEncounter('night', () => .1).kind, 'animal');
  assert.ok(chooseEncounter('day', () => .1).duration >= 20);
});
