KING — RIGHT-FACING RUN

Start with king_run_strip.png: 1024 x 128, eight 128 x 128 cells.
Play frames 0 through 7, left to right, at 12 FPS, looping.
The alternative king_run_grid.png is 512 x 256: four columns, two rows,
read across the top row, then across the bottom row.
Both sheets have zero spacing and zero margin between cells.

frames/ contains the same eight transparent RGBA PNGs individually.
Use the entire 128 x 128 rectangle for each frame. Do not automatically trim
or independently center the silhouettes: that removes the shared registration.
Shared pivot: pixel (84,120), measured from the top-left of every frame.
Normalized top-left-origin pivot: (0.65625,0.9375).
The animation runs in place; move the character using your game code.
Flip horizontally to face left. The cape and sword also flip.

IMPORT SETTINGS
Nearest/Point filtering; mipmaps off; preserve alpha; render at integer scale.
Avoid lossy texture compression. Eight frames, forward playback, loop enabled.
Unity: Sprite Multiple, grid 128x128, Point, no compression, custom pivot.
Godot: hframes=8, vframes=1; animate frame 0..7 at 12 FPS; nearest filtering.
Unreal Paper2D: extract 128x128 cells; build a 12 FPS looping Flipbook;
use point filtering and a consistent custom pivot.

king_run_atlas.json: TexturePacker-style JSON hash atlas with rectangles,
durations, source sizes and pivots. Check your importer supports this schema;
manual uniform-grid slicing works without an atlas importer.
king_run_animation.json: simple engine-neutral animation description.
king_run_preview.gif: enlarged animation on a dark background for review.
king_run_contact_sheet.png: enlarged static reference, not a game texture.

ARTWORK / EXPORT
Artwork: built-in imagegen, based on the user's king reference.
Artwork prompt: an eight-frame right-facing pixel-art king run cycle,
with gold crown, black beard, cream fur, silver armor, green tunic/cape,
and sword; four columns by two rows on transparent background.
This export slices that generated artwork, converts it to equal 128x128
frames with nearest-neighbor sampling, binary transparency and a shared
palette of at most 48 colors. It does not redraw the generated poses;
small costume and silhouette variations remain between frames.
This is one run animation; idle, attack, death and other views are not included.
