"""Sweatpants adapter for the independently testable font pipeline."""
import asyncio
import base64
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image
from sweatpants import Module

# The daemon loads entrypoints with spec_from_file_location, not as packages.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import segment, build_font, render_preview


USER_AGENT = 'Sweatpants/1.0 (+https://github.com/Extra-Chill/sweatpants)'


def download_image(url, directory, auth_header=None):
    """Stream HTTP(S) input to a unique temporary path; never overwrite outputs."""
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError('image_url must use http or https')
    request = Request(url, headers={'User-Agent': USER_AGENT})
    if auth_header:
        request.add_header('Authorization', auth_header)
    path = None
    try:
        with urlopen(request, timeout=300) as response:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='source-', delete=False) as out:
                path = Path(out.name)
                shutil.copyfileobj(response, out)
        if not path.stat().st_size:
            raise ValueError('Downloaded image is empty')
        return path
    except BaseException:
        if path:
            path.unlink(missing_ok=True)
        raise


def process(image_path, output_dir, inputs):
    """Run CPU work off the event loop and write the three artifacts."""
    with Image.open(image_path) as image:
        glyphs, counts = segment(image, inputs['glyph_map'],
                                 inputs.get('threshold', 110), inputs.get('upscale', 8))
    options = {key: inputs[key] for key in ('upscale', 'cap_height', 'units_per_em',
               'sidebearing', 'add_basic_punctuation') if key in inputs}
    fonts = build_font(glyphs, inputs['font_name'], **options)
    artifacts = {**fonts, 'preview': render_preview(fonts['ttf'])}
    stem = re.sub(r'\s+', '', inputs['font_name']) + '-Regular'
    files = {}
    for key, data in artifacts.items():
        path = output_dir / (stem + ('.png' if key == 'preview' else '.' + key))
        path.write_bytes(data)
        files[key] = str(path)
    from io import BytesIO
    from fontTools.ttLib import TTFont
    with TTFont(BytesIO(fonts['ttf'])) as font:
        count = len(font.getGlyphOrder())
    return {'status': 'complete', 'files': files,
            'content': {key: base64.b64encode(data).decode('ascii') for key, data in artifacts.items()},
            'stats': {'glyphs': count, 'rows': counts}}


class FontBuilder(Module):
    """Convert a letter sheet to installable fonts and a preview."""

    async def run(self, inputs, settings):
        if not inputs.get('image_url') and not inputs.get('image_path'):
            raise ValueError('One of image_path or image_url is required')
        output_dir = Path(inputs['output_dir']).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        source = Path(inputs['image_path']) if inputs.get('image_path') else None
        downloaded = None
        try:
            if inputs.get('image_url'):
                downloaded = await asyncio.to_thread(download_image, inputs['image_url'],
                    output_dir, inputs.get('image_url_auth_header'))
                source = downloaded
            await self.log('Segmenting letter sheet and building fonts')
            result = await asyncio.to_thread(process, source, output_dir, inputs)
            yield result
            acknowledged = False
            if inputs.get('callback_url'):
                acknowledged = await self.send_signed_callback(
                    inputs['callback_url'], result, inputs.get('callback_secret'),
                    issuer=inputs.get('callback_issuer', 'sweatpants'),
                    user_id=inputs.get('callback_user_id'))
            if acknowledged and inputs.get('callback_cleanup_on_success', True):
                try:
                    # Only remove upload sources in the daemon-owned UUID layout.
                    if source and source.parent.parent.name == 'uploads' and re.fullmatch(
                            r'[0-9a-f]{32}', source.parent.name):
                        shutil.rmtree(source.parent)
                    shutil.rmtree(output_dir)
                except OSError as exc:
                    await self.log(f'Callback cleanup failed: {exc}', level='WARNING')
        finally:
            if downloaded:
                downloaded.unlink(missing_ok=True)
