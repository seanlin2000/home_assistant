"""Audio as the Wyoming protocol carries it: 16-bit mono PCM. Speech is made louder, but a sentence that would clip is lowered instead."""

import numpy as np

PCM_WIDTH_BYTES = 2
PCM_CHANNELS = 1
PCM_FULL_SCALE = 32767
RECOGNIZER_SAMPLE_RATE = 16000
CLIP_CEILING = 0.95
LOUDNESS_FRAME_SECONDS = 0.03
SILENT_DBFS = -120.0


class SentenceGain:
    """Amplifies one sentence's audio, piece by piece as it streams. A piece that would clip lowers the gain for the rest of the sentence; the gain never
    rises again within the sentence, so the volume does not pump between pieces."""

    def __init__(self, target_gain: float) -> None:
        self.gain = target_gain

    def amplified_pcm(self, samples: np.ndarray) -> bytes:
        peak = float(np.abs(samples).max(initial=0.0))
        if peak * self.gain > CLIP_CEILING:
            self.gain = CLIP_CEILING / peak
        return pcm_bytes(samples * self.gain)


def pcm_bytes(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * PCM_FULL_SCALE).astype(np.int16).tobytes()


def pcm_samples(audio: bytes) -> np.ndarray:
    return np.frombuffer(audio, dtype=np.int16).astype(np.float32) / (PCM_FULL_SCALE + 1)


def loudest_frame_dbfs(samples: np.ndarray, sample_rate: int) -> float:
    """The loudness of the loudest 30 ms of a recording, in decibels below full scale. A question is mostly pauses, so the whole recording's average
    would sink a short question below the floor."""
    frame_length = max(1, int(sample_rate * LOUDNESS_FRAME_SECONDS))
    frame_count = len(samples) // frame_length
    if frame_count == 0:
        return SILENT_DBFS
    frames = samples[: frame_count * frame_length].reshape(frame_count, frame_length)
    loudest_rms = float(np.sqrt(np.mean(frames**2, axis=1)).max())
    return max(SILENT_DBFS, 20 * np.log10(loudest_rms)) if loudest_rms > 0 else SILENT_DBFS
