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

*Exactly one of `audio_url`, `audio_path`, or `text_input` must be provided.

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
- `{base}.speakers.clean.txt` - Filler-free speaker transcript

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
