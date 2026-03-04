import os
import sys
import time
import numpy as np

try:
    from mlx_audio.stt.utils import load_model, get_model_path
    import mlx.core as mx
    import numpy as np
except ImportError:
    print("Error: Required libraries not found. Please run 'pixi run' to install dependencies.")
    sys.exit(1)

MODEL_REPO = "mlx-community/Qwen3-ASR-1.7B-4bit"

def benchmark_qwen_asr():
    print(f"--- Qwen3-ASR MLX Benchmark ---")
    print(f"Loading model: {MODEL_REPO}")
    
    t0 = time.time()
    try:
        # 0.3.1 should support this repo directly
        model = load_model(MODEL_REPO)
        print(f"Model loaded in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        return

    # Create dummy audio (5 seconds of silence at 16kHz)
    sample_rate = 16000
    duration = 5
    # mlx-audio 0.3.1 load_model might return a different object but transcribe wrapper usually exists
    # Or for Qwen3, it might be model.generate
    audio = np.zeros(sample_rate * duration, dtype=np.float32)
    
    print(f"Transcribing {duration}s of dummy audio...")
    t1 = time.time()
    # Attempt transcribe (high level) or generate
    try:
        if hasattr(model, "transcribe"):
            result = model.transcribe(audio)
            text = result.text if hasattr(result, "text") else str(result)
        else:
            # Fallback to generate with mx array
            mx_audio = [mx.array(audio)]
            result = model.generate(audio=mx_audio)
            text = result.text
    except Exception as e:
        print(f"Transcription failed: {e}")
        return

    t2 = time.time()
    
    print(f"Transcription finished in {t2 - t1:.2f}s")
    print(f"Result text: {text}")
    
    rtf = (t2 - t1) / duration
    print(f"Real Time Factor (RTF): {rtf:.4f}")
    
    rtf = (t2 - t1) / duration
    print(f"Real Time Factor (RTF): {rtf:.4f}")
    if rtf < 1.0:
        print("PASS: Faster than real-time!")
    else:
        print("INFO: Slower than real-time (Normal for a first run/compilation).")

if __name__ == "__main__":
    benchmark_qwen_asr()
