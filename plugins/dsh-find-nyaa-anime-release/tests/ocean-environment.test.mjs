import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { OceanWorld } from '../client/ocean/faunaMotion.mjs';
import { WaterAtmosphere } from '../client/ocean/waterAtmosphere.mjs';
import { seedAmbient, floorFit } from '../client/ocean/scene.mjs';

test('floor effects share the existing bottom-right painting anchors at every width', () => {
  for (const [width,height] of [[1440,900],[780,720],[390,720]]) {
    const fit = floorFit(width,height);
    assert.equal(fit.x + 1536 * fit.scale, width);
    assert.equal(fit.y + 1024 * fit.scale, height);
    assert.equal(1536 * fit.scale, Math.max(width,780));
  }
});
test('DSH starts with the reviewed day/night populations', () => {
  for (const [width,day,night] of [[1440,36,22],[780,23,16],[390,17,11]]) for (const theme of ['day','night']) {
    const world = new OceanWorld({ width,height:900,theme,seed:22 });
    seedAmbient(world); assert.equal(world.animals.length, theme === 'day' ? day : night);
    for (const animal of world.animals) assert.equal(animal.spec.theme,theme);
    world.step(.016); assert.ok(world.animals.length > 0);
  }
});
test('seabed root positions use the unchanged floor fit, not viewport cover', () => {
  const water = new WaterAtmosphere({ width:390,height:720 });
  water.details.fit = floorFit(390,720);
  const first = water.frame(0), next = water.frame(12);
  assert.deepEqual(first.seaweed.map(p => p.spine[0]), next.seaweed.map(p => p.spine[0]));
  assert.notDeepEqual(first.seaweed.map(p => p.spine.at(-1)), next.seaweed.map(p => p.spine.at(-1)));
});
test('environment stays trapped below existing summoned fish and actor stacking contexts', () => {
  const css = fs.readFileSync(fileURLToPath(new URL('../client/oceanAmbient.css', import.meta.url)),'utf8');
  assert.match(css,/\.anime-panel \.anime-ocean \{ isolation:isolate/);
  assert.match(css,/\.anime-environment \{[^}]*z-index:0;[^}]*isolation:isolate/);
  assert.doesNotMatch(css,/anime-summoned-fish|anime-whale|anime-current-rest/);
  const component = fs.readFileSync(fileURLToPath(new URL('../client/AmbientOcean.jsx', import.meta.url)),'utf8');
  assert.match(component,/aria-hidden="true" inert=""/);
  assert.doesNotMatch(component,/rpc|bangumi|qbittorrent|fetch\(/i);
});
