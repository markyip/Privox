"""
WebRTC VAD (no PyTorch) — approximates Silero VADIterator call pattern for voice_input.processing_loop.

Frames must be 10 / 20 / 30 ms at 16 kHz; we buffer incoming float32 chunks (e.g. 512 samples)
and run int16 PCM through webrtcvad.Vad.
"""
from __future__ import annotations

import numpy as np

# 16 kHz × 30 ms = 480 samples (valid webrtc frame size)
_FRAME_SAMPLES = 480


class WebRtcVadAdapter:
    """Callable like Silero VADIterator(audio, return_seconds=True) -> dict | None."""

    def __init__(
        self,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        min_silence_duration_ms: int = 550,
        speech_pad_ms: int = 30,
    ):
        import webrtcvad

        if sample_rate != 16000:
            raise ValueError("WebRtcVadAdapter only supports 16 kHz")
        self._vad = webrtcvad.Vad(int(np.clip(aggressiveness, 0, 3)))
        self.sample_rate = sample_rate
        self.min_silence_duration_ms = max(100, int(min_silence_duration_ms))
        self._silence_samples_needed = int(self.min_silence_duration_ms * sample_rate / 1000)
        self._byte_buf = bytearray()
        self._speaking = False
        self._silence_run = 0
        self._speech_run = 0
        self._min_speech_frames = 2

    def reset_states(self):
        self._byte_buf.clear()
        self._speaking = False
        self._silence_run = 0
        self._speech_run = 0

    def __call__(self, audio, return_seconds: bool = False):
        x = np.asarray(audio, dtype=np.float32).flatten()

        pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
        self._byte_buf.extend(pcm.tobytes())

        out = None
        frame_bytes = _FRAME_SAMPLES * 2
        while len(self._byte_buf) >= frame_bytes:
            frame = bytes(self._byte_buf[:frame_bytes])
            del self._byte_buf[:frame_bytes]
            is_speech = self._vad.is_speech(frame, self.sample_rate)

            if is_speech:
                self._speech_run += 1
                self._silence_run = 0
                if not self._speaking and self._speech_run >= self._min_speech_frames:
                    self._speaking = True
                    if return_seconds:
                        out = {"start": 0.0}
                    else:
                        out = {"start": 0}
                    break
            else:
                self._silence_run += _FRAME_SAMPLES
                self._speech_run = 0
                if self._speaking and self._silence_run >= self._silence_samples_needed:
                    self._speaking = False
                    if return_seconds:
                        out = {"end": self._silence_duration_sec()}
                    else:
                        out = {"end": self._silence_run}
                    break
        return out

    def _silence_duration_sec(self) -> float:
        return self._silence_run / float(self.sample_rate)
