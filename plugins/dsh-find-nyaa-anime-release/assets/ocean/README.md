# Ocean artwork

Generated bitmap decorations for the DSH dashboard:

- `water-light.webp`: daylight painting, with overhead water, an open center and
  a low asymmetric seabed. Pearl aqua, jade grass, lavender rocks and muted coral.
- `water-dark.webp`: moonlit color-and-light edit of the daylight master. The
  viewpoint, terrain, rocks, grasses and coral retain the same composition;
  this is not a separately invented landscape or an inverted image.
- `carved-starfish.webp`: transparent hand-carved starfish illustration, guided by
  user-provided CLANNAD prop references. It is a static decorative accent.

The environment borrows an anime background-painting direction from Nagi no
Asukara and Goodbye, Lara. No anime screenshots or city buildings are included.
The separate project mascot is documented in `whale/README.md`. Generated artwork is not official
artwork or an affiliation claim. The client embeds these files as data URLs so
they also work in DSH's virtual module loader without additional asset routes.

## Background revision (2026-11-10)

Both backgrounds were created with the built-in image generation tool, then
encoded to WebP without resizing, cropping or color processing. Each is 1536 x
1024. The original layered, hand-painted anime direction is retained.

Prompt brief: clear underwater daylight; graceful surface ripples at the top;
quiet central water for the application; a low sandy seabed with pale rocks,
slender grasses and restrained coral at the edges; no buildings, characters,
text, painted bubbles or additional starfish. Night edit: change only light and
color to silver-aqua moonlight and deep petrol-teal water; preserve all terrain
and object placement from the daylight master.

The client uses each painting twice, masked at the top and bottom of the panel,
over a quiet theme-specific depth color. Both themes share identical geometry.
This preserves the water surface and seabed in wide and narrow windows without
stretching the art. Independent light and ambient overlays can move; the terrain
does not drift. Mascot, current ribbon and carved starfish are separate.

## Ambient overlays (2026-11-10)

`overlays/` contains resized WebP versions of the transparent generated PNG
masters in `design/ocean-overlays-v1/` at the repository root. These are separate
layers; neither terrain painting is modified. All overlays are embedded by the
existing client bundler, with no remote asset requests or new host APIs.

- Day: one school (at most three small fish) or one larger animal. The current
  pool includes sardine- and anchovy-inspired schools, clownfish, butterflyfish,
  porcupinefish, a blue-spotted ray, seahorses and an octopus. A rare whale cameo
  replaces the encounter, never adds to it.
- Night: one deep-water animal OR one jellyfish. Lanternfish, hatchetfish,
  barreleye and dumbo octopus share the pool with five distinct jellyfish designs.
  They do not all appear together.
- Both themes: one faint bubble trail and sparse current traces. Narrow windows
  clip the bubble trail to three bubbles. The current traces are separate from
  the existing seat ribbon; the ribbon and girl are unchanged.

`JellyfishLight` is a reusable, self-contained luminous sprite. Its blurred,
masked duplicate brightens the bell locally; it does not darken the page, recolor
the girl, or run a light-interaction system. The glow remains when motion is off,
while the small breathing variation stops. `--ap-ambient-play` controls animation
and defaults to paused when the component is used outside the ocean scene.

## Fauna expansion (2026-11-11)

New transparent masters and their generator manifest are in
`design/ocean-fauna-v2/` at the repository root. See its README for source links,
prompt briefs, design weights and the distinction between natural color morphs
and camouflage states. The style remains soft, simplified anime illustration,
not photographic marine imagery. Existing silver/jade schools are reused.

`client/oceanFauna.mjs` owns the separate species and color weights. These are
design probabilities, not biological abundance statistics. Clownfish orange/black,
seahorse brown/gold and octopus russet/sand are independent generated textures;
there is no arbitrary runtime hue filter. Day/shallow and night/deep is a playful
visual convention, not a claim that all these animals coexist in one habitat.

Each encounter crosses an uncluttered header lane in 26-44 seconds, with gentle
school, swimming, gliding, hovering or pulsing motion. Once it has faded out,
the animation-end event selects the next encounter. This is sprite translation
and light deformation, not an articulated skeletal or frame-by-frame animation.
Inactive themes pause. Static mode keeps one centered, motionless encounter.
The faint bubbles and currents, terrain, mascot and seat ribbon are unchanged.

All decoration is pointer-transparent and hidden from accessibility. The existing
motion preference, reduced-motion setting, document visibility and intersection
observer pause its animation. Only transform and opacity animate; no timers,
canvas loops, tracking state, network requests or layout updates are introduced.
