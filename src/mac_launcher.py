import os
import sys
import datetime

def main():
    if getattr(sys, 'frozen', False):
        # Initial logging for debugging wrapped Apps
        with open("/tmp/privox_mac_launcher.log", "a") as f:
            f.write(f"\n--- Privox Launch: {datetime.datetime.now()} ---\n")
            f.write(f"sys.executable: {sys.executable}\n")
            
        # We are running inside the PyInstaller .app bundle
        # sys.executable is Privox.app/Contents/MacOS/Privox
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        macos_dir = os.path.dirname(sys.executable)
        
        resources_dir = os.path.abspath(os.path.join(macos_dir, "..", "Resources"))
        
        with open("/tmp/privox_mac_launcher.log", "a") as f:
            f.write(f"_MEIPASS base_dir: {base_dir}\n")
            f.write(f"macos_dir: {macos_dir}\n")
            f.write(f"resources_dir: {resources_dir}\n")
        
        # Inject the bundled .pixi environment site-packages into sys.path
        # PyInstaller python and .pixi python share the same ABI, so binaries will work natively.
        lib_base = os.path.join(resources_dir, ".pixi", "envs", "default", "lib")
        python_lib = None
        if os.path.exists(lib_base):
            for item in os.listdir(lib_base):
                if item.startswith("python3."):
                    python_lib = os.path.join(lib_base, item)
                    break
        
        if python_lib and os.path.exists(python_lib):
            site_pkgs = os.path.join(python_lib, "site-packages")
            lib_dynload = os.path.join(python_lib, "lib-dynload")
            
            with open("/tmp/privox_mac_launcher.log", "a") as f:
                f.write(f"Found python_lib inside bundle: {python_lib}\n")
            # Insert at index 1 to prioritize bundled packages over stripped PyInstaller zips
            sys.path.insert(1, site_pkgs)
            sys.path.insert(1, lib_dynload)
            sys.path.insert(1, python_lib)
            
            # Also inject the .pixi lib folder for dying dylibs like libc++.dylib
            pixi_lib = lib_base
            if "DYLD_LIBRARY_PATH" in os.environ:
                os.environ["DYLD_LIBRARY_PATH"] = f"{pixi_lib}:{os.environ['DYLD_LIBRARY_PATH']}"
            else:
                os.environ["DYLD_LIBRARY_PATH"] = pixi_lib
            
            with open("/tmp/privox_mac_launcher.log", "a") as f:
                f.write(f"DYLD_LIBRARY_PATH set to: {os.environ.get('DYLD_LIBRARY_PATH')}\n")
        else:
            with open("/tmp/privox_mac_launcher.log", "a") as f:
                f.write(f"WARNING: python_lib NOT FOUND inside bundle: {python_lib}\n")
                

        if len(sys.argv) > 1 and sys.argv[1].endswith(".py"):
            script_path = sys.argv[1]
        else:
            # When frozen, src/ is moved to Resources or bundled along with the exe
            # If we use --add-data "src:src", it lands in base_dir/src
            script_path = os.path.join(base_dir, "src", "voice_input.py")
            
            # Fallback for complex bundle structures
            if not os.path.exists(script_path):
                script_path = os.path.join(resources_dir, "src", "voice_input.py")
    else:
        # Development mode
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if len(sys.argv) > 1 and sys.argv[1].endswith(".py"):
            script_path = sys.argv[1]
        else:
            script_path = os.path.join(base_dir, "src", "voice_input.py")

    if not os.path.exists(script_path):
        print(f"Error: Script not found at {script_path}")
        os.system(f"""osascript -e 'display dialog "The Privox source script is missing.\\n\\nLooked for:\\n{script_path}" buttons {{"OK"}} default button "OK" with icon stop with title "Privox Error"' """)
        sys.exit(1)

    import runpy
    # Inject the script's directory into sys.path so it can find its sibling modules
    sys.path.insert(0, os.path.dirname(script_path))
    
    if getattr(sys, 'frozen', False):
        with open("/tmp/privox_mac_launcher.log", "a") as f:
            f.write(f"Executing runpy on: {script_path}\n")
            
    # Execute natively within the Privox process to preserve macOS permissions
    try:
        runpy.run_path(script_path, run_name="__main__")
    except Exception as e:
        if getattr(sys, 'frozen', False):
            import traceback
            with open("/tmp/privox_mac_launcher.log", "a") as f:
                f.write(f"FATAL ERROR during runpy:\n{traceback.format_exc()}\n")
        raise

if __name__ == "__main__":
    main()
