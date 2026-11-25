"""Letter-sheet segmentation and font construction, independent of Sweatpants."""
from dataclasses import dataclass
from io import BytesIO
import re

import numpy as np
import potrace
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage as ndi
from fontTools.agl import AGL2UV
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen


@dataclass
class Glyph:
    bitmap: np.ndarray
    top: int
    bottom: int
    row: int


def _runs(mask, minimum):
    edges = np.diff(np.pad(np.asarray(mask, dtype=int), (1, 1)))
    return [(int(a), int(b)) for a, b in zip(
        np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    ) if b - a > minimum]


def segment(image, glyph_map, threshold=110, upscale=8):
    """Return named glyph bitmaps and detected counts, in reading order.

    Input is a Pillow image; all coordinates before smoothing are source pixels.
    """
    if not 0 <= threshold <= 255 or upscale < 1:
        raise ValueError("threshold must be 0..255 and upscale must be positive")
    names = [line.split() for line in glyph_map.replace('|', '\n').splitlines() if line.strip()]
    flat = [n for row in names for n in row]
    if not flat or len(set(flat)) != len(flat):
        raise ValueError("glyph_map must contain unique glyph names")
    for name in flat:
        if not re.fullmatch(r"[A-Za-z0-9_.]+", name) and len(name) != 1:
            raise ValueError(f"Invalid glyph name: {name!r}")
        if name == '.notdef':
            raise ValueError(".notdef is reserved")
    a = np.array(image.convert('L'))
    ink = a < threshold
    rows = [(max(0, y0 - 6), min(a.shape[0], y1 + 6))
            for y0, y1 in _runs(ink.sum(axis=1) > 2, 15)]
    columns = [_runs(ndi.binary_dilation(ink[y0:y1].any(axis=0), iterations=3), 8)
               for y0, y1 in rows]
    counts = [len(cols) for cols in columns]
    expected = [len(row) for row in names]
    if not counts or counts != expected:
        raise ValueError(f"glyph_map mismatch: detected count per row {counts}; expected {expected}")
    glyphs = {}
    for row, ((y0, y1), cols, row_names) in enumerate(zip(rows, columns, names)):
        for name, (x0, x1) in zip(row_names, cols):
            m = ink[y0:y1, x0:x1]
            labels, k = ndi.label(m)
            sizes = np.bincount(labels.ravel(), minlength=k + 1)
            keep = np.isin(labels, np.flatnonzero(sizes[1:] >= 25) + 1)
            ys, xs = np.where(keep)
            if not len(ys):
                raise ValueError(f"Glyph {name!r} in row {row + 1} contains no components >=25 pixels")
            by0, by1, bx0, bx1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            g = a[y0:y1, x0:x1].copy()
            g[~ndi.binary_dilation(keep, iterations=2)] = 255
            # Explicit padding also handles crops touching any image edge.
            g = np.pad(g, 2, constant_values=255)[by0:by1 + 4, bx0:bx1 + 4]
            im = Image.fromarray(g).resize((g.shape[1] * upscale, g.shape[0] * upscale),
                                          Image.Resampling.LANCZOS)
            im = im.filter(ImageFilter.GaussianBlur(upscale * 0.6))
            glyphs[name] = Glyph(np.array(im) < 128, int(y0 + by0 - 2),
                                 int(y0 + by1 + 2), row)
    return glyphs, counts


