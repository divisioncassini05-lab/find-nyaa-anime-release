# Ambient gestures

Five gestures accepted for integration on 2026-11-10. The GIFs retain the
reviewed 512x512 origin and are displayed at 150px / 132px with no recentering.
The original four master GIFs remain byte-identical in the parent directory.

- Idle: alternating feet, sleeve adjustment, playing with water.
- Reading: tracing the page, resting her chin while thinking.
- The book layer runs on a continuous clock during idle gestures.
- Water and blue-to-black ink are separate procedural layers; the near book
  cover occludes the ink. Their coordinates are tied to the selected GIF hashes.
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
