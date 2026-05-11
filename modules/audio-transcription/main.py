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
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from urllib.parse import urlparse

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
        audio_url = inputs.get("audio_url")
        audio_url_auth_header = inputs.get("audio_url_auth_header")
        output_dir = Path(inputs["output_dir"])
        model_size = inputs.get("model", "base")
        language = inputs.get("language", "en")
        should_diarize = inputs.get("diarize", True)
        min_speakers = inputs.get("min_speakers", 2)
        max_speakers = inputs.get("max_speakers", 10)
        skip_transcription = inputs.get("skip_transcription", False)
        remove_fillers = inputs.get("remove_fillers", False)
        text_input = inputs.get("text_input")
        callback_url = inputs.get("callback_url")
        callback_secret = inputs.get("callback_secret")
        callback_issuer = inputs.get("callback_issuer", "sweatpants")
        callback_user_id = inputs.get("callback_user_id")
        callback_cleanup = bool(inputs.get("callback_cleanup_on_success", True))
        hf_token = settings.get("hf_token") or os.environ.get("HF_TOKEN")

        # Track downloaded source for cleanup at end of job
        downloaded_audio_path: Path | None = None
        
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
                
                output_files = {
                    "input": str(text_path),
                    "output": str(output_path),
                }
                yield {
                    "status": "complete",
                    "files": output_files,
                    "content": self._read_inline_content(output_files),
                    "stats": {
                        "original_chars": len(content),
                        "clean_chars": len(clean_content),
                        "reduction": len(content) - len(clean_content),
                    },
                }
            else:
                await self.log("No text processing requested (set remove_fillers=true)")
                output_files = {"input": str(text_path)}
                yield {
                    "status": "complete",
                    "files": output_files,
                    "content": self._read_inline_content(output_files),
                    "message": "No processing requested",
                }
            
            return
        
        if audio_url is None and audio_path is None:
            raise ValueError(
                "One of audio_url, audio_path, or text_input is required"
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        # If audio_url is provided, fetch it and use it as the effective audio_path.
        # audio_url takes precedence over audio_path when both are set.
        if audio_url:
            downloaded_audio_path = await self._download_audio_url(
                audio_url, output_dir, audio_url_auth_header
            )
            audio_path = downloaded_audio_path

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
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
        whisper_clean_txt = output_base.with_suffix(".whisper.clean.txt")
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
        
        # Step 2.5: Filler removal on the raw whisper output
        # Produces whisper.clean.txt regardless of whether diarization runs.
        # This is the decoupled filler-removal pass — every transcript can be
        # cleaned, not just speaker-labeled ones. The diarize branch below
        # produces an additional speakers.clean.txt when both options are on.
        if remove_fillers:
            cleaned_text = self._remove_fillers(result["text"])
            with open(whisper_clean_txt, "w") as f:
                f.write(cleaned_text)
            await self.log(f"Filler-removed transcript saved: {whisper_clean_txt.name}")
        
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

        # Step 4: Combine transcription with speaker labels (when diarization ran)
        if diarization_data:
            combined = self._combine_with_speakers(result["segments"], diarization_data)
            combined_txt = output_base.with_suffix(".speakers.txt")
            combined_json = output_base.with_suffix(".speakers.json")
            
            # Always write the speaker-labeled transcript when we have one.
            with open(combined_txt, "w") as f:
                f.write(self._format_speaker_text(combined))
            with open(combined_json, "w") as f:
                json.dump(combined, f, indent=2)
            await self.log(f"Speaker-separated transcription saved")
            
            # When filler removal is also on, produce the speakers.clean.txt
            # variant alongside. The whisper.clean.txt was already written
            # above (decoupled filler-removal pass); this adds the
            # speaker-labeled clean version for a fully-processed output.
            combined_txt_clean = None
            if remove_fillers:
                combined_clean = []
                for seg in combined:
                    seg_clean = seg.copy()
                    seg_clean["text"] = self._remove_fillers(seg["text"])
                    combined_clean.append(seg_clean)
                combined_txt_clean = output_base.with_suffix(".speakers.clean.txt")
                with open(combined_txt_clean, "w") as f:
                    f.write(self._format_speaker_text(combined_clean))
                await self.log(f"Speaker-labeled filler-removed transcript saved")
            
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
            if remove_fillers:
                output_files["transcription_clean"] = str(whisper_clean_txt)
            if remove_fillers and combined_txt_clean:
                output_files["combined_txt_clean"] = str(combined_txt_clean)
            
            final_result = {
                "status": "complete",
                "files": output_files,
                "content": self._read_inline_content(output_files),
                "stats": {
                    "segments": len(result["segments"]),
                    "speakers": len(set(s["speaker"] for s in diarization_data)),
                    "duration": result["segments"][-1]["end"] if result["segments"] else 0,
                },
            }
            yield final_result
        else:
            # No diarization. Surface the raw whisper outputs and the
            # filler-removed variant if it was produced above.
            await self.save_checkpoint(stage="complete", has_speakers=False)

            output_files = {
                "transcription": str(whisper_txt),
                "transcription_json": str(whisper_json),
                "transcription_srt": str(whisper_srt),
                "transcription_vtt": str(whisper_vtt),
            }
            if remove_fillers:
                output_files["transcription_clean"] = str(whisper_clean_txt)

            final_result = {
                "status": "complete",
                "files": output_files,
                "content": self._read_inline_content(output_files),
                "stats": {
                    "segments": len(result["segments"]),
                    "speakers": None,
                    "duration": result["segments"][-1]["end"] if result["segments"] else 0,
                },
            }
            yield final_result

        # Fire the completion callback (if configured) BEFORE local cleanup so
        # the receiver gets the file paths in case it wants to ACK before we
        # delete them. The callback is best-effort: a failure is logged but
        # never propagated to the job result.
        callback_acknowledged = False
        if callback_url:
            callback_acknowledged = await self._fire_completion_callback(
                callback_url=callback_url,
                callback_secret=callback_secret,
                callback_issuer=callback_issuer,
                callback_user_id=callback_user_id,
                payload=final_result,
            )

        # Cleanup ffmpeg-converted wav file (always — it's a derived artifact).
        if wav_path != audio_path and wav_path.suffix == ".wav":
            wav_path.unlink(missing_ok=True)
            await self.log("Temporary wav cleaned up")

        # Cleanup downloaded source file from audio_url mode (always — same).
        if downloaded_audio_path is not None and downloaded_audio_path.exists():
            downloaded_audio_path.unlink(missing_ok=True)
            await self.log(f"Downloaded source file cleaned up: {downloaded_audio_path.name}")

        # Cleanup the upload dir + the entire output dir IF the consumer ACKed
        # the callback (meaning they captured the transcript and don't need
        # the files anymore). Skipped when callback_cleanup_on_success=false
        # so callers can opt out.
        if callback_acknowledged and callback_cleanup:
            await self._cleanup_after_callback(
                audio_path=audio_path,
                output_dir=output_dir,
            )

    # Maximum number of bytes to inline per text artifact in the result payload.
    # Files larger than this are still produced on disk and listed in `files`,
    # but skipped from the inlined `content` map. 5 MB is generous for transcripts
    # (a 10-hour interview is roughly 1 MB of plain text) but keeps result rows
    # bounded if a future module produces unusually large artifacts.
    _MAX_INLINE_CONTENT_BYTES = 5 * 1024 * 1024

    # File extensions that are safe to inline as UTF-8 text. Other extensions
    # (e.g. binary diarization JSONs that are technically text but verbose, or
    # SRT/VTT which are useful but secondary) are NOT inlined by default — they
    # remain on disk for clients that want them via a future artifact-fetch path.
    _INLINE_TEXT_EXTENSIONS = (".txt", ".srt", ".vtt", ".json")

    def _read_inline_content(self, file_paths: dict[str, str]) -> dict[str, str]:
        """Read text artifacts into a content map keyed by the same labels as files.

        Reads each path under `file_paths`, returning a dict with the same keys.
        Files larger than `_MAX_INLINE_CONTENT_BYTES` are skipped (the key is
        omitted from the result, not nulled). Files that fail to read for any
        reason (missing, permission denied, decode error) are also skipped.

        This lets cross-host clients consume transcripts directly from the
        results endpoint without needing filesystem access to the worker. The
        on-disk files remain authoritative; this map is a convenience for
        small-payload pipelines.

        Args:
            file_paths: Map of label → absolute path on the worker filesystem.

        Returns:
            Map of label → file contents (str), with skipped files omitted.
        """
        content: dict[str, str] = {}
        for label, path_str in file_paths.items():
            try:
                p = Path(path_str)
                if not p.exists():
                    continue
                if p.suffix.lower() not in self._INLINE_TEXT_EXTENSIONS:
                    continue
                size = p.stat().st_size
                if size > self._MAX_INLINE_CONTENT_BYTES:
                    continue
                content[label] = p.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                # Best-effort inlining; failure to inline is not a job failure.
                continue
        return content

    # -----------------------------------------------------------------
    # Completion callback
    # -----------------------------------------------------------------

    @staticmethod
    def _b64url_encode(b: bytes) -> str:
        """Encode bytes as base64url without padding (matches sweatpants core)."""
        return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

    @classmethod
    def _sign_callback_token(
        cls,
        secret: str,
        issuer: str,
        sub: Optional[int],
        job_id: str,
        ttl_seconds: int = 300,
    ) -> str:
        """Mint a sweatpants-compatible signed bearer token.

        Format matches sweatpants core's `_verify_signed_token` (see
        `sweatpants/api/auth.py`) and the WP-native-auth verifier, so a
        receiving site can validate the callback with the existing
        `wp_native_auth_verify_external_token` primitive against the same
        shared HMAC secret.

        Token shape: <base64url(payload_json)>.<base64url(hmac_sha256(secret, payload_b64))>

        Payload claims:
          iss     issuer string (default "sweatpants")
          sub     subject — typically the WP user_id who submitted the job
          scope   "callback:write" — a fixed scope so receivers can gate
          exp     unix expiry, default now + 300s (callbacks should be near-instant)
          jti     unique token id, populated with the job_id for trace
        """
        payload = {
            "iss": issuer,
            "sub": int(sub) if sub is not None else 0,
            "scope": "callback:write",
            "exp": int(time.time()) + ttl_seconds,
            "jti": job_id,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_b64 = cls._b64url_encode(payload_json.encode("utf-8"))
        sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        sig_b64 = cls._b64url_encode(sig)
        return f"{payload_b64}.{sig_b64}"

    async def _fire_completion_callback(
        self,
        callback_url: str,
        callback_secret: Optional[str],
        callback_issuer: str,
        callback_user_id: Optional[int],
        payload: dict[str, Any],
    ) -> bool:
        """POST the completion payload to the configured callback URL.

        Best-effort delivery: a single POST with a 30s timeout. Failures are
        logged at WARNING level but never propagated — the transcript
        remains available via `GET /jobs/{id}/results` if the receiver wants
        to retry on their own schedule.

        When `callback_secret` is set, the request carries an
        `Authorization: Bearer <signed_token>` header with the same
        HMAC-SHA256 shape sweatpants core uses for its own signed tokens,
        so the receiver can use one verifier for both auth and callbacks.

        Args:
            callback_url: HTTPS endpoint to POST to.
            callback_secret: Shared HMAC secret. None disables signing.
            callback_issuer: `iss` claim in the signed payload.
            callback_user_id: `sub` claim — the WP user the callback represents.
            payload: The final result dict already yielded to the scheduler.

        Returns:
            True iff the receiver returned a 2xx status. Callers may use
            this signal to gate cleanup of source/output files.
        """
        # Augment the body with the job_id so receivers can correlate.
        # `self.job_id` is populated by the sweatpants Module base class.
        body_dict = {
            "job_id": getattr(self, "job_id", None),
            **payload,
        }
        body_bytes = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if callback_secret:
            token = self._sign_callback_token(
                secret=callback_secret,
                issuer=callback_issuer,
                sub=callback_user_id,
                job_id=str(body_dict.get("job_id") or "unknown"),
            )
            headers["Authorization"] = f"Bearer {token}"

        await self.log(f"Firing completion callback → {callback_url}")

        request = urllib.request.Request(
            callback_url,
            data=body_bytes,
            headers=headers,
            method="POST",
        )

        def _do_request() -> tuple[int, str]:
            try:
                with urllib.request.urlopen(request, timeout=30) as resp:
                    return resp.status, ""
            except urllib.error.HTTPError as exc:
                # Read at most 1 KB of the error body for the log.
                detail = exc.read(1024).decode("utf-8", errors="replace") if exc.fp else ""
                return exc.code, detail

        try:
            status, detail = await asyncio.to_thread(_do_request)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            await self.log(
                f"Completion callback failed (network): {exc}",
                level="WARNING",
            )
            return False
        except Exception as exc:  # pragma: no cover — defensive
            await self.log(
                f"Completion callback failed (unexpected): {exc!r}",
                level="WARNING",
            )
            return False

        if 200 <= status < 300:
            await self.log(f"Completion callback acknowledged (HTTP {status})")
            return True

        await self.log(
            f"Completion callback returned HTTP {status}: {detail[:200]}",
            level="WARNING",
        )
        return False

    async def _cleanup_after_callback(
        self,
        audio_path: Optional[Path],
        output_dir: Path,
    ) -> None:
        """Delete the upload dir + the entire output dir after a successful callback.

        Only invoked when `callback_cleanup_on_success` is true AND the
        callback POST returned 2xx. The transcript content is already in the
        receiver's hands by that point; on-disk copies are redundant and
        eating storage on the worker host.

        Failures during cleanup are logged but never raised — the job has
        already succeeded as far as the scheduler is concerned.
        """
        # Delete the entire upload directory (the upload_id-scoped tempdir
        # created by POST /uploads). If the audio came from a local path
        # outside that layout we leave it alone — the convention is
        # "sweatpants owns what sweatpants created."
        try:
            if audio_path is not None:
                upload_dir = audio_path.parent
                # Only delete if it's a uuid-hex dir under .../uploads/
                if (
                    upload_dir.parent.name == "uploads"
                    and len(upload_dir.name) == 32
                    and all(c in "0123456789abcdef" for c in upload_dir.name)
                ):
                    shutil.rmtree(upload_dir, ignore_errors=True)
                    await self.log(f"Upload dir cleaned up: {upload_dir}")
        except Exception as exc:
            await self.log(f"Upload cleanup failed: {exc!r}", level="WARNING")

        # Delete the output directory wholesale. The receiver acked the
        # callback containing the inlined content, so the files on disk are
        # no longer needed.
        try:
            if output_dir.is_dir():
                shutil.rmtree(output_dir, ignore_errors=True)
                await self.log(f"Output dir cleaned up: {output_dir}")
        except Exception as exc:
            await self.log(f"Output cleanup failed: {exc!r}", level="WARNING")

    async def _download_audio_url(
        self,
        audio_url: str,
        output_dir: Path,
        auth_header: str | None = None,
    ) -> Path:
        """Download audio from a URL into output_dir.

        Streams the response to disk in chunks and logs progress every 5 MB.
        Uses urllib (stdlib only). 30s connect timeout, 5 min read timeout.

        Args:
            audio_url: HTTP(S) URL to fetch.
            output_dir: Directory to write the downloaded file into.
            auth_header: Optional Authorization header value (e.g. "Bearer xxx").

        Returns:
            Path to the downloaded file.

        Raises:
            RuntimeError: If the download fails or yields a 0-byte file.
        """
        parsed = urlparse(audio_url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError(
                f"audio_url must be http or https, got: {parsed.scheme!r}"
            )

        # Derive a filename from the URL path; fall back to a generic name.
        url_basename = os.path.basename(parsed.path) or "audio_url_download"
        # Strip query strings already excluded by parsed.path; sanitize separators.
        url_basename = url_basename.replace("/", "_").replace("\\", "_")
        if not url_basename:
            url_basename = "audio_url_download"

        output_dir.mkdir(parents=True, exist_ok=True)
        dest_path = output_dir / url_basename

        await self.log(f"Downloading audio from URL: {audio_url}")

        def _do_download() -> int:
            req = urllib.request.Request(audio_url)
            if auth_header:
                req.add_header("Authorization", auth_header)
            # 30s connect / 5 min read; urllib uses a single timeout for both.
            # Use the larger value so reads on slow links still succeed.
            with urllib.request.urlopen(req, timeout=300) as response:
                if getattr(response, "status", 200) >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status} fetching audio_url: {audio_url}"
                    )
                bytes_written = 0
                chunk_size = 1024 * 1024  # 1 MB read chunks
                next_log_threshold = 5 * 1024 * 1024  # log every 5 MB
                with open(dest_path, "wb") as out:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out.write(chunk)
                        bytes_written += len(chunk)
                        if bytes_written >= next_log_threshold:
                            # Schedule a log emit on the main loop without
                            # blocking the worker thread.
                            asyncio.run_coroutine_threadsafe(
                                self.log(
                                    f"Downloaded {bytes_written / (1024 * 1024):.1f} MB..."
                                ),
                                loop,
                            )
                            next_log_threshold += 5 * 1024 * 1024
            return bytes_written

        loop = asyncio.get_running_loop()
        try:
            bytes_written = await asyncio.to_thread(_do_download)
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"HTTP {e.code} fetching audio_url ({audio_url}): {e.reason}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Network error fetching audio_url ({audio_url}): {e.reason}"
            ) from e
        except TimeoutError as e:
            raise RuntimeError(
                f"Timeout fetching audio_url ({audio_url}): {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Failed to download audio_url ({audio_url}): {e}"
            ) from e

        if not dest_path.exists() or dest_path.stat().st_size == 0:
            # Best-effort cleanup of empty/missing artifact before raising.
            dest_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Downloaded file is empty or missing: {audio_url}"
            )

        await self.log(
            f"Download complete: {dest_path.name} "
            f"({bytes_written / (1024 * 1024):.1f} MB)"
        )
        return dest_path

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
            (r',?\s*you know\?[\s,]*', '.'),  # ", you know?" or "you know?" → "."
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
            (r'\s+ah[,\s]*', ' '),  # " ah"
            (r'\s+oh[,\s]+', ' '),  # " oh, "
            (r'\s+just[,\s]+', ' '),  # " just, " or " just " - careful, can be meaningful
            (r'^just[,\s]+', ''),  # "Just, " at start
            
            # Phrase fillers
            (r'\s+or\s+something\b', ''),  # " or something"
            (r'\s+or\s+whatever\b', ''),  # " or whatever"
            (r'\s+and\s+stuff\b', ''),  # " and stuff"
            (r'\s+and\s+everything\b', ''),  # " and everything"
            (r'\s+and\s+all\s+that\b', ''),  # " and all that"
            
            # Repetitive transitions (consecutive occurrences)
            (r'\s+and\s+then\s+and\s+then\b', ' and then'),  # "and then and then"
            (r'\s+yeah,?\s+yeah,?\s+yeah\b', ' yeah'),  # "yeah yeah yeah" → single "yeah"
            (r'\s+yeah\s+yeah\b', ' yeah'),  # "yeah yeah" → single
            
            # Transition fillers at sentence start
            (r'\s+and\s+so\b', ''),  # " and so"
            (r'\s+but\s+yeah\b', ''),  # " but yeah" (redundant agreement)
            (r'\s+so\s+yeah\b', ''),  # " so yeah"
            
            # Filler combos
            (r'\s+right,?\s+yeah\b', ''),  # " right, yeah" or " right yeah"
            (r'\s+yeah,?\s+right\b', ''),  # " yeah, right"
            
            # Excessive ellipses
            (r'…\s*…', '…'),  # "… …" → single ellipsis
            (r'\.\.\.\s*\.\.\.', '...'),  # "... ..." → single
            
            # Colloquial patterns
            (r"\s+it's\s+like\b", ''),  # " it's like"
            (r"^it's\s+like\b", ''),  # "It's like" at start
            (r'\s+kind\s+of[-\s]*[-—]', ' '),  # "kind of ---" with dashes
            (r'\s+sort\s+of[-\s]*[-—]', ' '),  # "sort of ---"
            
            # Combo patterns
            (r'\s+just\s+kind\s+of\s+', ' '),  # " just kind of " → single space
            (r'\band\s+it\s+was\s+just\s+it\s+was\b', ' it was'),  # "And it was just it was" → "It was"
            (r'\bit\s+was\s+just\s+it\s+was\b', ' it was'),  # "it was just it was" → "it was"
            (r'\s+just\s+really\b', ''),  # " just really"
            (r'\s+just\s+definitely\b', ''),  # " just definitely"
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
