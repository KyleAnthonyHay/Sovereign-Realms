#!/usr/bin/env python3
"""Draws the interface's pixel art into SourceArt/UI (run: Tools/.venv/bin/python Tools/ui/gen_ui_art.py).

  T_UI_Icons.png   the icon atlas: COLS x ROWS cells of CELL px (a 16 px icon with a 1 px gutter). The order of ICONS
                   below IS the C++ enum ESRIcon (Source/SovereignRealms/Player/SRHUD.h): add new icons at the end
                   of the list and to the enum. Every icon is drawn twice: rows 0..5 in the player's blue, rows
                   6..11 with the team pixels (t T u) swapped to the enemy's red.
  T_UI_Title.png   the "SOVEREIGN REALMS" title lettering (an original chiselled-gold pixel face).
Imported by Tools/import_ui_assets.py into /Game/SR/UI (nearest filter, no mips). A contact sheet goes to
Saved/TexturePreview/ui.png.
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "UI")
CELL, COLS, ROWS = 18, 8, 6

PAL = {
    "k": "1a1210", "y": "e8b030", "Y": "ffe07a", "o": "a86a14", "w": "f4ecd8", "g": "b9c0c8", "G": "7c8794",
    "d": "4a5260", "b": "7a4a22", "B": "b07a3c", "n": "4a2c14", "r": "d8402c", "R": "8c2018", "t": "3d7be0",
    "T": "2450a8", "u": "8ab8ff", "e": "6aa83a", "E": "3c6c24", "s": "e8b890", "S": "b88058", "p": "e9dcb8",
}
ENEMY = {"t": "d04a34", "T": "8c2418", "u": "ff9a7a"}
OUTLINE = (16, 14, 20, 255)

ICONS = [
    ("Coin", """
....yyyy....
..yyYYYYyy..
.yYYyyyyyyo.
.yYyyoyyyyo.
yYyyoyyyyyyo
yYyyoyyyyyyo
yyyyoyyyyyoo
yyyyoyyyyyoo
.yyyyooyyoo.
.yyyyyyyooo.
..ooyyyooo..
....oooo...."""),
    ("Food", """
.....Y......
....YyY.....
...Y.y.Y....
...yYyYy....
..Y.yyy.Y...
..yY.y.Yy...
...yYyYy....
....yyy.....
.....o......
.....o......
.....o......
.....o......"""),
    ("Pop", """
...ss....ss...
..ssss..ssss..
..sSSs..sSSs..
...ss....ss...
..tttt..tttt..
.tuttttttuttt.
.tttttTTttttt.
.tttttTTttttt.
.TTTTT..TTTTT."""),
    ("Shield", """
.gggggggggg.
.gttttuuttg.
.gtttuutttg.
.gttwwwwttg.
.gttwttwttg.
.gttwwwwttg.
.gTttwwttTg.
..gTtttTTg..
..gTTttTTg..
...gTTTTg...
....gTTg....
.....gg....."""),
    ("Bow", """
...wyy......
...w.yy.....
...w..yy....
...w...yB...
...w...yB...
GGgwgggyBgww
...w...yB...
...w...yB...
...w..yy....
...w.yy.....
...wyy......"""),
    ("Farm", """
.....rr.....
....rrrr....
...rrRRrr...
..rrRRRRrr..
.rrpppppprr.
..pppnnppp..
..pppnnppp..
..pppnnppp..
eEeEeEeEeEeE
yEyEyEyEyEyE"""),
    ("Mine", """
..ggggggg...
.gGG...bGg..
.g....b..Gg.
.....b....g.
....b.......
...b....yy..
..b....yYyy.
.b....yyyyo.
b.....yyooo."""),
    ("Tower", """
.g.gg.gg.g..
.gggggggggg.
.gGGGGGGGGg.
..gggggggg..
..ggGdGggG..
..gggdgggG..
..ggggggGG..
..gGggggGG..
..ggggGgGG..
..ggnnnggG..
.gggnnngGGG.
.gggnnngGGG."""),
    ("FormLine", """
