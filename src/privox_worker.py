"""
Privox inference worker process.

Holds ALL CUDA-heavy state (ASR model + llama.cpp refiner) in its own OS process
so that, when the main app goes idle, killing this process returns 100% of the
VRAM to the OS -- including the CUDA context / cuDNN / cuBLAS library footprint
that torch.cuda.empty_cache() can never release inside a long-lived process.

The main process owns the tray, hotkey, microphone, VAD (CPU) and clipboard, and
delegates only the audio -> refined-text inference to this worker over a local
socket (see privox_ipc).

Lifecycle:
  - main spawns:  python privox_worker.py --port <N>
  - worker binds 127.0.0.1:<N>, accepts ONE persistent connection from main
  - worker starts WARM-FRESH (no models loaded, ~0 VRAM); "ping" reports readiness
  - "load" triggers background model load (hotkey-down warm-up); "ping" reports when ready
  - "transcribe" runs ASR + refiner and returns text (lazy-loads if needed)
  - "shutdown" (or a dropped connection) exits the process -> VRAM freed by OS
"""
from __future__ import annotations

import os
import sys
import argparse
import threading
import traceback

# Engine mode MUST be set before importing voice_input so its __init__ skips the
# tray / microphone / hotkey startup and only owns the inference engine.
os.environ["PRIVOX_ENGINE_MODE"] = "1"

# Ensure the worker can import sibling modules whether launched as a script or frozen.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import numpy as np  # noqa: E402

import privox_ipc  # noqa: E402


def _log(msg: str) -> None:
    try:
        print(f"[privox-worker] {msg}", flush=True)
    except Exception:
        pass


