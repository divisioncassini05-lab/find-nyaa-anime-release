# Ocean artwork

Generated bitmap decorations for the DSH dashboard:

- `water-light.webp`: painted natural seabed, with an open center for UI content.
- `water-dark.webp`: separately painted low-light seabed; not an inverted image.
- `carved-starfish.webp`: transparent hand-carved starfish illustration, guided by
  user-provided CLANNAD prop references. It is a static decorative accent.

The environment borrows an anime background-painting direction from Nagi no
Asukara and Goodbye, Lara. No anime screenshots or city buildings are included.
The separate project mascot is documented in `whale/README.md`. Generated artwork is not official
artwork or an affiliation claim. The client embeds these files as data URLs so
they also work in DSH's virtual module loader without additional asset routes.