pp.pp.pp.pp
pp.pp.pp.pp
...........
pp.pp.pp.pp
pp.pp.pp.pp"""),
    ("FormColumn", """
pp.pp
pp.pp
.....
pp.pp
pp.pp
.....
pp.pp
pp.pp
.....
pp.pp
pp.pp"""),
    ("FormWedge", """
.....pp.....
.....pp.....
............
...pp..pp...
...pp..pp...
............
.pp......pp.
.pp......pp."""),
    ("FormSquare", """
pp.pp.pp
pp.pp.pp
........
pp.yy.pp
pp.yy.pp
........
pp.pp.pp
pp.pp.pp"""),
    ("StanceAggressive", """
.........ww.
........wgw.
.......wgw..
......wgw...
.....wgw....
.o..wgw.....
.yowgw......
..yow.......
.byyo.......
bb..yo......
b..........."""),
    ("StanceDefensive", """
.yyyyyyyyyy.
.yggggwwggy.
.ygggwwgggy.
.yggyyyyggy.
.yggyggyggy.
.yggyyyyggy.
.yGggyyggGy.
..yGgggGGy..
..yGGggGGy..
...yGGGGy...
....yGGy....
.....yy....."""),
    ("StanceHold", """
...n.......
...nrrrrrr.
...nrrRRrr.
...nrrrrr..
...nrrrr...
...n.......
...n.......
...n.......
..GnG......
.GGGGG.....
GGGGGGG...."""),
    ("Stop", """
...rrrrrr...
..rrrrrrrr..
.rrrrrrrrrr.
rrrrrrrrrrrr
rrwwwwwwwwrr
rrwwwwwwwwrr
rrwwwwwwwwrr
rrrrrrrrrrrr
.RRRRRRRRRR.
..RRRRRRRR..
...RRRRRR..."""),
    ("Swords", """
w..........w
ww........ww
.ww......ww.
..ww....ww..
...ww..ww...
....wwww....
.....ww.....
....wwww....
.y.ww..ww.y.
..yw....wy..
.byy....yyb.
b..........b"""),
    ("AlertAttack", """
.....r......
....rr......
....rrr.....
...rryr..r..
..rryyrr.rr.
..ryyyyrrrr.
.rryYYyyrrr.
.rryYYYyyrr.
.rryYwYyyrr.
..ryYwwYyr..
..rryYYyrr..
...rrrrrr..."""),
    ("AlertLost", """
..wwwwwwww..
.wwwwwwwwww.
.wwwwwwwwww.
.wkkwwwwkkw.
.wkkwwwwkkw.
.wwwwkkwwww.
..wwwkkwww..
..wgwwwwgw..
...wkwkwkw..
...gwgwgwg.."""),
    ("AlertDone", """
....GGGGGG..
...GgggggG..
...GgggggG..
....GGbGG...
......b.....
.....b......
....b.......
...b........
..b.........
.b.........."""),
    ("AlertWave", """
.n.........
.nrrrrrrrrr
.nrrrwwrrr.
.nrrrwwrr..
.nrrrwwrrr.
.nrrrrrrrrr
.nrrrwwrr..
.nrrrrr....
.n.........
.n.........
.n........."""),
    ("AlertPop", """
.....rr.....
....rrrr....
...rrrrrr...
..rrrrrrrr..
.rrrrrrrrrr.
..pppppppp..
..ppnnpppp..
..ppnnpupp..
..ppnnpppp.."""),
    ("AlertInfo", """
...tttttt...
..tttwwttt..
.ttttwwtttt.
.tttttttttt.
.tttwwwtttt.
.ttttwwtttt.
.ttttwwtttt.
.tttwwwwttt.
..tttttttt..
...tttttt..."""),
    ("Clock", """
