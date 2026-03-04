import torch
import os
import time

APP_DATA_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "Privox")
hub_dir = os.path.join(APP_DATA_DIR, "models", "hub")
torch.hub.set_dir(hub_dir)

repo_dir = os.path.join(hub_dir, 'snakers4_silero-vad_master')

start = time.time()
print(f"Loading from: {repo_dir}")
vad_model, utils = torch.hub.load(repo_or_dir=repo_dir,
                                        source='local',
                                        model='silero_vad',
                                        force_reload=False,
                                        trust_repo=True,
                                        onnx=False)
print(f"Loaded in {time.time() - start:.2f}s")
