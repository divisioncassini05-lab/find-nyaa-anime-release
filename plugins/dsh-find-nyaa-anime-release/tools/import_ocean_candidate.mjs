import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const source = path.resolve(process.argv[2] || '');
if (!process.argv[2]) throw new Error('Pass the reviewed candidate directory.');
const manifest = JSON.parse(fs.readFileSync(path.join(source, 'manifest.json'), 'utf8'));
const target = path.join(root, 'assets/ocean/living');
fs.mkdirSync(target, { recursive:true });
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const imports = [], sprites = {}, files = [];
function asset(relative, variable) {
  const name = path.basename(relative);
  if (!/^[-a-z0-9]+\.(webp|png)$/.test(name)) throw new Error('Unexpected asset name.');
  const input = path.join(source, relative), output = path.join(target, name);
  const bytes = fs.readFileSync(input);
  fs.copyFileSync(input, output);
  files.push({ file:name, sha256:hash(bytes), bytes:bytes.length });
  imports.push(`import ${variable} from '../../assets/ocean/living/${name}';`);
  return variable;
}
for (const [id, meta] of Object.entries(manifest.sprites)) {
  const variable = asset(meta.atlas, `sprite${Object.keys(sprites).length}`);
  const { cell, columns, frames, durations, duration_ms, visible_width, visible_height, native_direction, light_anchors } = meta;
  sprites[id] = { cell, columns, frames, durations, duration_ms, visible_width, visible_height, native_direction, light_anchors, atlas:variable };
}
const environments = {};
for (const [name, meta] of Object.entries(manifest.environment_assets)) {
  environments[name] = { asset:asset(meta.asset, `environment${name}`) };
}
let serialized = JSON.stringify({ clips:Object.fromEntries(Object.keys(manifest.clips).map(id => [id, {}])), sprites, environment_assets:environments }, null, 2);
for (const entry of [...Object.values(sprites).map(m => m.atlas), ...Object.values(environments).map(m => m.asset)]) serialized = serialized.replaceAll(`"${entry}"`, entry);
fs.writeFileSync(path.join(root, 'client/ocean/assets.mjs'), `// Generated from the reviewed native-frame atlases; no profile data.\n${imports.join('\n')}\nexport const environmentManifest = ${serialized};\n`);
fs.writeFileSync(path.join(target, 'manifest.json'), JSON.stringify({ origin:'reviewed ocean-fauna-modules candidate', terrain_changed:false, native_frame_atlases:true, files }, null, 2) + '\n');
console.log(JSON.stringify({ imported:files.length, bytes:files.reduce((n,f) => n + f.bytes, 0) }));
