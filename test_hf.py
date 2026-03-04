import os
os.environ["HF_HOME"] = os.path.expanduser("~/Library/Application Support/Privox/models/hub")
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

from huggingface_hub import snapshot_download
target = os.path.expanduser("~/Library/Application Support/Privox/models/mlx-llama-3.2")
print("Trying without flag...")
try:
    snapshot_download("mlx-community/Llama-3.2-3B-Instruct-4bit", local_dir=target)
    print("Success!")
except Exception as e:
    print("Error:", e)