def trace(bitmap, scale=1.0, ox=0, oy=0):
    """Trace ink to cubic outlines, flipping image y into font coordinates."""
    pen = RecordingPen()
    # potracer treats False as foreground: tracing ink directly yields a box!
    path = potrace.Bitmap(~bitmap).trace(turdsize=40, alphamax=1.0,
                                        opticurve=True, opttolerance=0.3)
    def point(pt):
        return round(pt.x * scale + ox), round(oy - pt.y * scale)
    for curve in path:
        pen.moveTo(point(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                pen.lineTo(point(seg.c))
                pen.lineTo(point(seg.end_point))
            else:
                pen.curveTo(point(seg.c1), point(seg.c2), point(seg.end_point))
        pen.closePath()
    return pen


def _polygon(points):
    pen = RecordingPen()
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()
    return pen


def build_font(glyphs, font_name, *, upscale=8, cap_height=700,
               units_per_em=1000, sidebearing=35, add_basic_punctuation=True):
    """Return {'otf': bytes, 'ttf': bytes} without filesystem side effects."""
    ps_family = re.sub(r'\s+', '', font_name)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ps_family):
        raise ValueError("font_name must contain only letters, numbers, spaces, hyphens or underscores")
    if not glyphs or upscale < 1 or cap_height < 1 or not 16 <= units_per_em <= 16384 or sidebearing < 0:
        raise ValueError("Invalid font dimensions or empty glyph collection")
    ps_name = ps_family + '-Regular'
    scale = cap_height / (np.median([g.bottom - g.top for g in glyphs.values()]) - 4) / upscale
    baselines = {r: np.median([g.bottom for g in glyphs.values() if g.row == r])
                 for r in {g.row for g in glyphs.values()}}
    recs, advances = {}, {}
    for name, g in glyphs.items():
        recs[name] = trace(g.bitmap, scale, sidebearing - 2 * upscale * scale,
                           (baselines[g.row] - g.top - 2) * upscale * scale)
        advances[name] = round((g.bitmap.shape[1] - 4 * upscale) * scale + 2 * sidebearing)
    punctuation = {
        'period': ([(40,0),(40,130),(170,130),(170,0)], 210),
        'comma': ([(40,-110),(110,0),(40,0),(40,130),(170,130),(170,10),(95,-110)], 210),
        'quotesingle': ([(50,700),(50,470),(120,470),(150,700)], 200),
        'quoteright': ([(40,700),(170,700),(170,580),(95,450),(60,450),(110,570),(40,570)], 210),
    }
    # Recognize both literal codepoints and standard Adobe glyph names.
    cmap = {}
    for name in glyphs:
        if len(name) == 1:
            cmap[ord(name)] = name
        elif name in AGL2UV:
            cmap[AGL2UV[name]] = name
    if add_basic_punctuation:
        for name, (points, width) in punctuation.items():
            code = AGL2UV[name]
            if code not in cmap:
                recs[name] = _polygon(points[::-1])
                advances[name] = width
                cmap[code] = name
        if 32 not in cmap:
            recs['space'] = RecordingPen()
            advances['space'] = 260
            cmap[32] = 'space'
    recs['.notdef'] = _polygon([(50,0),(50,700),(450,700),(450,0)])
    advances['.notdef'] = 500
    order = ['.notdef'] + [n for n in recs if n != '.notdef']
    substitutions = []
    for name in glyphs:
        if name.endswith('.alt'):
            base = name[:-4]
            if base not in glyphs:
                raise ValueError(f"Alternate {name!r} has no base glyph {base!r}")
            # Backslash escapes single-character punctuation and feature keywords.
            substitutions.append(f'sub \\{base} by \\{name};')
    outputs = {}
    for ext in ('otf', 'ttf'):
        fb = FontBuilder(units_per_em, isTTF=ext == 'ttf')
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap(cmap)
        if ext == 'otf':
            strings = {}
            for name in order:
                pen = T2CharStringPen(advances[name], None)
                recs[name].replay(pen)
                strings[name] = pen.getCharString()
            fb.setupCFF(ps_name, {'FullName': font_name, 'FamilyName': font_name}, strings, {})
        else:
            outlines = {}
            for name in order:
                pen = TTGlyphPen(None)
                recs[name].replay(Cu2QuPen(pen, 1.0, reverse_direction=True))
                outlines[name] = pen.glyph()
            fb.setupGlyf(outlines)
        fb.setupHorizontalMetrics({n: (advances[n], 0) for n in order})
        fb.setupHorizontalHeader(ascent=900, descent=-250)
        fb.setupNameTable({'familyName': font_name, 'styleName': 'Regular',
                           'uniqueFontIdentifier': ps_name + '-1.0', 'fullName': font_name,
                           'psName': ps_name, 'version': 'Version 1.000'})
        fb.setupOS2(sTypoAscender=900, sTypoDescender=-250, usWinAscent=950,
                    usWinDescent=300, sCapHeight=cap_height, sxHeight=cap_height, fsType=0)
        fb.setupPost()
        if substitutions:
            rules = ' '.join(substitutions)
            addOpenTypeFeaturesFromString(fb.font, '\n'.join(
                f'feature {tag} {{ {rules} }} {tag};' for tag in ('salt', 'ss01')))
        out = BytesIO()
        fb.save(out)
        outputs[ext] = out.getvalue()
    return outputs


def render_preview(ttf):
    """Return a PNG with uppercase, lowercase and a sample sentence."""
    font = ImageFont.truetype(BytesIO(ttf), 48)
    lines = ['ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz',
             'The quick brown fox jumps over the lazy dog.']
    width = max(800, int(max(font.getlength(s) for s in lines)) + 48)
    image = Image.new('RGB', (width, 260), 'white')
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((24, 15 + i * 78), line, font=font, fill='black')
    out = BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()