.yyyyyyyyyy.
..pppppppp..
..pYYYYYYp..
...pYYYYp...
....pYYp....
.....pp.....
....p..p....
...p.Y..p...
..p.YYYY.p..
..pYYYYYYp..
.yyyyyyyyyy."""),
    ("Pause", """
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp
ppp..ppp"""),
    ("Help", """
..yyyyyy..
.yy....yy.
.yy....yy.
......yy..
.....yy...
....yy....
....yy....
..........
....yy....
....yy...."""),
    ("RecruitFlag", """
.n.........
.ntttttttt.
.nttttwttt.
.ntttwwwt..
.nttttwttt.
.ntttttttt.
.n.........
.n.........
.n.........
.n........."""),
    ("Castle", """
g.g..gg..g.g
ggg..gg..ggg
gGg.gggg.gGg
ggggggGggggg
gGgggggggGgg
ggggnnnngggg
gGggnnnngGgg
ggggnnnngggg"""),
    ("ChevronDown", """
p......p
pp....pp
.pp..pp.
..pppp..
...pp..."""),
    ("ChevronUp", """
...pp...
..pppp..
.pp..pp.
pp....pp
p......p"""),
    ("Crown", """
y....y....y
yy..yYy..yy
yYyyyYyyyYy
yYYyYYYyYYy
yyyyyyyyyyy
orooyuyooro
ooooooooooo"""),
    ("Cancel", """
rr......rr
rrr....rrr
.rrr..rrr.
..rrrrrr..
...rrrr...
..rrrrrr..
.rrr..rrr.
rrr....rrr
rr......rr"""),
    ("PortraitShield", """
...gggggg...
..gwggggGg..
.ggggggggGg.
.gggggggGGg.
.gGssssssGg.
.gsskssksGg.
.gssssssSg..
..gssnnsSg..
...sssssS...
..tttttttt..
.tuttttttTt.
.ttttttttTt."""),
    ("PortraitArcher", """
....eeee....
...eeeeEe...
..eeeeeeEe..
..eessssEe..
..esksskse..
..essssSSe..
..eEsnnsEE..
...EsssSE...
..bttttttE..
.bBtutttTt..
.b.tttttTt.."""),
    ("Check", """
.........ee
........eee
.......eee.
ee....eee..
eee..eee...
.eeeeee....
..eeee.....
...ee......"""),
    ("Vein", """
....yy......
...yYyy..y..
..yYyyyoyYy.
.yyyyyooyyo.
..oyyoo.oo..
...ooo......"""),
    ("Barracks", """
..b......b..
...b....b...
....b..b....
.rrrrbbrrrr.
rrRRRbbRRRrr
.pppbppbppp.
.ppbptTpbpp.
.pppptTpppp.
.ppppnnpppp.
.ppppnnpppp.
eEeEeEeEeEeE"""),
    ("Range", """
....rrrr....
..rrwwwwrr..
.rwwrrrrwwr.
.rwrrwwrrwr.
rwrwwyywwrwr
rwrwyYYywrwr
rwrwyYYywrwr
rwrwwyywwrwr
.rwrrwwrrwr.
.rwwrrrrwwr.
..rrwwwwrr..
....rrrr...."""),
    ("Hammer", """
..ggggg.....
.gwGGGGg....
.gGGGGGg....
..gggggB....
......BB....
.....BB.....
....BB......
...bb.......
..bb........
.bb........."""),
    ("Patrol", """
...uuuuu....
..u.....uu..
.u.......uuu
.u.......uu.
.u..........
............
..........u.
.uu.......u.
uuu.......u.
..uu.....u..
....uuuuu..."""),
    ("Disband", """
.n..........
.ntttttt....
.nttTTtt....
.ntttttt....
.n......r..r
.n.......rr.
.n.......rr.
.n......r..r
.n..........
.n.........."""),
    ("PortraitHorse", """
