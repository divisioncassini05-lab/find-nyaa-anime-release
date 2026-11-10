# Ambient gestures

Five gestures accepted for integration on 2026-11-10; the complete fingertip
gesture and two independent native water effects were accepted on 2026-11-11.
The GIFs retain the
reviewed 512x512 origin and are displayed at 150px / 132px with no recentering.
The original four master GIFs remain byte-identical in the parent directory.

- Idle: alternating feet, sleeve adjustment, playing with water.
- Reading: tracing the page, resting her chin while thinking.
- The book layer runs on a continuous clock during idle gestures.
- Water and blue-to-black ink are separate native animated textures projected
  onto a curved surface. The near book cover and fingertip occlude the ink;
  palm silhouettes and a contact shade establish front/back depth for water.
- The scheduler waits 25-45 seconds of stable playback, then a full parent loop.
  Reading gestures therefore never interrupt a page turn. A started gesture
  finishes before a mode request; requests do not queue multiple gestures.
- Hidden/offscreen/reduced-motion playback freezes the same clocks. Only one
  ambient clip is retained decoded alongside the base clips, limiting memory.

The manifest records selected hashes and concise production provenance, not
private generation logs or machine paths. Slight redrawn contour differences
remain in the sleeve/chin gestures; do not describe them as pixel-identical.
This release does not connect experimental searching, fish, or feedback assets
to business events. The character remains visual-only.

## Native Liquid Contract

`reading-trace.gif` is the accepted 24-frame, 4100ms action, SHA-256
`401ecada2d6cec385bbc7bdd8ff635d72706536a1c6d207abc06fb203fa1061d`.
The exact decoded holds are recorded in `manifest.json` and `arm-manifest.json`.
`arm-manifest.json` contains 24 matching tips and cover polygons, with ink active
from 500ms through 2050ms (exclusive). Do not reuse the old 48-frame shared mask,
constant book polygon, or evenly distributed frame timings.

`ink-study.gif` and `palm-study.gif` retain their native bytes: each has 16 frames
of 140ms, 2240ms total. The renderer maps the full blue-to-black ink texture to
the active fingertip interval and plays two palm cycles with the accepted soft
end gates. This is not a claim of a seamless native loop or interpolated frames.
`manifest.liquid.effects` records their hashes, timings and motion metadata.
The existing `palm-motion.json` and `idle-droplet.gif` are unchanged.

The host entry point is `client/whale-native-liquid.mjs`. It imports bundled
assets and metadata and delegates to `client/whale-liquid-depth.mjs` and
`client/whale-liquid-mask.mjs`. The historical `whale-liquid.mjs` remains for
legacy callers/tests, but is not the renderer for these accepted assets.

```js
const liquids = createNativeLiquid({cancelled: () => disposed});
await liquids.load(id, characterClip);
liquids.draw(context, id, timeline.elapsed, timeline.frame);
liquids.dispose();
```

`load` accepts every ambient ID. Non-water IDs release old masks and water
frames without decoding anything. Water loads replace their cache only after
decoding and mask creation succeed. Failed, cancelled or superseded loads
close their newly decoded water frames; failed loads leave the prior cache
usable. `dispose` also cancels in-flight loads, is idempotent, and closes owned
water frames. The wrapper never closes caller-owned character frames. The host
must close a newly decoded character clip if its preparation fails, and may
close the previous character clip after `load` succeeds. `draw` composites onto
the character canvas without clearing it or changing its clock.

The following lower-level API remains available for callers owning water frames:

```js
const state = buildContext();
loadAction(state, id, {
  character: {...clips[id], sha256: ambient.actions[id].sha256},
  liquid: decodedWaterClip,
  landmarks: arm.landmarks,
  palms: palm,
});
draw(state, fx, id, timeline.elapsed, timeline.frame);
```

- Import `buildContext`, `loadAction`, `draw`, `releaseAction`, `disposeContext`
  from the module. Import the two GIFs through the same bundler as character
  assets, then decode with the existing `decodeWhaleClips` (expected count 16).
- `loadAction` is synchronous, supports only `reading-trace`/`idle-droplet`,
  accepts decoded `{frames, durations}` clips, and replaces the single mask
  cache. Invoke after successful decoding, before marking the action ready,
  and never replace the cache while its previous action is still playing.
- `landmarks` is `arm.landmarks`; `palms` is the existing palm-motion object.
  Pass the character manifest's `sha256` as above to enforce identity binding.
  Decoded dimensions, timings, anchors and cover counts are always validated.
- Draw after the character/book, on the caller's cleared 512x512 effect canvas.
  `draw` does not clear the target, fetch assets, schedule frames, or advance
  clocks. It returns false outside the active effect; mismatched frame/time
  arguments throw. Omitting `frame` derives it from the same elapsed time.
- `releaseAction(state)` drops masks and clip references. `disposeContext(state)`
  also releases scratch surfaces and is idempotent. Neither closes decoded
  frames; the host must close its effect clips on eviction, cancellation,
  failed preparation and unmount. Do not change parent/book clock ownership.

## Verification

`node --test tests/whale-liquid.test.mjs` checks hashes, exact metadata binding,
frame boundaries, perspective, validation, deterministic timing and cleanup.
`node tools/check_whale_liquid_ui.mjs` decodes real GIFs in Chromium and checks
occlusion, changing texture pixels, caller-canvas preservation, repeat draws,
and 150px/132px screenshots in light/dark backgrounds. It starts a temporary
loopback server and closes it on completion; outputs go under ignored
`.preview/liquid/`. Set `PLAYWRIGHT_NODE_MODULES`/`PLAYWRIGHT_CHANNEL` if needed.
An optional `WHALE_LIQUID_REFERENCE` directory enables pixel comparison against
the accepted depth/study player modules without copying them into public code.

This asset/module handoff does not edit the host component or build artifacts.
The host must switch to the new API before shipping the new fingertip asset;
legacy procedural ink coordinates do not match it. Build/package and full host
lifecycle verification belong to that final integration step.
