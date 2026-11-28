"""Synthetic sheets only: no daemon, downloads, or external image fixtures."""
from io import BytesIO
from pathlib import Path
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import segment, build_font, render_preview, trace


@pytest.fixture
def sheet():
    # Pillow's bundled scalable font avoids dependence on system font paths.
    font = ImageFont.load_default(size=64)
    image = Image.new('L', (320, 210), 255)
    draw = ImageDraw.Draw(image)
    for y in (15, 115):
        for x, letter in zip((20, 120, 220), 'ABO'):
            draw.text((x, y), letter, font=font, fill=0)
    return image


@pytest.fixture
def generated(sheet):
    glyphs, counts = segment(sheet, 'A B O | A.alt B.alt O.alt')
    return glyphs, counts, build_font(glyphs, 'Test Family')


def test_segmentation(sheet):
    glyphs, counts = segment(sheet, 'A B O\nA.alt B.alt O.alt')
    assert counts == [3, 3]
    assert len(glyphs) == 6
    assert all(g.bitmap.dtype == bool for g in glyphs.values())


def test_mismatch_reports_all_counts(sheet):
    with pytest.raises(ValueError, match=r'detected count per row \[3, 3\]; expected \[2, 1\]'):
        segment(sheet, 'A B | C')


@pytest.mark.parametrize('ext', ['otf', 'ttf'])
def test_font_tables(generated, ext):
    _, counts, fonts = generated
    with TTFont(BytesIO(fonts[ext])) as font:
        cmap = font.getBestCmap()
        assert {ord(c) for c in "ABO .,\u0027\u2019"} <= set(cmap)
        assert cmap[ord('A')] == 'A'
        assert font['name'].getDebugName(1) == 'Test Family'
        assert font['name'].getDebugName(4) == 'Test Family'
        assert font['name'].getDebugName(6) == 'TestFamily-Regular'
        assert font['OS/2'].fsType == 0
        features = font['GSUB'].table.FeatureList.FeatureRecord
        assert {f.FeatureTag for f in features} == {'salt', 'ss01'}
        lookups = font['GSUB'].table.LookupList.Lookup
        assert any(s.mapping.get('A') == 'A.alt' for l in lookups for s in l.SubTable)
        assert ('CFF ' if ext == 'otf' else 'glyf') in font
    assert counts == [3, 3]


def test_not_inverted(generated):
    """Both formats must show ink, not a filled cell with a knocked-out letter."""
    for data in generated[2].values():
        font = ImageFont.truetype(BytesIO(data), 180)
        mask = np.array(font.getmask('A')).reshape(font.getmask('A').size[::-1])
        assert 0.05 < (mask > 128).mean() < 0.60
        # The outside corners should be white, not part of a background box.
        assert mask[0, 0] == 0


def test_trace_does_not_include_bitmap_boundary():
    bitmap = np.zeros((100, 100), dtype=bool)
    bitmap[20:80, 40:60] = True
    pen = trace(bitmap)
    coords = [p for _, points in pen.value for p in points]
    assert coords
    assert min(x for x, y in coords) >= 39
    assert max(x for x, y in coords) <= 61


def test_preview(generated):
    png = render_preview(generated[2]['ttf'])
    with Image.open(BytesIO(png)) as image:
        assert image.format == 'PNG'
        assert image.width >= 800
        assert np.asarray(image).min() < 128


def test_optional_punctuation_and_supplied_preserved(sheet):
    glyphs, _ = segment(sheet, 'A period O | A.alt B C')
    fonts = build_font(glyphs, 'Test', add_basic_punctuation=False)
    with TTFont(BytesIO(fonts['ttf'])) as font:
        assert font.getBestCmap()[46] == 'period'
        assert 32 not in font.getBestCmap()
    fonts = build_font(glyphs, 'Test')
    with TTFont(BytesIO(fonts['ttf'])) as font:
        assert font['hmtx']['period'][0] != 210


def test_alternate_requires_base(sheet):
    glyphs, _ = segment(sheet, 'A B C | X.alt Y Z')
    with pytest.raises(ValueError, match='has no base glyph'):
        build_font(glyphs, 'Test')
