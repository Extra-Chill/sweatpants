"""Audio Transcription with Speaker Diarization module for Sweatpants.

Handles audio file conversion, Whisper transcription, and PyAnnote speaker diarization.
"""

# Patch torchaudio for pyannote.audio compatibility (torchaudio 2.x removed these functions)
import torchaudio
if not hasattr(torchaudio, 'set_audio_backend'):
    torchaudio.set_audio_backend = lambda x: None
if not hasattr(torchaudio, 'list_audio_backends'):
    torchaudio.list_audio_backends = lambda: ['soundfile']

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np
import whisper
from pyannote.audio import Pipeline

from sweatpants import Module


class AudioTranscription(Module):
    """Transcribe audio with speaker identification."""

    async def run(
        self, inputs: dict[str, Any], settings: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Execute transcription pipeline.
        
        Args:
            inputs: audio_path, output_dir, model, language, diarize, min_speakers, max_speakers
            settings: hf_token (for diarization)
        """
        audio_path = Path(inputs["audio_path"]) if inputs.get("audio_path") else None
        output_dir = Path(inputs["output_dir"])
        model_size = inputs.get("model", "base")
        language = inputs.get("language", "en")
        should_diarize = inputs.get("diarize", True)
        min_speakers = inputs.get("min_speakers", 2)
        max_speakers = inputs.get("max_speakers", 10)
        skip_transcription = inputs.get("skip_transcription", False)
        remove_fillers = inputs.get("remove_fillers", False)
        text_input = inputs.get("text_input")
        hf_token = settings.get("hf_token") or os.environ.get("HF_TOKEN")
        
        # Standalone text processing mode
        if text_input:
            text_path = Path(text_input)
            if not text_path.exists():
                raise FileNotFoundError(f"Text file not found: {text_path}")
            
            await self.log(f"Processing existing transcript: {text_path.name}")
            
            # Read the input file
            with open(text_path, 'r') as f:
                content = f.read()
            
            # Apply filler removal
            if remove_fillers:
                clean_content = self._remove_fillers(content)
                
                # Determine output path
                output_path = output_dir / f"{text_path.stem}.clean.txt"
                with open(output_path, 'w') as f:
                    f.write(clean_content)
                
                await self.log(f"Clean transcript saved: {output_path}")
                
                yield {
                    "status": "complete",
                    "files": {
                        "input": str(text_path),
                        "output": str(output_path),
                    },
                    "stats": {
                        "original_chars": len(content),
                        "clean_chars": len(clean_content),
                        "reduction": len(content) - len(clean_content),
                    },
                }
            else:
                await self.log("No text processing requested (set remove_fillers=true)")
                yield {
                    "status": "complete",
                    "files": {"input": str(text_path)},
                    "message": "No processing requested",
                }
            
            return
        
        if audio_path is None:
            raise ValueError("audio_path is required unless using text_input mode")
        
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate output filename
        base_name = audio_path.stem
        output_base = output_dir / base_name

        await self.log(f"Starting transcription of {audio_path.name}")
        await self.log(f"Using Whisper model: {model_size}")
        await self.save_checkpoint(stage="started", audio_file=str(audio_path))

        # Step 1: Convert to WAV if needed
        wav_path = await self._convert_to_wav(audio_path)
        if not wav_path:
            raise RuntimeError("Failed to convert audio to WAV format")
        
        await self.log(f"Audio converted to: {wav_path}")
        await self.save_checkpoint(stage="converted", wav_path=str(wav_path))

        # Step 2: Transcribe with Whisper (or load existing)
        whisper_txt = output_base.with_suffix(".whisper.txt")
        whisper_json = output_base.with_suffix(".whisper.json")
        whisper_srt = output_base.with_suffix(".whisper.srt")
        whisper_vtt = output_base.with_suffix(".whisper.vtt")
        
        # Check for existing transcription
        if skip_transcription and whisper_json.exists():
            await self.log("Loading existing transcription (skip_transcription=true)")
            with open(whisper_json) as f:
                result = json.load(f)
            await self.log(f"Loaded existing transcription: {len(result['segments'])} segments")
        else:
            await self.log("Loading Whisper model...")
            model = await asyncio.to_thread(whisper.load_model, model_size)
            
            await self.log("Transcribing audio...")
            result = await asyncio.to_thread(
                model.transcribe,
                str(wav_path),
                language=None if language == "auto" else language,
                verbose=False,
            )
            
            # Save Whisper output
            with open(whisper_txt, "w") as f:
                f.write(result["text"])
            
            with open(whisper_json, "w") as f:
                json.dump(result, f, indent=2)
            
            with open(whisper_srt, "w") as f:
                f.write(self._to_srt(result["segments"]))
            
            with open(whisper_vtt, "w") as f:
                f.write(self._to_vtt(result["segments"]))
            
            await self.log(f"Whisper transcription complete")
        
        await self.save_checkpoint(
            stage="transcribed",
            text_file=str(whisper_txt),
            segments=len(result["segments"]),
        )

        # Step 3: Speaker diarization (if enabled)
        diarization_data = None
        diarization_json = None
        if should_diarize:
            if not hf_token:
                await self.log(
                    "Warning: HF token not configured, skipping diarization", 
                    level="WARNING"
                )
            else:
                try:
                    await self.log("Starting speaker diarization...")
                    diarization_data = await self._diarize(
                        wav_path, hf_token, min_speakers, max_speakers
                    )
                    
                    # Save diarization results
                    diarization_json = output_base.with_suffix(".diarization.json")
                    with open(diarization_json, "w") as f:
                        json.dump(diarization_data, f, indent=2)
                    
                    await self.log(f"Diarization complete: {len(diarization_data)} segments")
                    await self.save_checkpoint(
                        stage="diarized", 
                        speakers=len(set(s["speaker"] for s in diarization_data))
                    )
                except Exception as e:
                    await self.log(f"Diarization failed: {e}", level="ERROR")

        # Step 4: Combine transcription with speaker labels
        if diarization_data:
            combined = self._combine_with_speakers(result["segments"], diarization_data)
            combined_txt = output_base.with_suffix(".speakers.txt")
            combined_json = output_base.with_suffix(".speakers.json")
            
            # Apply filler removal if requested
            combined_txt_clean = None
            if remove_fillers:
                combined_clean = []
                for seg in combined:
                    seg_clean = seg.copy()
                    seg_clean["text"] = self._remove_fillers(seg["text"])
                    combined_clean.append(seg_clean)
                
                # Write clean version
                combined_txt_clean = output_base.with_suffix(".speakers.clean.txt")
                with open(combined_txt_clean, "w") as f:
                    f.write(self._format_speaker_text(combined_clean))
                
                # Also write original
                with open(combined_txt, "w") as f:
                    f.write(self._format_speaker_text(combined))
                
                await self.log(f"Clean transcript (fillers removed) saved")
            else:
                with open(combined_txt, "w") as f:
                    f.write(self._format_speaker_text(combined))
            
            with open(combined_json, "w") as f:
                json.dump(combined, f, indent=2)
            
            await self.log(f"Speaker-separated transcription saved")
            await self.save_checkpoint(stage="complete", has_speakers=True)
            
            output_files = {
                "transcription": str(whisper_txt),
                "transcription_json": str(whisper_json),
                "transcription_srt": str(whisper_srt),
                "transcription_vtt": str(whisper_vtt),
                "diarization": str(diarization_json),
                "combined_txt": str(combined_txt),
                "combined_json": str(combined_json),
            }
            
            if remove_fillers and combined_txt_clean:
                output_files["combined_txt_clean"] = str(combined_txt_clean)
            
            yield {
                "status": "complete",
                "files": output_files,
                "stats": {
                    "segments": len(result["segments"]),
                    "speakers": len(set(s["speaker"] for s in diarization_data)),
                    "duration": result["segments"][-1]["end"] if result["segments"] else 0,
                },
            }
        else:
            await self.save_checkpoint(stage="complete", has_speakers=False)
            
            yield {
                "status": "complete",
                "files": {
                    "transcription": str(whisper_txt),
                    "transcription_json": str(whisper_json),
                    "transcription_srt": str(whisper_srt),
                    "transcription_vtt": str(whisper_vtt),
                },
                "stats": {
                    "segments": len(result["segments"]),
                    "speakers": None,
                    "duration": result["segments"][-1]["end"] if result["segments"] else 0,
                },
            }

        # Cleanup temp file
        if wav_path != audio_path and wav_path.suffix == ".wav":
            wav_path.unlink(missing_ok=True)
            await self.log("Temporary files cleaned up")

    async def _convert_to_wav(self, audio_path: Path) -> Path | None:
        """Convert audio file to WAV format if needed."""
        if audio_path.suffix.lower() == ".wav":
            return audio_path
        
        wav_path = audio_path.with_suffix(".wav")
        
        cmd = [
            "ffmpeg",
            "-i", str(audio_path),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            "-y",
            str(wav_path)
        ]
        
        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0 and wav_path.exists():
                return wav_path
            else:
                return None
        except Exception as e:
            await self.log(f"FFmpeg conversion failed: {e}", level="ERROR")
            return None

    async def _diarize(self, wav_path: Path, hf_token: str, min_speakers: int, max_speakers: int) -> list[dict]:
        """Perform speaker diarization using PyAnnote community-1."""
        os.environ["HF_TOKEN"] = hf_token
        
        def _run_diarization():
            pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=hf_token,
            )
            
            output = pipeline(str(wav_path))
            
            results = []
            for turn, speaker in output.speaker_diarization:
                results.append({
                    "speaker": speaker,
                    "start": turn.start,
                    "end": turn.end,
                })
            
            return results
        
        return await asyncio.to_thread(_run_diarization)

    def _combine_with_speakers(
        self, 
        segments: list[dict], 
        diarization: list[dict]
    ) -> list[dict]:
        """Combine Whisper segments with speaker labels."""
        combined = []

        for seg in segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            seg_text = seg["text"].strip()

            # Find speakers for this segment
            speakers = set()
            for d in diarization:
                # Check if diarization segment overlaps with transcription segment
                if d["start"] < seg_end and d["end"] > seg_start:
                    speakers.add(d["speaker"])

            # Use most common speaker or "UNKNOWN"
            speaker = list(speakers)[0] if len(speakers) == 1 else (
                "MULTIPLE" if len(speakers) > 1 else "UNKNOWN"
            )

            combined.append({
                "start": seg_start,
                "end": seg_end,
                "text": seg_text,
                "speaker": speaker,
            })

        return combined

    def _format_speaker_text(self, combined: list[dict]) -> str:
        """Format combined segments as readable text."""
        lines = []
        current_speaker = None
        current_text = []

        for seg in combined:
            if seg["speaker"] != current_speaker:
                if current_speaker and current_text:
                    lines.append(f"[{current_speaker}] {' '.join(current_text)}")
                current_speaker = seg["speaker"]
                current_text = []

            current_text.append(seg["text"])

        if current_speaker and current_text:
            lines.append(f"[{current_speaker}] {' '.join(current_text)}")

        return "\n\n".join(lines)

    def _to_srt(self, segments: list[dict]) -> str:
        """Convert segments to SRT format."""
        lines = []
        for i, seg in enumerate(segments, 1):
            start = self._format_time(seg["start"])
            end = self._format_time(seg["end"])
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"].strip())
            lines.append("")
        return "\n".join(lines)

    def _remove_fillers(self, text: str) -> str:
        """Remove filler words from transcript text.
        
        Removes common filler words while preserving meaning and flow.
        """
        import re
        
        # Define filler word patterns
        # More aggressive patterns first, then simpler ones
        patterns = [
            # Multi-word fillers (more specific first)
            (r'\byou know[,\s]*\s*', ''),  # "you know, " or "you know "
            (r'\bI mean[,\s]*\s*', ''),    # "I mean, " or "I mean "
            (r'\bkind of\s+', ''),          # "kind of " (when used as filler)
            (r'\bsort of\s+', ''),          # "sort of "
            
            # Single word fillers with context clues
            (r'\s+um[,\s]*', ' '),          # " um" or "um, "
            (r'\s+uh[,\s]*', ' '),          # " uh" or "uh, "
            (r'\s+like[,\s]+', ' '),        # " like " or "like, " - careful with this
            (r'^like\s+', ''),               # "Like " at start
            (r'\s+actually[,\s]*', ' '),     # " actually"
            (r'\s+basically[,\s]*', ' '),   # " basically"
            (r'\s+literally[,\s]*', ' '),   # " literally"
            (r'\s+honestly[,\s]*', ' '),    # " honestly"
            (r'\s+well[,\s]+', ' '),         # " well, "
            (r'^well[,\s]+', ''),            # "Well, " at start
            (r'\s+so[,\s]+', ' '),           # " so, " - careful
            (r'\s+right[,\?\s]*', ' '),      # " right" or "right?"
            (r'\s+okay[,\s]+', ' '),         # " okay, "
            (r'^okay[,\s]+', ''),            # "Okay, " at start
            (r'\s+hmm[,\s]*', ' '),         # " hmm"
            (r'\s+err[,\s]*', ' '),          # " err"
            (r'\s+ah[,\s]*', ' '),           # " ah"
            (r'\s+oh[,\s]+', ' '),           # " oh, "
        ]
        
        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        # Clean up double spaces and trim
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'\s+([,.!?])', r'\1', result)  # Remove space before punctuation
        result = re.sub(r'([,.!?])\s+', r'\1 ', result)    # Ensure space after punctuation
        result = result.strip()
        
        return result

    def _to_vtt(self, segments: list[dict]) -> str:
        """Convert segments to WebVTT format."""
        lines = ["WEBVTT", ""]
        for seg in segments:
            start = self._format_vtt_time(seg["start"])
            end = self._format_vtt_time(seg["end"])
            lines.append(f"{start} --> {end}")
            lines.append(seg["text"].strip())
            lines.append("")
        return "\n".join(lines)

    def _format_vtt_time(self, seconds: float) -> str:
        """Format seconds as WebVTT timecode."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def _format_time(self, seconds: float) -> str:
        """Format seconds as SRT timecode."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