......nn....
.....nBBn...
....nBBBBn..
...nBBkBBBn.
..nBBBBBBBBn
.nBBBnnBBBBn
.nBBn..nBBBn
..nn...nBBBn
......nBBBBn
.....nttttBn
.....ntTTtBn
.....nttttBn"""),
    ("PortraitCatapult", """
..........gg
.........gg.
........bb..
.......bb...
......bb....
.....bb.....
....bbbbbbb.
...bbbbbbbbb
..bnbbbbbnbb
..nnn...nnn.
...n.....n.."""),
    ("Stable", """
....rrrrrr..
...rrRRRRrr.
..rrRRRRRRrr
.rrrrrrrrrrr
.pbpppbpppbp
.pbnnnbnnnbp
.pbnBnbnBnbp
.pbnnnbnnnbp
.pbbbbbbbbbp
yeyeyeyeyeye"""),
    ("Workshop", """
..rrrrrrrr..
.rrRRRRRRrr.
rrrrrrrrrrrr
.b..g...b...
.b.gg...b...
.b..bb..b...
.b...bb.b...
.b.bbbbbb...
.b.n.bb.nb..
nnnnnnnnnnnn"""),
    ("PortraitBuilder", """
.......nBBBn
.......nBBBn
..ttt....b..
.tTTTt...b..
tTssst...b..
tssksk...b..
tsssss..sb..
.tSSS..ss...
.nnnnnnn....
nppnnppn....
.pnnnnp.....
.nn..nn....."""),
]


def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def draw_icon(rows, enemy):
    rows = [r for r in rows.strip("\n").split("\n")]
    h, w = len(rows), max(len(r) for r in rows)
    assert w <= 16 and h <= 16, (w, h)
    cell = np.zeros((CELL, CELL, 4), np.uint8)
    ox, oy = 1 + (16 - w) // 2, 1 + (16 - h) // 2
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            col = ENEMY[ch] if enemy and ch in ENEMY else PAL[ch]
            cell[oy + j, ox + i] = hexrgb(col)
    # a dark one-pixel outline wherever there is room: the icons sit on dark panels AND on the lit battlefield
    solid = cell[..., 3] > 0
    grow = np.zeros_like(solid)
    grow[1:, :] |= solid[:-1, :]; grow[:-1, :] |= solid[1:, :]; grow[:, 1:] |= solid[:, :-1]; grow[:, :-1] |= solid[:, 1:]
    edge = grow & ~solid
    edge[0, :] = edge[-1, :] = False; edge[:, 0] = edge[:, -1] = False
    cell[edge] = OUTLINE
    return cell


GLYPHS = {
    "S": [".#####.", "##...##", "##.....", "###....", ".#####.", "....###", ".....##", "##...##", ".#####."],
    "O": [".#####.", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", ".#####."],
    "V": ["##...##", "##...##", "##...##", "##...##", "##...##", ".##.##.", ".##.##.", "..###..", "...#..."],
    "E": ["#######", "##....#", "##.....", "##..#..", "#####..", "##..#..", "##.....", "##....#", "#######"],
    "R": ["######.", "##...##", "##...##", "##...##", "######.", "##.##..", "##..##.", "##...##", "##...##"],
    "I": ["######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..", "######"],
    "G": [".#####.", "##...##", "##.....", "##.....", "##..###", "##...##", "##...##", "##...##", ".#####."],
    "N": ["##...##", "###..##", "###..##", "####.##", "##.#.##", "##.####", "##..###", "##..###", "##...##"],
    "A": ["..###..", ".##.##.", "##...##", "##...##", "##...##", "#######", "##...##", "##...##", "##...##"],
    "L": ["##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##.....", "##....#", "#######"],
    "M": ["##.....##", "###...###", "####.####", "##.###.##", "##..#..##", "##.....##", "##.....##", "##.....##", "##.....##"],
    " ": ["....", "....", "....", "....", "....", "....", "....", "....", "...."],
}


def draw_title(text, k=4):
    cols = []
    for ch in text:
        g = GLYPHS[ch]
        cols.append(np.array([[c == "#" for c in row] for row in g], bool))
        cols.append(np.zeros((9, 1), bool))
    mask = np.concatenate(cols[:-1], axis=1)
    mask = np.kron(mask, np.ones((k + 2, k), bool))                    # each glyph pixel is a k x k block, shaded below
    pad = 4
    h, w = mask.shape
    m = np.zeros((h + 2 * pad + 2, w + 2 * pad), bool)
    m[pad:pad + h, pad:pad + w] = mask
    img = np.zeros(m.shape + (4,), np.uint8)
    # drop shadow, then a dark outline
    sh = np.zeros_like(m); sh[3:, 2:] = m[:-3, :-2]
    img[sh] = (8, 8, 14, 150)
    out = m.copy()
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            if abs(dx) + abs(dy) <= 3:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    img[out] = (38, 22, 8, 255)
    # chiselled gold: a vertical gradient in bands, a light top-left edge, a deep lower-right edge
    top = np.array([255, 236, 150], float); mid = np.array([236, 178, 52], float); low = np.array([168, 104, 22], float)
    ys = np.arange(m.shape[0])
    t = np.clip((ys - pad) / float(h - 1), 0, 1)
    t = np.round(t * 8) / 8.0                                         # banded, not smooth: it is pixel art
    grad = np.where(t[:, None] < 0.5, top + (mid - top) * (t[:, None] / 0.5), mid + (low - mid) * ((t[:, None] - 0.5) / 0.5))
    body = np.repeat(grad[:, None, :], m.shape[1], axis=1)
    up = np.roll(m, 1, 0); left = np.roll(m, 1, 1); down = np.roll(m, -1, 0); right = np.roll(m, -1, 1)
    hi = m & (~up | ~left)
    lo = m & (~down | ~right) & ~hi
    body[hi] = (255, 248, 205)
    body[lo] = (122, 70, 14)
    img[m, :3] = np.clip(body[m], 0, 255).astype(np.uint8)
    img[m, 3] = 255
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    assert len(ICONS) <= COLS * ROWS
    atlas = np.zeros((ROWS * 2 * CELL, COLS * CELL, 4), np.uint8)
    for n, (name, rows) in enumerate(ICONS):
        for enemy in (0, 1):
            r, c = n // COLS + enemy * ROWS, n % COLS
            atlas[r * CELL:(r + 1) * CELL, c * CELL:(c + 1) * CELL] = draw_icon(rows, enemy)
    Image.fromarray(atlas).save(os.path.join(OUT, "T_UI_Icons.png"))
    title = draw_title("SOVEREIGN REALMS")
    Image.fromarray(title).save(os.path.join(OUT, "T_UI_Title.png"))

    prev = os.path.join(ROOT, "Saved", "TexturePreview")
    os.makedirs(prev, exist_ok=True)
    sheet = Image.new("RGBA", (max(atlas.shape[1] * 4, title.shape[1] * 2), atlas.shape[0] * 4 + title.shape[0] * 2 + 8), (22, 30, 48, 255))
    sheet.alpha_composite(Image.fromarray(atlas).resize((atlas.shape[1] * 4, atlas.shape[0] * 4), Image.NEAREST), (0, 0))
    sheet.alpha_composite(Image.fromarray(title).resize((title.shape[1] * 2, title.shape[0] * 2), Image.NEAREST), (0, atlas.shape[0] * 4 + 8))
    sheet.save(os.path.join(prev, "ui.png"))
    print("icons %d (atlas %dx%d), title %dx%d" % (len(ICONS), atlas.shape[1], atlas.shape[0], title.shape[1], title.shape[0]))
    print("enum order:", ", ".join(n for n, _ in ICONS))


if __name__ == "__main__":
    main()
