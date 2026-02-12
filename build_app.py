import PyInstaller.__main__
import os
import shutil

# Clean previous builds
if os.path.exists('build'):
    shutil.rmtree('build')
if os.path.exists('dist'):
    shutil.rmtree('dist')

print("Starting PyInstaller Build...")

PyInstaller.__main__.run([
    'src/voice_input.py',
    '--name=WisprLocal',
    '--onefile',
    '--clean',
    '--noconsole',
    '--icon=assets/icon.ico',
    # Hidden imports for dynamic dependencies
    '--hidden-import=pystray',
    '--hidden-import=pynput',
    '--hidden-import=faster_whisper',
    '--hidden-import=scikit-learn',
    '--hidden-import=sklearn.utils._cython_blas',
    '--hidden-import=sklearn.neighbors.typedefs',
    '--hidden-import=sklearn.neighbors.quad_tree',
    '--hidden-import=sklearn.tree',
    '--hidden-import=sklearn.tree._utils',
    '--hidden-import=scipy.spatial.transform._rotation_groups',
    '--hidden-import=scipy.special.cython_special',
    '--hidden-import=llama_cpp',
    # Collect data for faster-whisper (if needed, though it usually downloads to cache)
    # We might need to ensure the VAD model is handled if it's not in cache, but the app handles download.
])

print("Build Complete. Executable is in 'dist/WisprLocal.exe'")
