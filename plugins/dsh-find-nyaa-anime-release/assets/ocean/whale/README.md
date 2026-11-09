# Seated whale: four reviewed actions

The four GIFs share a 512x512 transparent canvas and a fixed seat. They are shown
at 150px on desktop and 132px in a narrow panel. They are original project mascot
artwork, not a sprite sheet or a remote media dependency.

Order: idle -> receive -> reading -> return -> the same idle. Reading includes
one automatic page turn. The source GIF timings and frame counts are retained.
The idle and reading masters remain unchanged; receive includes a tiny cuff-glint
cleanup. `manifest.json` records the exact shipped file hashes.

The client decodes all four clips into one canvas. It pauses for hidden/offscreen
panels, disabled background motion and reduced-motion preferences without losing
its position. Requests change modes only at safe clip boundaries. Browsers lacking
ImageDecoder show `idle-poster.png`, not an uncontrolled animated-image fallback.

The old `../whale-seated.png` is retained as historical source art and is no
longer used by this player. No API key, personal tracking data or external URL is
needed by the mascot. These assets do not change download or host behavior.
