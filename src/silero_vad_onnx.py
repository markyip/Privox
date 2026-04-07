"""
Silero VAD using only ONNX Runtime (no PyTorch).
Provides a VADIterator-compatible interface for streaming voice activity detection.
Model: snakers4/silero-vad v5 ONNX (16kHz and 8kHz).
"""

from __future__ import annotations

import os
import urllib.request
import numpy as np

# Lazy import so callers can try/except and fall back to torch path
def _get_ort():
    import onnxruntime as ort
    return ort

# Default: snakers4 silero-vad v5 ONNX (16k and 8k)
SILERO_VAD_V5_ONNX_URL = (
    "https://github.com/snakers4/silero-vad/raw/refs/tags/v5.0/files/silero_vad.onnx"
)

CHUNK_SAMPLES_16K = 512
CHUNK_SAMPLES_8K = 256


def _download_model(cache_dir: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    name = "silero_vad_v5.onnx"
    path = os.path.join(cache_dir, name)
    if os.path.isfile(path):
        return path
    try:
        urllib.request.urlretrieve(SILERO_VAD_V5_ONNX_URL, path)
    except Exception as e:
        raise RuntimeError(f"Failed to download Silero VAD ONNX: {e}") from e
    return path


def load_silero_vad_onnx(cache_dir: str | None = None) -> "SileroVADOnnx":
    """Load Silero VAD ONNX model. cache_dir defaults to ~/.privox or current dir."""
    if cache_dir is None:
        cache_dir = os.path.expanduser(os.path.join("~", ".privox"))
    path = _download_model(cache_dir)
    return SileroVADOnnx(path)


class SileroVADOnnx:
    """
    Silero VAD model running with ONNX Runtime.
    Supports both v5-style (input, state, sr) and (input, h, c) interfaces.
    """

    def __init__(self, onnx_path: str):
        self._path = onnx_path
        ort = _get_ort()
        self._session = ort.InferenceSession(
            onnx_path,
            providers=["CPUExecutionProvider"],
            sess_options=ort.SessionOptions(),
        )
        inames = {i.name for i in self._session.get_inputs()}
        onames = [o.name for o in self._session.get_outputs()]
        self._use_state = "state" in inames
        self._use_hc = "h" in inames and "c" in inames
        if not (self._use_state or self._use_hc):
            # Fallback: assume first input is audio, last two are state
            self._use_state = True
        self._out_prob_idx = 0
        self._out_state_idx = 1
        self._state: np.ndarray | None = None
        self.reset_states()

    def _get_initial_state(self, batch_size: int = 1) -> np.ndarray:
        # (2, batch, 128) for "state"; or h (1,1,128), c (1,1,128)
        return np.zeros((2, batch_size, 128), dtype=np.float32)

    def reset_states(self) -> None:
        self._state = self._get_initial_state(1)

    def _run(self, audio_chunk: np.ndarray, sr: int) -> tuple[float, np.ndarray]:
        if audio_chunk.dtype != np.float32:
            audio_chunk = audio_chunk.astype(np.float32)
        if audio_chunk.ndim == 1:
            audio_chunk = audio_chunk.reshape(1, -1)
        inputs = {}
        for inp in self._session.get_inputs():
            name = inp.name.lower()
            if name == "input":
                inputs[inp.name] = audio_chunk
            elif name == "sr" or name == "sampling_rate":
                inputs[inp.name] = np.array([sr], dtype=np.int64)
            elif name == "state":
                inputs[inp.name] = self._state
            elif name == "h":
                inputs[inp.name] = self._state[:1]
            elif name == "c":
                inputs[inp.name] = self._state[1:2]
        outs = self._session.run(None, inputs)
        prob = float(np.asarray(outs[self._out_prob_idx]).reshape(-1)[-1])
        if self._use_state and len(outs) > self._out_state_idx:
            self._state = np.asarray(outs[self._out_state_idx])
        elif self._use_hc and len(outs) >= 3:
            self._state = np.concatenate(
                [np.asarray(outs[1]), np.asarray(outs[2])], axis=0
            )
        return prob, self._state

    def __call__(self, chunk: np.ndarray, sr: int = 16000) -> float:
        """Return speech probability for the chunk (0..1)."""
        prob, _ = self._run(chunk, sr)
        return prob


class VADIterator:
    """
    Stream-oriented VAD iterator compatible with snakers4 silero-vad API.
    Call with 512-sample (16kHz) or 256-sample (8kHz) chunks; returns
    {'start'|'end': time_sec} when segment boundaries are detected.
    """

    def __init__(
        self,
        model: SileroVADOnnx,
        *,
        threshold: float = 0.5,
        sampling_rate: int = 16000,
        min_silence_duration_ms: int = 500,
        speech_pad_ms: int = 500,
    ):
        self.model = model
        self.threshold = threshold
        self.sampling_rate = sampling_rate
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_pad_ms = speech_pad_ms
        self._chunk_sec = (CHUNK_SAMPLES_16K if sampling_rate == 16000 else CHUNK_SAMPLES_8K) / sampling_rate
        self._in_speech = False
        self._segment_start_sec: float = 0.0
        self._cur_time_sec: float = 0.0
        self._silence_duration_sec: float = 0.0

    def reset_states(self) -> None:
        self.model.reset_states()
        self._in_speech = False
        self._segment_start_sec = 0.0
        self._cur_time_sec = 0.0
        self._silence_duration_sec = 0.0

    def __call__(
        self,
        chunk: np.ndarray,
        return_seconds: bool = True,
    ) -> dict | None:
        """
        Process one chunk. Returns None or a dict with 'start' and/or 'end' keys.
        'end' is emitted when silence after speech exceeds min_silence_duration_ms.
        """
        if chunk is None or len(chunk) == 0:
            return None
        prob = self.model(chunk, sr=self.sampling_rate)
        result = None
        self._cur_time_sec += self._chunk_sec
        if prob >= self.threshold:
            if not self._in_speech:
                self._in_speech = True
                self._segment_start_sec = max(
                    0.0,
                    self._cur_time_sec - self._chunk_sec - self.speech_pad_ms / 1000.0,
                )
                result = {"start": self._segment_start_sec}
            self._silence_duration_sec = 0.0
        else:
            if self._in_speech:
                self._silence_duration_sec += self._chunk_sec
                if self._silence_duration_sec >= self.min_silence_duration_ms / 1000.0:
                    end_sec = self._cur_time_sec + (self.speech_pad_ms / 1000.0)
                    if result is None:
                        result = {}
                    result["end"] = end_sec
                    self._in_speech = False
                    self._silence_duration_sec = 0.0
        return result
