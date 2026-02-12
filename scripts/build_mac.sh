#!/bin/bash
echo "Building Wispr Voice Input for macOS..."
rm -rf dist build

python3 -m PyInstaller --clean --noconsole --onefile \
    --name WisprVoiceInput \
    --hidden-import pystray._darwin \
    --hidden-import sounddevice \
    --hidden-import PIL \
    --hidden-import cn2an \
    --hidden-import tiktoken \
    --hidden-import funasr \
    --hidden-import modelscope \
    --collect-all llama_cpp \
    --collect-all funasr \
    --collect-all opencc \
    voice_input.py

echo "Build Complete. Check dist/WisprVoiceInput"
