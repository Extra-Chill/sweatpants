# Font Builder

A Sweatpants module that turns a photo or scan of a letter sheet into an
OpenType CFF (`.otf`), TrueType (`.ttf`) and PNG preview. No external tracer
binary, GPU or daemon is needed for the pure Python pipeline.

## Installation

```bash
sweatpants module install ./font-builder
```

Requirements are installed from `requirements.txt`: Pillow, NumPy, SciPy,
fontTools and potracer. The worker supplies the Sweatpants SDK with
`Module.send_signed_callback` support.

## Quick Start

For a sheet with three letters in each of two rows:

```bash
sweatpants run font-builder \
  -i 'image_path=/path/to/sheet.png' \
  -i 'output_dir=/output/font-job' \
  -i 'font_name=My Lettering' \
  -i 'glyph_map=A B C | a b c'
```

Use `image_path` for a local file or the path returned by `POST /uploads`.
For cross-host jobs, use `image_url` with an HTTP(S) image URL and optionally
`image_url_auth_header` (such as `Bearer xxxxx`). URL input takes precedence
over a local path. Downloads use a 300-second timeout and are always removed,
including when processing fails. Local sources are retained unless successful
callback cleanup applies.

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `image_path` | text | Yes* | - | Local source image path |
| `image_url` | text | Yes* | - | HTTP(S) source URL, takes precedence |
| `image_url_auth_header` | text | No | - | Authorization value for source download |
| `output_dir` | text | Yes | - | Dedicated per-job artifact directory |
| `font_name` | text | Yes | - | Family/full name, e.g. `GlobePrinting` |
| `glyph_map` | text | Yes | - | Names in sheet reading order |
| `threshold` | integer | No | 110 | Grayscale ink cutoff, 0–255 |
| `upscale` | integer | No | 8 | Positive bitmap enlargement factor |
| `cap_height` | integer | No | 700 | Target cap height in font units |
| `units_per_em` | integer | No | 1000 | Font em size, 16–16384 |
| `sidebearing` | integer | No | 35 | Nonnegative spacing on either side |
| `add_basic_punctuation` | boolean | No | true | Add missing `. , ' ’` and space |
| `callback_url` | text | No | - | Completion receiver URL |
| `callback_secret` | text | No | - | Shared HMAC-SHA256 signing secret |
| `callback_issuer` | text | No | sweatpants | Signed token `iss` claim |
| `callback_user_id` | integer | No | - | Signed token `sub` claim |
| `callback_cleanup_on_success` | boolean | No | true | Delete outputs and daemon-owned uploads after receiver ACK |

*At least one of `image_path` or `image_url` is required.

Family names may contain ASCII letters, numbers, spaces, hyphens and
underscores. Spaces are removed for filenames and the PostScript name,
which ends in `-Regular`.

## Glyph Map

Rows are separated by newlines or `|`; names within rows by whitespace:

```text
A a A.alt B b C c
D d E e E.alt F f
```

Names must be unique. Single characters map to their Unicode codepoint;
standard Adobe names such as `ampersand`, `exclam`, `question`, `period`,
`comma`, `quotesingle`, `quoteright` and `space` map to the corresponding
characters. Names ending in `.alt` are unencoded alternates and require a
base glyph: `A.alt` creates `sub A by A.alt` under both `salt` and `ss01`.
Enable stylistic alternates in a supporting application to use them.

Every detected cell must have exactly one name. A mismatch reports all
detected row counts and expected counts, for example:
`glyph_map mismatch: detected count per row [3, 3]; expected [2, 1]`.
Supplied punctuation is preserved; synthesized punctuation only fills gaps.
The reported glyph total includes `.notdef`, space and any synthesized glyphs.

## Output Files and Completion Callback

Files are named `{FamilyWithoutSpaces}-Regular.otf`, `.ttf` and `.png`.
The final yielded result has this shape:

```json
{
  "status": "complete",
  "files": {"otf": "/output/MyFont-Regular.otf", "ttf": "/output/MyFont-Regular.ttf", "preview": "/output/MyFont-Regular.png"},
  "content": {"otf": "<base64>", "ttf": "<base64>", "preview": "<base64>"},
  "stats": {"glyphs": 13, "rows": [3, 3]}
}
```

Like audio-transcription, `content` is keyed by the same labels as `files`.
Unlike its UTF-8 transcripts, these three artifacts are binary: **all content
values are standard base64**, decoded by the receiver before saving. The
preview renders uppercase, lowercase and a sample sentence; characters not
in the map display the font's `.notdef` placeholder.

The SDK `Module.send_signed_callback` posts the same result, adds `job_id`,
and handles signing and best-effort delivery. With a secret, the Authorization
Bearer token uses Sweatpants' HMAC-SHA256-over-base64url-payload format,
`scope=callback:write`, issuer/subject inputs, a 300-second expiry and the job
ID as `jti`. A failed callback does not fail the job or remove its outputs.

When the receiver returns 2xx and cleanup is enabled, the module deletes the
output directory and a source upload directory only if it matches the daemon
layout `uploads/<32-lowercase-hex-id>/`. Other local sources are untouched.
Use a **dedicated output directory**, not a shared directory; set
`callback_cleanup_on_success=false` to retain files. All binary content is
inlined so an acknowledging receiver can retain the artifacts before cleanup.

## Algorithm and Limitations

- Grayscale ink projection finds rows taller than 15 pixels, padded by six.
- Three-iteration column dilation joins nearby components into cells wider
  than eight pixels. Components smaller than 25 pixels are discarded.
- Two-pixel padded glyph crops are enlarged with LANCZOS, blurred at
  `0.6 × upscale`, and thresholded at 128.
- Median row bottoms establish baselines; median glyph height establishes
  cap-height scaling. The tracer uses `turdsize=40`, `alphamax=1.0`,
  `opticurve=True`, `opttolerance=0.3`.
- **Inverted bitmap gotcha:** potracer must receive `potrace.Bitmap(~bitmap)`.
  Giving it the ink mask directly traces the background and produces filled
  boxes with knocked-out letters. Tests check both rendered coverage and
  outline bounds to catch this regression.
- fontTools builds CFF OTF and quadratic TTF (Cu2Qu, error 1.0, reversed
  direction), with unrestricted embedding (`fsType=0`), ascent 900 and
  descent −250.

Use a high-contrast, straight, well-spaced sheet with aligned rows. This is
projection segmentation, not OCR or perspective correction: touching letters,
strong shadows, tiny punctuation or disconnected marks may need image cleanup
or a threshold adjustment. Fixed component/row cutoffs favor substantial
letter sheets, not small text. Preview missing characters are expected when
only a subset of the alphabet was supplied.

## Development

`pipeline.py` exposes `segment`, `trace`, `build_font` and `render_preview`;
these operate on Pillow images, arrays and bytes without filesystem writes
or importing Sweatpants. `main.py` is the daemon adapter for downloads,
artifact persistence and callbacks.

```bash
cd font-builder
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest -q
```

Tests draw a two-row sheet using Pillow's bundled font. No network, daemon,
system font installation or external image fixture is required.
