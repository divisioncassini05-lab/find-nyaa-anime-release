# Seated Whale Mascot

`whale-seated.png` is an alpha-transparent character asset made with the built-in
image-generation tool, using the user's cropped whale-hood mascot reference.
It is separate from the ocean backdrop and from the code-rendered water ribbon.
The initial upright and crouching variants are not included in the plugin.

Final prompt: preserve the reference's small face, blue-and-amber eyes, loose
blue whale hood, white scalloped trim, long blue hair, gray/navy coat and tail.
Change only the pose to sitting on an invisible ledge, hands braced beside the
hips and both lower legs dangling naturally. Do not crouch or hug the knees.
Keep soft hand-drawn anime shading and muted colors. Output only the whole
character on actual transparency, without a seat, water, shadow or text.

The 1339 x 1174 sprite has its seating contact at approximately (40.5%, 70%).
CSS isolates the lower legs below 72.5%; the body overlaps the cut by 0.5% to
conceal the hinges. Do not substitute a different pose without updating these
anchors and running `tools/check_whale_ui.mjs`.

The mascot is fixed to the ribbon, not draggable. Its interaction is local-only
and cannot run searches, submit downloads or update watching progress. Idle
motion follows the scene setting, reduced-motion preference and visibility.
