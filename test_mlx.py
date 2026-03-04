import sys
print(sys.executable)
try:
    import mlx_whisper
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
