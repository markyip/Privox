#!/usr/bin/env python3
"""Build/install llama-cpp-python with CUDA for Windows (cp312 often has no prebuilt cu124 wheel).

- CMAKE_ARGS must not contain unquoted spaces (e.g. under Program Files); use 8.3 short paths.
- Ninja builds need MSVC cl.exe on PATH; we locate it via vswhere when not in a VS Developer shell.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _windows_short_path(path: str) -> str:
    """8.3 path so CMAKE_ARGS is not split on spaces by the build frontend."""
    if sys.platform != "win32":
        return path
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return path
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    if n:
        return buf.value
    return path


def _cmake_arg_path(p: str) -> str:
    """Forward slashes, no spaces (short path on Windows)."""
    p = _windows_short_path(os.path.normpath(p))
    return Path(p).as_posix()


def _parse_cuda_dir_version(dirname: str) -> tuple[int, ...] | None:
    """'v12.6' -> (12, 6); unknown -> None."""
    if not dirname.startswith("v"):
        return None
    body = dirname.lstrip("v")
    nums: list[int] = []
    for part in body.split("."):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    return tuple(nums) if nums else None


def _enumerate_windows_cuda_installs() -> list[tuple[tuple[int, ...], str, str]]:
    """Each entry: (version_tuple, toolkit_root, nvcc_path). Deduped by resolved root."""
    seen: set[str] = set()
    out: list[tuple[tuple[int, ...], str, str]] = []

    def add_root(root: str) -> None:
        root = os.path.normpath(os.path.abspath(root))
        if root in seen:
            return
        nvcc = os.path.join(root, "bin", "nvcc.exe")
        if not os.path.isfile(nvcc):
            return
        ver = _parse_cuda_dir_version(os.path.basename(root))
        if ver is None:
            return
        seen.add(root)
        out.append((ver, root, nvcc))

    for key in ("CUDA_PATH", "CUDA_HOME", "CUDA_ROOT"):
        v = os.environ.get(key)
        if v:
            add_root(v)

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    cuda_parent = os.path.join(pf, "NVIDIA GPU Computing Toolkit", "CUDA")
    if os.path.isdir(cuda_parent):
        for name in os.listdir(cuda_parent):
            if name.startswith("v"):
                add_root(os.path.join(cuda_parent, name))

    w = shutil.which("nvcc")
    if w:
        add_root(str(Path(w).resolve().parent.parent))

    return out


def _find_nvcc() -> str | None:
    """Windows: MSVC 14.4x STL requires CUDA toolkit >= 12.4 (STL1002); prefer newest eligible install."""
    if sys.platform != "win32":
        env = os.environ
        for key in ("CUDA_PATH", "CUDA_HOME", "CUDA_ROOT"):
            v = env.get(key)
            if v:
                nvcc = os.path.join(v, "bin", "nvcc.exe")
                if os.path.isfile(nvcc):
                    return nvcc
        return shutil.which("nvcc")

    inst = _enumerate_windows_cuda_installs()
    if not inst:
        return shutil.which("nvcc")

    inst.sort(key=lambda t: t[0], reverse=True)
    min_stl = (12, 4)
    eligible = [t for t in inst if t[0] >= min_stl]
    if eligible:
        chosen = eligible[0]
    else:
        chosen = inst[0]
        print(
            "WARNING: No CUDA toolkit >= 12.4 found. MSVC 14.4 may fail with STL1002 "
            '(expected "CUDA 12.4 or newer"). Install CUDA 12.4+ or use an older MSVC.',
            file=sys.stderr,
            flush=True,
        )

    user_path = os.environ.get("CUDA_PATH")
    chosen_root = chosen[1]
    if user_path and os.path.normpath(os.path.abspath(user_path)) != os.path.normpath(chosen_root):
        print(
            f"Using CUDA toolkit: {chosen_root} (not CUDA_PATH={user_path!r}) "
            "so host STL matches this MSVC — need toolkit >= 12.4.",
            flush=True,
        )
    return chosen[2]


def _find_msvc_cl() -> str | None:
    if sys.platform != "win32":
        return None
    if shutil.which("cl"):
        return shutil.which("cl")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = os.path.join(pf86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.isfile(vswhere):
        return None
    try:
        out = subprocess.check_output(
            [
                vswhere,
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if not out:
        return None
    msvc_root = Path(out) / "VC" / "Tools" / "MSVC"
    if not msvc_root.is_dir():
        return None
    for verdir in sorted(msvc_root.iterdir(), key=lambda p: p.name, reverse=True):
        cl = verdir / "bin" / "Hostx64" / "x64" / "cl.exe"
        if cl.is_file():
            return str(cl)
    return None


def _ensure_pip_importable() -> None:
    """Broken conda/pixi envs may ship Scripts\\pip.exe without the pip package — always verify import."""
    try:
        import pip  # noqa: F401
        return
    except ImportError:
        pass
    print("pip module missing; running ensurepip --upgrade ...", flush=True)
    try:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"], env=os.environ)
    except subprocess.CalledProcessError:
        print(
            "ERROR: ensurepip failed (some conda-forge builds disable it). "
            "Run: pixi add pip && pixi install",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    try:
        import pip  # noqa: F401
    except ImportError:
        print(
            "ERROR: pip still not importable after ensurepip. Run: pixi add pip && pixi install",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)


def _pip_command_prefix() -> list[str]:
    _ensure_pip_importable()
    return [sys.executable, "-m", "pip"]


def _find_windows_sdk_x64_bin() -> str | None:
    """Directory containing rc.exe and mt.exe (needed for MSVC + Ninja link step)."""
    if sys.platform != "win32":
        return None
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    bin_root = os.path.join(pf86, "Windows Kits", "10", "bin")
    if not os.path.isdir(bin_root):
        return None
    candidates: list[str] = []
    for name in os.listdir(bin_root):
        x64 = os.path.join(bin_root, name, "x64")
        rc = os.path.join(x64, "rc.exe")
        if os.path.isfile(rc):
            candidates.append(name)
    if not candidates:
        return None

    def _ver_key(folder: str) -> tuple:
        nums: list[int] = []
        for part in folder.split("."):
            if part.isdigit():
                nums.append(int(part))
            else:
                nums.append(0)
        return tuple(nums)

    best = sorted(candidates, key=_ver_key, reverse=True)[0]
    return os.path.join(bin_root, best, "x64")


def _apply_msvc_sdk_lib_include(cl_exe: str, sdk_tools_x64: str, env: dict) -> None:
    """Set LIB / INCLUDE so link.exe finds kernel32.lib and CRT (LNK1104 without vcvars)."""
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    sdk_ver = Path(sdk_tools_x64).parent.name
    kit10 = Path(pf86) / "Windows Kits" / "10"
    lib_um = kit10 / "Lib" / sdk_ver / "um" / "x64"
    lib_ucrt = kit10 / "Lib" / sdk_ver / "ucrt" / "x64"
    inc_um = kit10 / "Include" / sdk_ver / "um"
    inc_ucrt = kit10 / "Include" / sdk_ver / "ucrt"
    inc_shared = kit10 / "Include" / sdk_ver / "shared"
    inc_winrt = kit10 / "Include" / sdk_ver / "winrt"

    cl_p = Path(cl_exe).resolve()
    # .../VC/Tools/MSVC/<ver>/bin/Hostx64/x64/cl.exe -> MSVC root is parents[3]
    msvc_root = cl_p.parents[3]
    vc_lib = msvc_root / "lib" / "x64"
    vc_include = msvc_root / "include"

    for label, p in (
        ("MSVC lib/x64", vc_lib),
        ("SDK um/x64", lib_um),
        ("SDK ucrt/x64", lib_ucrt),
    ):
        if not p.is_dir():
            print(f"ERROR: expected {label} at {p} — repair VS Build Tools / Windows SDK install.", file=sys.stderr, flush=True)
            sys.exit(1)

    lib_parts = [str(vc_lib), str(lib_um), str(lib_ucrt)]
    if env.get("LIB"):
        lib_parts.append(env["LIB"])
    env["LIB"] = os.pathsep.join(lib_parts)

    inc_parts = [str(vc_include), str(inc_um), str(inc_ucrt), str(inc_shared)]
    if inc_winrt.is_dir():
        inc_parts.append(str(inc_winrt))
    if env.get("INCLUDE"):
        inc_parts.append(env["INCLUDE"])
    env["INCLUDE"] = os.pathsep.join(inc_parts)

    env["WindowsSDKVersion"] = sdk_ver + os.sep
    print(f"LIB (first): {vc_lib}", flush=True)


def _find_ninja() -> str | None:
    n = shutil.which("ninja")
    if n:
        return n
    prefix = Path(sys.prefix)
    for cand in (
        prefix / "Library" / "bin" / "ninja.exe",
        prefix / "Scripts" / "ninja.exe",
        prefix / "bin" / "ninja.exe",
    ):
        if cand.is_file():
            return str(cand)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build/install llama-cpp-python with CUDA on Windows (cp312-friendly env)."
    )
    ap.add_argument(
        "--wheel",
        action="store_true",
        help="Only build a wheel into --wheel-dir (no pip install). Same CUDA/MSVC env as install.",
    )
    ap.add_argument(
        "--wheel-dir",
        default="wheels",
        help="Output directory for --wheel (default: ./wheels)",
    )
    ap.add_argument(
        "--version",
        default="0.3.20",
        help="llama-cpp-python version to build/install (default: 0.3.20)",
    )
    args = ap.parse_args()

    os.environ["PYTHONNOUSERSITE"] = "1"
    os.environ.setdefault("CFLAGS", "/utf-8")
    os.environ.setdefault("CXXFLAGS", "/utf-8")

    nvcc = _find_nvcc()
    if not nvcc:
        print(
            "ERROR: nvcc.exe not found. Install CUDA Toolkit and set CUDA_PATH, or add CUDA\\bin to PATH.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    nvcc_cmake = _cmake_arg_path(nvcc)
    py_exe_cmake = _cmake_arg_path(sys.executable)
    print(f"Using CUDA compiler (CMake): {nvcc_cmake}", flush=True)
    print(f"Using Python (CMake): {py_exe_cmake}", flush=True)

    cmake_args = [
        "-DLLAMA_BUILD_TESTS=OFF",
        "-DLLAMA_BUILD_EXAMPLES=OFF",
        "-DLLAMA_BUILD_SERVER=OFF",
        "-DGGML_CUDA=ON",
        f"-DCMAKE_CUDA_COMPILER={nvcc_cmake}",
        f"-DPython_EXECUTABLE={py_exe_cmake}",
    ]
    # Older nvcc rejects newest MSVC unless allowed. CMAKE_ARGS is split on spaces — use ';' so
    # -Xcompiler stays inside one -D value (else CMake sees a stray -Xcompiler=... and errors).
    if sys.platform == "win32":
        cmake_args.append(
            "-DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler;-Xcompiler=/utf-8"
        )
        # Helps MSVC parse llama.cpp headers with UTF-8 (avoids C4819/C2001 in jinja/utils.h under MSBuild).
        cmake_args.append("-DCMAKE_CXX_FLAGS=/utf-8")
        cmake_args.append("-DCMAKE_C_FLAGS=/utf-8")
    os.environ["CMAKE_ARGS"] = " ".join(cmake_args)

    ninja = _find_ninja()
    env = os.environ.copy()
    path_prefixes: list[str] = []

    cl = _find_msvc_cl()
    if not cl:
        print(
            "ERROR: MSVC cl.exe not found. Install 'Desktop development with C++' / VS Build Tools, "
            "or run this from 'x64 Native Tools Command Prompt for VS 2022'.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    cl_dir = str(Path(cl).parent)
    path_prefixes.append(cl_dir)
    env["CC"] = cl
    env["CXX"] = cl
    print(f"Using MSVC: {cl}", flush=True)

    if sys.platform == "win32":
        sdk_x64 = _find_windows_sdk_x64_bin()
        if not sdk_x64:
            print(
                "ERROR: Windows 10/11 SDK not found (need rc.exe for linking). "
                "In Visual Studio Installer, install 'Windows 11 SDK' (or 10 SDK) for Build Tools.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)
        path_prefixes.append(sdk_x64)
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        env.setdefault("WindowsSdkDir", os.path.join(pf86, "Windows Kits", "10"))
        print(f"Using Windows SDK tools: {sdk_x64}", flush=True)
        _apply_msvc_sdk_lib_include(cl, sdk_x64, env)

    if ninja:
        ninja_dir = str(Path(ninja).parent)
        path_prefixes.append(ninja_dir)
        env["CMAKE_GENERATOR"] = "Ninja"
        print(f"Using CMake generator: Ninja ({ninja})", flush=True)
    else:
        print(
            "WARNING: ninja not found; install with: pixi add ninja",
            flush=True,
        )

    env["PATH"] = os.pathsep.join(path_prefixes + [env.get("PATH", "")])

    if sys.platform == "win32":
        cuda_root = str(Path(nvcc).resolve().parent.parent)
        env["CUDACXX"] = nvcc
        env["CUDA_PATH"] = cuda_root
        env["CUDA_HOME"] = cuda_root
        env["CUDA_ROOT"] = cuda_root

    ver = str(args.version).strip()
    if args.wheel:
        out = Path(args.wheel_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        cmd = _pip_command_prefix() + [
            "wheel",
            "--no-deps",
            "--no-cache-dir",
            "--no-binary",
            "llama-cpp-python",
            "-w",
            str(out),
            f"llama-cpp-python=={ver}",
        ]
        print(f"Building wheel (CUDA) into {out} ...", flush=True)
    else:
        cmd = _pip_command_prefix() + [
            "install",
            "--upgrade",
            "--force-reinstall",
            "--no-cache-dir",
            f"llama-cpp-python=={ver}",
            "--extra-index-url",
            "https://abetlen.github.io/llama-cpp-python/whl/cu124",
            "--no-deps",
        ]
    print("Running:", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, env=env)


if __name__ == "__main__":
    main()
