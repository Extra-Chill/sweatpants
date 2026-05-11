# Audio Transcription with Speaker Diarization

A Sweatpants module for transcribing audio files with optional speaker identification and filler word removal.

## Features

- **Whisper Transcription**: OpenAI Whisper models (tiny → large)
- **Speaker Diarization**: PyAnnote audio speaker identification
- **Filler Word Removal**: Regex-based cleanup of um, uh, like, you know, etc.
- **Multiple Outputs**: TXT, JSON, SRT, VTT formats
- **Standalone Text Processing**: Clean existing transcripts without re-transcribing

## Installation

```bash
sweatpants module install ./audio-transcription
```

## Requirements

- FFmpeg (for audio conversion)
- Hugging Face token (for diarization)
  - Accept terms at https://huggingface.co/pyannote/speaker-diarization-community-1
  - Generate token at https://hf.co/settings/tokens

## Quick Start

### Complete Pipeline (Audio → Speakers + Clean Text)

```bash
sweatpants run audio-transcription \
  -i "audio_path=/path/to/interview.m4a" \
  -i "output_dir=/output/folder" \
  -i "model=large" \
  -i "diarize=true" \
  -i "remove_fillers=true" \
  -s "hf_token=YOUR_HF_TOKEN"
```

**Time**: ~3 hours (large model) + ~15 min (diarization)

### Cross-host: Fetch Audio from a URL

When the audio file lives on a different host (for example a WordPress media library), pass `audio_url` instead of `audio_path`. The module downloads the file into `output_dir`, runs the normal transcription pipeline, and deletes the downloaded source when the job finishes.

```bash
curl -X POST https://sweatpants.example.com/jobs \
  -H "Authorization: Bearer $SWEATPANTS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "module": "audio-transcription",
    "inputs": {
      "audio_url": "https://studio.extrachill.com/wp-content/uploads/2026/05/interview.mp3",
      "output_dir": "/var/sweatpants/output",
      "model": "large",
      "diarize": true,
      "remove_fillers": true
    },
    "settings": {"hf_token": "YOUR_HF_TOKEN"}
  }'
```

If the URL requires authentication, also set `audio_url_auth_header` (e.g. `"Bearer xxxxx"`). `audio_url` takes precedence over `audio_path` when both are provided.

## Workflow Options

### 1. Transcription Only (No Speakers)

Fastest option when you just need text:

```bash
sweatpants run audio-transcription \
  -i "audio_path=/path/to/audio.mp3" \
  -i "output_dir=/output/folder" \
  -i "model=large" \
  -i "diarize=false"
```

**Outputs**: `.whisper.txt`, `.whisper.json`, `.whisper.srt`, `.whisper.vtt`

**Time**: ~3 hours (large model)

### 2. Diarization Only (Existing Transcription)

When you already have Whisper output and just need speakers:

```bash
sweatpants run audio-transcription \
  -i "audio_path=/path/to/audio.m4a" \
  -i "output_dir=/output/folder" \
  -i "skip_transcription=true" \
  -i "diarize=true" \
  -s "hf_token=YOUR_HF_TOKEN"
```

**Uses**: Existing `whisper.json` from previous run
**Outputs**: `.speakers.txt`, `.speakers.json`, `.diarization.json`

**Time**: ~15 minutes

### 3. Filler Removal Only (Standalone)

Clean up existing transcript without touching audio:

```bash
sweatpants run audio-transcription \
  -i "text_input=/path/to/transcript.txt" \
  -i "output_dir=/output/folder" \
  -i "remove_fillers=true"
```

**Output**: `transcript.clean.txt`

**Time**: Instant

### 4. Re-diarization with Different Settings

Fine-tune speaker detection:

