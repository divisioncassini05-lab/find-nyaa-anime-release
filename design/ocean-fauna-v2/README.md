# Anime ocean fauna, revision 2

Local preview artwork for the DSH panel, 2026-11-11. The user requested sparse
shallow-water encounters by day and playful deep-sea encounters at night. Real
species inform silhouettes and palettes only. The painting stays simplified,
soft and anime-like; no photorealistic scales, dense textures or horror treatment.

## Assets and generation

All 18 new PNGs were generated with the built-in image generation tool with
`transparent_background: true`. `manifest.json` maps each asset to its original
generated file. The existing daylight painting was a style reference only;
color variants used the corresponding base animal as an edit reference.
Deployable copies are encoded to WebP, longest side 512px, quality 86 and alpha
quality 100. No runtime hue shifts are used. Existing silver/jade schools and
the whale cameo come from `design/ocean-overlays-v1/`.

Common prompt direction: one isolated, complete marine sprite with generous
transparent margins; soft 2D Japanese animation, broad gentle cel shading,
delicate outlines and simplified silhouettes; no scenery, lettering, cast
shadow, heavy glow or scientific-plate texture. Match the existing underwater
background, not a nature photograph.

| Asset | Prompt-specific shape and palette |
| --- | --- |
| clownfish-orange | Orange ocellaris-inspired fish, three white bars, fine dark edging |
| clownfish-black | Same shape and white bars, charcoal natural morph, small orange snout tint |
| butterflyfish | Yellow longnose butterflyfish, black upper mask, white snout, small fin spot |
| porcupinefish | Compact cream/tan body, few round spots and short spines, friendly simplified shape |
| blue-spotted-ray | Pale olive disc, blue spots, long tail, gentle three-quarter gliding pose |
| seahorse-gold | White's-seahorse-inspired upright golden body and curled tail |
| seahorse-brown | Same pose, brown/gray-olive camouflage palette |
| octopus-russet | Gloomy-octopus-inspired russet mantle, cream underside, eight flowing arms |
| octopus-sand | Same pose, pale sand/taupe camouflage palette |
| lanternfish | Slender muted blue body and seven tiny cyan light points |
| hatchetfish | Pearl-blue hatchet belly, upward eye, restrained ventral light points |
| barreleye | Clear head dome with green tubular eyes, simplified small body |
| dumbo-octopus | Pale peach mantle, ear-like fins, eight-arm webbed skirt |
| jelly-solmissus | Flattened pale disc and slender radial tentacles |
| jelly-atolla | Muted ruby crown bell, one extended trailing tentacle |
| jelly-pandea | Coral-red folded paper-lantern bell and fine tentacles |
| jelly-crossota | Ruby center, purple radial channels, small orange nodes, many fine threads |
| jelly-phantom | Muted plum bell and four broad ribbon-like oral arms |

An earlier porcupinefish draft was rejected for overly dense, realistic texture.
The final listed version is the simplified redraw. Source animal details are
stylized rather than intended as a taxonomic identification guide.

## Encounter weights

These numbers are **art-direction choices, not measured wild frequencies**.
They make small schools familiar and unusual silhouettes occasional. The small
number of visible animals is a UI requirement, not a population model.

- Day: sardines 30%, anchovies 22%, clownfish 14%, butterflyfish 10%,
  porcupinefish 7%, ray 6%, seahorse 5%, octopus 5%, fantasy whale cameo 1%.
- Night chooses a deep-water animal 60% of the time and a jellyfish 40%.
- Within deep-water animals: lanternfish 60%, hatchetfish 25%, barreleye 9%,
  dumbo octopus 6%.
- Within jellyfish: Solmissus 40%, Atolla 25%, Pandea 18%, Crossota 12%,
  giant phantom-inspired jelly 5%.
- Clownfish variants: orange 90%, black 10%. Seahorse variants: brown 65%,
  gold 35%. Octopus variants: russet 60%, sand 40%.

Clownfish variants refer to natural color forms; seahorse and octopus palettes
are camouflage-inspired appearances, not separate subspecies. Jellyfish local
glow is a restrained artistic lighting choice, not a claim that each species
emits a constant visible halo in nature. No fish receives arbitrary recoloring.

## Reference sources

- [Florida Museum, clown anemonefish](https://www.floridamuseum.ufl.edu/discover-fish/species-profiles/clown-anemonefish/)
- [Animal Diversity Web, Amphiprion ocellaris](https://animaldiversity.org/accounts/Amphiprion_ocellaris/)
- [Woollahra Council, underwater camouflage](https://www.woollahra.nsw.gov.au/Environment/bushland-and-biodiversity/stories-of-local-biodiversity/Underwater-Masters-Of-Disguise)
- [Monterey Bay Aquarium, deep sea](https://www.montereybayaquarium.org/animals-the-ocean/ecosystems/deep-sea)
- [Monterey Bay Aquarium, open sea](https://www.montereybayaquarium.org/visit/exhibits/open-sea/)
- [MBARI, barreleye](https://www.mbari.org/animal/barreleye-fish/)
- [MBARI, dinner-plate jelly](https://www.mbari.org/animal/dinner-plate-jelly/)
- [MBARI, Atolla](https://www.mbari.org/news/scientists-discover-a-new-species-of-deep-sea-crown-jelly-in-monterey-bay/)
- [Monterey Bay Aquarium, red paper lantern jelly](https://www.montereybayaquarium.org/animals-the-ocean/animals-a-to-z/red-paper-lantern-jelly)
- [MBARI, psychedelic jelly](https://www.mbari.org/animal/psychedelic-jelly/)
- [MBARI, giant phantom jelly footage](https://www.mbari.org/news/new-underwater-camera-records-stunning-4k-video-of-deep-sea-animals-and-habitats/)

## Integration boundaries

One visible encounter at a time; up to three fish in the two existing school
textures. Traversal takes 26-44 seconds. Gentle gliding, hovering and pulsing
distinguish shapes without implying fully rigged fin animation. Replacement
occurs only after a pass leaves the lane. Hidden pages and inactive themes
pause; reduced-motion and the saved motion-off preference show static animals.

The host, girl mascot, lighting interaction, search, downloads, schedules and
personal state are untouched. This iteration does not install or publish.

Unchanged terrain SHA-256:

```text
water-light.webp 24A89BED812F40AD0EBADBE1863F1A3481C7B745A69A64B63F4D205CC547DB73
water-dark.webp  2C3B114CF474ECB10A200B5189F640158204E471969775E1619155778C0AE650
```

Open `index.html` for a local asset contact sheet. The integrated preview is
served by the plugin's existing `tools/preview_ui.mjs` workflow.
