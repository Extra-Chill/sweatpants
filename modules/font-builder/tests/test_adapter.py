"""Adapter contract tests with a stand-in SDK (no daemon or network)."""
import asyncio
import base64
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

from PIL import Image, ImageDraw, ImageFont
import pytest


@pytest.fixture
def adapter(monkeypatch):
    sdk = ModuleType('sweatpants')
    sdk.Module = type('Module', (), {})
    monkeypatch.setitem(sys.modules, 'sweatpants', sdk)
    path = Path(__file__).resolve().parents[1] / 'main.py'
    spec = importlib.util.spec_from_file_location('font_builder_test_adapter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('ack,cleanup,removed', [(True, True, True),
                                              (False, True, False),
                                              (True, False, False)])
def test_callback_and_cleanup(adapter, tmp_path, ack, cleanup, removed):
    upload = tmp_path / 'uploads' / ('a' * 32)
    upload.mkdir(parents=True)
    source = upload / 'sheet.png'
    image = Image.new('L', (100, 100), 255)
    ImageDraw.Draw(image).text((15, 10), 'A', font=ImageFont.load_default(size=64), fill=0)
    image.save(source)
    output = tmp_path / 'output'
    module = adapter.FontBuilder()
    calls = []

    async def log(*args, **kwargs):
        pass

    async def callback(url, payload, secret, **kwargs):
        calls.append((url, payload, secret, kwargs))
        return ack

    module.log = log
    module.send_signed_callback = callback

    async def run():
        return [r async for r in module.run({
            'image_path': str(source), 'output_dir': str(output),
            'font_name': 'Adapter Test', 'glyph_map': 'A',
            'callback_url': 'https://receiver.invalid/done', 'callback_secret': 'secret',
            'callback_user_id': 42, 'callback_issuer': 'test',
            'callback_cleanup_on_success': cleanup,
        }, {})]

    results = asyncio.run(run())
    result = results[0]
    assert result['status'] == 'complete'
    assert result['stats']['rows'] == [1]
    assert set(result['files']) == {'otf', 'ttf', 'preview'}
    assert base64.b64decode(result['content']['ttf'])[:4] == b'\x00\x01\x00\x00'
    assert base64.b64decode(result['content']['preview']).startswith(b'\x89PNG')
    assert calls == [('https://receiver.invalid/done', result, 'secret',
                      {'issuer': 'test', 'user_id': 42})]
    assert output.exists() is not removed
    assert upload.exists() is not removed


def test_missing_source(adapter, tmp_path):
    async def run():
        return [r async for r in adapter.FontBuilder().run({'output_dir': str(tmp_path)}, {})]
    with pytest.raises(ValueError, match='One of image_path or image_url'):
        asyncio.run(run())


def test_reject_non_http_download(adapter, tmp_path):
    with pytest.raises(ValueError, match='http or https'):
        adapter.download_image('file:///etc/passwd', tmp_path)