```bash
sweatpants run audio-transcription \
  -i "audio_path=/path/to/audio.m4a" \
  -i "output_dir=/output/folder" \
  -i "skip_transcription=true" \
  -i "diarize=true" \
  -i "min_speakers=2" \
  -i "max_speakers=4" \
  -s "hf_token=YOUR_HF_TOKEN"
```

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `audio_path` | text | Yes* | - | Path to audio file (mp3, m4a, wav, etc.) |
| `audio_url` | text | Yes* | - | HTTP(S) URL to fetch audio from. Downloaded into `output_dir` before transcription. Takes precedence over `audio_path`. |
| `audio_url_auth_header` | text | No | - | Optional `Authorization` header sent with `audio_url` request (e.g. `Bearer xxxxx`). |
| `output_dir` | text | Yes | - | Directory to save output files |
| `text_input` | text | Yes* | - | Process existing transcript (skips audio) |
| `model` | text | No | base | Whisper model: tiny, base, small, medium, large |
| `language` | text | No | en | Language code (en, es, auto) |
| `diarize` | boolean | No | true | Perform speaker diarization |
| `remove_fillers` | boolean | No | false | Remove filler words from transcript |
| `skip_transcription` | boolean | No | false | Skip Whisper (use existing whisper.json) |
| `min_speakers` | integer | No | 2 | Minimum speakers for diarization |
| `max_speakers` | integer | No | 10 | Maximum speakers for diarization |
| `callback_url` | text | No | - | HTTPS URL the module POSTs the completion result to. See "Completion Callback" below. |
| `callback_secret` | text | No | - | Shared HMAC-SHA256 secret used to sign the callback request. |
| `callback_issuer` | text | No | sweatpants | Opaque issuer string included as the `iss` claim in the signed callback token. |
| `callback_user_id` | integer | No | - | Subject claim (`sub`) — typically the receiving WordPress user_id. |
| `callback_cleanup_on_success` | boolean | No | true | When callback returns 2xx, delete upload dir + output dir. |

*Exactly one of `audio_url`, `audio_path`, or `text_input` must be provided.

## Completion Callback

