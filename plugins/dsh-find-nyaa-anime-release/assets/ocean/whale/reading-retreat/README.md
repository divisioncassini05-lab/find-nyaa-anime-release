# Reading triple-click retreat

Accepted reading-only interaction, separate from the four main motion modules.
Original idle, receive, reading, return, ambient and checking assets are unchanged.

- `character.gif`: close the book on the lap, lift and hug it, then turn aside.
- `rise.gif`, `hold.gif`, `reveal.gif`: independent painted water veil.
- `recover.gif`: release the hug, lower and reopen the book behind opaque water.
- `water-core.png`: painted inner coverage shared with the reviewed veil.
- `manifest.json`: timing and SHA-256 values for the exact reviewed files.

Three reading clicks within a rolling 1.2 seconds confirm the branch. During this
window the normal single-click ripple remains immediate; its mode change waits
until the group is known. Without a triple-click the existing single-click mode
change is committed, and no new animation assets are decoded. Repeated keyboard
keydown events are not clicks.

Entry waits for the settled original reading cel. Opaque coverage lasts 7.68
seconds. Hidden recovery starts 600 ms into coverage and lasts 3.52 seconds;
original reading is restored while still covered, well before the reveal.
New checking requests wait for this branch, then use the existing complete
reading-to-idle handoff. The effect never owns tracking or download state.

All frames retain a 512x512 transparent canvas; water uses a separate 768x768
rendering surface. Supported desktop/narrow display sizes remain 150px/132px.
No production debug controls or preview-only reveal switch are shipped.