class InferenceWorker:
    def __init__(self, port: int):
        self.port = port
        self.app = None
        self._ready = False
        self._load_error = ""
        self._load_lock = threading.RLock()
        self._load_thread = None
        self._load_thread_lock = threading.Lock()
        self._prebuild_done = threading.Event()

    # --- model lifecycle -------------------------------------------------
    def _build_app(self):
        with self._load_lock:
            if self.app is not None:
                self._prebuild_done.set()
                return self.app
            import voice_input

            self.app = voice_input.VoiceInputApp()
            self._prebuild_done.set()
        return self.app

    def _prebuild_app(self):
        """WARM-FRESH pre-pay: import voice_input + construct VoiceInputApp (NO model load).

        This imports torch and builds the engine object (~3-4s) while holding ~0 VRAM, so a
        subsequent 'load' only has to load the ASR + refiner weights, not the heavy imports.
        """
        try:
            if self.app is None:
                _log("pre-building engine (import voice_input, no models)...")
                self._build_app()
                _log("engine pre-built (WARM-FRESH, ~0 VRAM).")
        except BaseException as e:
            _log(f"pre-build error: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        finally:
            self._prebuild_done.set()

    def _load_models(self):
        if not self._prebuild_done.wait(timeout=120.0):
            _log("pre-build still running after 120s; loading anyway")
        with self._load_lock:
            if self._ready:
                return
            try:
                if self.app is None:
                    self._build_app()
                # Engine mode does not auto-start initial_load; trigger heavy load now.
                self.app.load_heavy_models()
                self._ready = bool(getattr(self.app, "heavy_models_loaded", False))
                if not self._ready:
                    self._load_error = getattr(self.app, "last_model_error", "") or "load failed"
            except BaseException as e:
                # BaseException (not just Exception) so a stray SystemExit during import is logged
                # instead of silently killing this thread and leaving the worker stuck "not ready".
                self._load_error = f"{type(e).__name__}: {e}"
                _log(f"Model load error: {self._load_error}\n{traceback.format_exc()}")

    def _start_load(self) -> None:
        """Kick off model loading in the background (idempotent, non-blocking).

        The worker starts WARM-FRESH (process imported, CUDA context lazy, ~0 VRAM) and only
        loads heavy models when the main process sends a 'load' command (on hotkey-down) or on
        the first transcribe. This keeps a respawned idle worker at ~0 VRAM while still skipping
        the spawn+import cost on wake.
        """
        with self._load_thread_lock:
            if self._ready:
                return
            if self._load_thread is not None and self._load_thread.is_alive():
                return
            self._load_thread = threading.Thread(target=self._load_models, daemon=True)
            self._load_thread.start()

    def _ensure_ready(self) -> bool:
        if not self._ready:
            self._load_models()
        return self._ready

    # --- request handlers ------------------------------------------------
    def _handle_transcribe(self, header: dict, blob: bytes) -> dict:
        if not self._ensure_ready():
            return {"cmd": "result", "ok": False, "reason": "no_model", "detail": self._load_error}
        try:
            dtype = header.get("dtype", "float32")
            audio = np.frombuffer(blob, dtype=np.dtype(dtype)).copy()
            task_id = header.get("task_id")
            result = self.app.run_inference(audio, task_id=task_id)
            if not isinstance(result, dict):
                return {"cmd": "result", "ok": False, "reason": "bad_result"}
            result.setdefault("cmd", "result")
            return result
        except Exception as e:
            _log(f"Transcribe error: {e}\n{traceback.format_exc()}")
            return {"cmd": "result", "ok": False, "reason": "exception", "detail": str(e)}

    def _handle_reload(self) -> dict:
        try:
            asr_reload = False
            if self.app is not None and hasattr(self.app, "load_config"):
                self.app.load_config()
                if hasattr(self.app, "_reload_asr_if_preset_changed"):
                    asr_reload = bool(self.app._reload_asr_if_preset_changed())
                # Refiner persona/dictionary live on the grammar checker; refresh them.
                if hasattr(self.app, "_sync_refiner_from_config"):
                    self.app._sync_refiner_from_config()
            if asr_reload:
                self._ready = False
                self._load_error = ""
                self._start_load()
            return {"cmd": "ack", "ok": True, "asr_reload": asr_reload}
        except Exception as e:
            return {"cmd": "ack", "ok": False, "detail": str(e)}

    def _dispatch(self, header: dict, blob: bytes):
        cmd = header.get("cmd")
        if cmd == "transcribe":
            return self._handle_transcribe(header, blob)
        if cmd == "ping":
            return {"cmd": "pong", "ready": self._ready, "error": self._load_error}
        if cmd == "load":
            # Trigger background load (idempotent). Returns immediately; poll readiness via "ping".
            self._start_load()
            return {"cmd": "ack", "ok": True, "ready": self._ready}
        if cmd == "reload_config":
            return self._handle_reload()
        if cmd == "shutdown":
            return None  # signal to exit
        return {"cmd": "error", "detail": f"unknown cmd {cmd!r}"}

    # --- serve loop ------------------------------------------------------
    def serve(self):
        import socket

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", self.port))
        srv.listen(1)
        srv.settimeout(120.0)
        _log(f"listening on 127.0.0.1:{self.port} (WARM-FRESH; awaiting 'load')")

        # WARM-FRESH start: pre-build the engine (import voice_input + construct app) so the heavy
        # imports are paid now, but do NOT load models. This holds ~0 VRAM (CUDA context is lazy),
        # so an idle respawned worker stays at ~0 VRAM while a later 'load' only needs to load the
        # ASR + refiner weights -> much faster wake.
        threading.Thread(target=self._prebuild_app, daemon=True).start()

        try:
            conn, _addr = srv.accept()
        except socket.timeout:
            _log("no connection from main within 120s; exiting")
            return
        conn.settimeout(None)
        _log("main connected")

        with conn:
            while True:
                msg = privox_ipc.recv_message(conn)
                if msg is None:
                    _log("connection closed by main; exiting")
                    break
                header, blob = msg
                reply = self._dispatch(header, blob)
                if reply is None:
                    _log("shutdown requested; exiting")
                    privox_ipc.send_message(conn, {"cmd": "bye"})
                    break
                try:
                    privox_ipc.send_message(conn, reply)
                except (ConnectionError, OSError):
                    _log("failed to send reply; exiting")
                    break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    worker = InferenceWorker(args.port)
    try:
        worker.serve()
    except Exception as e:
        _log(f"fatal: {e}\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