For consumers that want fire-and-forget transcription (e.g. a browser tab
that doesn't want to poll for hours), set `callback_url` to an HTTPS
endpoint and the module will POST the completion result to that URL once
Whisper + diarization + filler removal are done.

**Request body** is JSON, identical to the result yielded to the
sweatpants scheduler:

```json
{
  "job_id": "<sweatpants job uuid>",
  "status": "complete",
  "files": { "transcription": "...", "transcription_json": "...", ... },
  "content": { "transcription": "And so, my fellow Americans...", ... },
  "stats": { "segments": 349, "speakers": null, "duration": 1380.0 }
}
```

**Signed authentication** (when `callback_secret` is set): the request
carries `Authorization: Bearer <signed_token>` where the token uses the
same HMAC-SHA256-over-base64url-payload format sweatpants core uses for
its own auth tokens. Receivers can validate it with the same verifier
they use for auth (e.g. WordPress + `wp-native-auth`'s
`wp_native_auth_verify_external_token`).

Token payload claims:

```json
{
  "iss": "<callback_issuer>",
  "sub": <callback_user_id>,
  "scope": "callback:write",
  "exp": <unix expiry, now + 300>,
  "jti": "<job_id>"
}
```

**Best-effort delivery**: a single POST with a 30-second timeout. Failures
are logged at WARNING level but never propagate to the job result — the
transcript remains available at `GET /jobs/{id}/results` for the
receiver to retry on their own schedule.

**Cleanup**: when `callback_cleanup_on_success=true` (the default) and
the receiver returns 2xx, the module deletes:

- The upload directory (`<uploads_dir>/<upload_id>/`) — source audio
- The output directory (`<output_dir>`) — transcript files

This keeps disk usage bounded for headless-compute pipelines where the
receiver becomes the new source of truth after the callback.

## Settings

| Setting | Type | Required | Description |
|---------|------|----------|-------------|
| `hf_token` | secret | For diarization | Hugging Face access token |

## Output Files

### Transcription Files
- `{base}.whisper.txt` - Plain text transcription
- `{base}.whisper.json` - Full Whisper data with timestamps
- `{base}.whisper.srt` - Subtitles format
- `{base}.whisper.vtt` - WebVTT format

### Speaker Files (if diarize=true)
- `{base}.speakers.txt` - Speaker-labeled transcript
- `{base}.speakers.json` - Combined data with speaker labels
- `{base}.diarization.json` - Raw PyAnnote diarization data

### Clean Files (if remove_fillers=true)
- `{base}.whisper.clean.txt` - Filler-free plain transcript (always produced when `remove_fillers=true`, independent of `diarize`)
- `{base}.speakers.clean.txt` - Filler-free speaker-labeled transcript (only when both `diarize=true` AND `remove_fillers=true`)

The three options (`model`, `diarize`, `remove_fillers`) are fully
independent. Filler removal runs as a post-processing pass over the
raw Whisper output regardless of whether speaker diarization also ran,
so you can ask for `(remove_fillers=true, diarize=false)` and get back
a clean monologue transcript without the diarization overhead.

### Inline Content in Job Results

Job results (returned by `GET /jobs/{id}/results`) include both the file
**paths** on the worker filesystem and the file **contents** inlined as
strings, keyed by the same labels:

```json
{
  "results": [{
    "data": {
      "status": "complete",
      "files": {
        "transcription": "/var/lib/sweatpants/output/.../foo.whisper.txt",
        "transcription_srt": "/var/lib/sweatpants/output/.../foo.whisper.srt"
      },
      "content": {
        "transcription": "And so, my fellow Americans, ask not...",
        "transcription_srt": "1\n00:00:00,000 --> 00:00:11,000\n..."
      }
    }
  }]
}
```

This lets cross-host clients consume transcripts directly from the API
without needing filesystem access to the worker. Files larger than 5 MB or
with non-text extensions are omitted from `content` (still listed under
`files`). The `files` paths remain authoritative — `content` is a
convenience for small-payload pipelines.

## Filler Words Removed

The `remove_fillers` option targets:

**Single words**: um, uh, like, actually, basically, literally, honestly, well, so, right, okay, hmm, err, ah, oh, just

**Phrases**: you know, I mean, kind of, sort of, or something, or whatever, and stuff, and everything, and all that

**Patterns**: it's like, just kind of, and then and then, yeah yeah yeah, just really, just definitely

**Transitions**: "you know?" → "." (with punctuation cleanup)

## Model Selection Guide

| Model | Speed | Quality | Use Case |
|-------|-------|---------|----------|
| tiny | ~2 min | Low | Quick tests |
| base | ~10 min | Medium | Drafts |
| small | ~30 min | Good | Blog posts |
| medium | ~90 min | Better | Important interviews |
| large | ~3 hours | Best | Published pieces |

*Times based on 16-minute audio on M4 Pro CPU

## Typical Workflow

### For a Published Interview

1. **First run**: Complete pipeline with large model
   ```bash
   sweatpants run audio-transcription \
     -i "audio_path=interview.m4a" \
     -i "output_dir=./output" \
     -i "model=large" \
     -i "diarize=true" \
     -i "remove_fillers=true" \
     -s "hf_token=$HF_TOKEN"
   ```

2. **Review**: Edit `.speakers.clean.txt` for final polish

3. **Publish**: Use cleaned transcript for article

### For Quick Drafts

1. **Transcribe only**: Skip diarization for speed
   ```bash
   sweatpants run audio-transcription \
     -i "audio_path=interview.m4a" \
     -i "output_dir=./output" \
     -i "model=medium" \
     -i "diarize=false"
   ```

2. **Edit**: Work with `.whisper.txt` directly

### For Re-processing

If transcription exists but you want speakers:

```bash
sweatpants run audio-transcription \
  -i "audio_path=interview.m4a" \
  -i "output_dir=./output" \
  -i "skip_transcription=true" \
  -i "diarize=true" \
  -s "hf_token=$HF_TOKEN"
```

## Limitations

- **Filler removal is regex-based**: Cannot distinguish "I like pizza" (verb) from "it's like cool" (filler). Review output for over-removal.
- **Speaker labels**: PyAnnote identifies voice clusters, not named individuals. Labels are SPEAKER_00, SPEAKER_01, etc.
- **MULTIPLE speakers**: Overlapping speech may be labeled as MULTIPLE
- **No GPU acceleration**: Runs on CPU (Apple Silicon Metal not supported by Whisper)

## Troubleshooting

**"403 Client Error" from Hugging Face**
- Ensure you've accepted terms at the model page
- Check HF token has read access

**"CUDA not available"**
- Normal on Mac, runs on CPU

**Merged words in clean output**
- Report specific examples for regex pattern improvements

## Development

### Adding New Filler Patterns

Edit `main.py`, `_remove_fillers()` method:

```python
patterns = [
    # Add your pattern
    (r'\s+your_filler\b', ' '),
    ...
]
```

### Testing Changes

```bash
sweatpants run audio-transcription \
  -i "text_input=/path/to/test.txt" \
  -i "output_dir=/tmp" \
  -i "remove_fillers=true"
```

## Version History

- **1.0.0**: Initial release
  - Whisper transcription (base model default)
  - Speaker diarization with PyAnnote community-1
  - Filler word removal
  - Standalone text processing mode
  - Multiple output formats

## License

MIT License - See LICENSE file
