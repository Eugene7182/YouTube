import argparse
import json
from pathlib import Path
from typing import List, Tuple
import wave

try:
    import numpy as np
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit("numpy is required for scripts/tts_xtts.py") from exc

try:
    from TTS.api import TTS as CoquiTTS
except ImportError:
    CoquiTTS = None

MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
TARGET_SAMPLE_RATE = 48_000
SPEED_MIN, SPEED_MAX = 0.97, 1.05


def _read_script(path: Path) -> Tuple[List[str], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = [str(line).strip() for line in data.get("lines", []) if str(line).strip()]
    cta = str(data.get("cta", "")).strip()
    return lines, cta


def _build_segments(lines: List[str], cta: str, pause_ms: int) -> List[Tuple[str, str]]:
    segments: List[Tuple[str, str]] = []
    if not lines and not cta:
        return segments

    if pause_ms > 0 and len(lines) > 1:
        lead = " ".join(lines[:-1]).strip()
        twist = lines[-1]
        if lead:
            segments.append(("text", lead))
        segments.append(("silence", str(pause_ms)))
        if twist:
            segments.append(("text", twist))
    else:
        combined_lines = " ".join(lines).strip()
        if combined_lines:
            segments.append(("text", combined_lines))

    if cta:
        segments.append(("text", cta))
    return segments


def _ensure_speed(speed: float) -> float:
    if not (SPEED_MIN <= speed <= SPEED_MAX):
        raise SystemExit(f"--speed must be between {SPEED_MIN} and {SPEED_MAX}, got {speed}")
    return speed


def _synthesize_segments(
    tts_model: "CoquiTTS",
    segments: List[Tuple[str, str]],
    *,
    speaker_wav: str | None,
    language: str,
    speed: float,
) -> Tuple[np.ndarray, int]:
    if not segments:
        return np.zeros(0, dtype=np.float32), TARGET_SAMPLE_RATE

    synthesizer = getattr(tts_model, "synthesizer", None)
    source_sr = getattr(synthesizer, "output_sample_rate", None) or TARGET_SAMPLE_RATE
    parts: List[np.ndarray] = []

    for kind, payload in segments:
        if kind == "text":
            text = payload.strip()
            if not text:
                continue
            audio = tts_model.tts(
                text=text,
                speaker_wav=speaker_wav,
                language=language,
                speed=speed,
            )
            audio_np = np.asarray(audio, dtype=np.float32).squeeze()
            parts.append(audio_np)
        elif kind == "silence":
            pause_ms = max(0, int(float(payload)))
            if pause_ms == 0:
                continue
            samples = int(round(source_sr * pause_ms / 1000.0))
            if samples > 0:
                parts.append(np.zeros(samples, dtype=np.float32))
        else:  # pragma: no cover - defensive branch
            raise RuntimeError(f"Unknown segment type: {kind}")

    if not parts:
        return np.zeros(0, dtype=np.float32), source_sr

    audio_all = np.concatenate(parts)
    return audio_all, int(source_sr)


def _resample(audio: np.ndarray, source_sr: int, target_sr: int) -> np.ndarray:
    if source_sr == target_sr or audio.size == 0:
        return audio.astype(np.float32, copy=False)

    duration = audio.shape[0] / float(source_sr)
    target_len = max(1, int(round(duration * target_sr)))
    old_times = np.linspace(0.0, duration, num=audio.shape[0], endpoint=False)
    new_times = np.linspace(0.0, duration, num=target_len, endpoint=False)
    resampled = np.interp(new_times, old_times, audio.astype(np.float64))
    return resampled.astype(np.float32)


def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.size == 0:
        raise SystemExit("Generated audio is empty; nothing to write")
    clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate narration with Coqui XTTS v2 (CPU).")
    parser.add_argument("--script_json", required=True, help="Path to script JSON with title/lines/cta")
    parser.add_argument("--out", required=True, help="Target WAV path (48 kHz)")
    parser.add_argument("--speaker_wav", help="Optional reference voice sample for cloning")
    parser.add_argument("--pause_ms_before_twist", type=int, default=0, help="Silence before final line in milliseconds")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier (0.97-1.05)")
    parser.add_argument("--language", default="en", help="Language token for XTTS (default: en)")
    args = parser.parse_args()

    if CoquiTTS is None:
        raise SystemExit("Coqui TTS package is not installed. Run 'pip install TTS'.")

    pause_ms = max(0, int(args.pause_ms_before_twist))
    speed = _ensure_speed(float(args.speed))

    script_path = Path(args.script_json)
    if not script_path.exists():
        raise SystemExit(f"Script JSON not found: {script_path}")

    speaker_path: str | None = None
    if args.speaker_wav:
        speaker = Path(args.speaker_wav)
        if not speaker.exists():
            raise SystemExit(f"Speaker WAV not found: {speaker}")
        speaker_path = str(speaker)

    lines, cta = _read_script(script_path)
    segments = _build_segments(lines, cta, pause_ms)

    tts_model = CoquiTTS(model_name=MODEL_NAME, progress_bar=False, gpu=False)
    audio, source_sr = _synthesize_segments(
        tts_model,
        segments,
        speaker_wav=speaker_path,
        language=args.language,
        speed=speed,
    )
    audio_48k = _resample(audio, source_sr, TARGET_SAMPLE_RATE)
    _write_wav(Path(args.out), audio_48k, TARGET_SAMPLE_RATE)
    print(f"XTTS narration saved to {args.out}")


if __name__ == "__main__":
    main()
