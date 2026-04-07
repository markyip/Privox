#!/usr/bin/env bash
# Build the native Swift menu-bar Privox.app (and optionally a DMG).
# Requires: Xcode Command Line Tools (swiftc), Python 3, and for full DMG: project .pixi or --slim + local Python/MLX.
#
# iTerm: Do NOT set this script as the profile "Command" for new windows — the window closes when the
# script exits and iTerm warns "session ended very soon". Open a normal shell, cd to the repo, run:
#   ./build_mac.sh
# Or use --keep-open if you must launch from a one-shot profile.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Error: '${PYTHON}' not found. Install Python 3 or set PYTHON=/path/to/python3." >&2
  exit 1
fi

PY_ARGS=()
KEEP_OPEN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      cat <<'EOF'
Usage: build_mac.sh [options]

Builds build_mac/Privox.app via build_mac_app.py (Swift UI + Python backend).

Options:
  --dmg         Also create build_mac/Privox.dmg (--create-dmg; bundles src/ and optionally .pixi).
  --slim        Only with --dmg: omit .pixi from the bundle; user supplies Python/MLX (PRIVOX_PYTHON or venv).
  --keep-open   After the build, wait for Enter (useful if iTerm closes the window when the script exits).

Environment:
  PYTHON                 Python to run the build script (default: python3).
  PRIVOX_BUILD_PAUSE=1   Same as --keep-open (for profile shortcuts).
  PRIVOX_SIGNING_IDENTITY, PRIVOX_NOTARY_PROFILE, PRIVOX_REQUIRE_STABLE_SIGNATURE — see build_mac_app.py

iTerm tip: keep Profile → Command = login shell. Run this script from that shell, not as the profile command.

Examples:
  ./build_mac.sh
  ./build_mac.sh --dmg
  ./build_mac.sh --dmg --slim
EOF
      exit 0
      ;;
    --dmg)
      PY_ARGS+=(--create-dmg)
      ;;
    --slim)
      PY_ARGS+=(--slim)
      ;;
    --keep-open)
      KEEP_OPEN=true
      ;;
    *)
      echo "Unknown option: $1 (use --help)" >&2
      exit 1
      ;;
  esac
  shift
done

slim=false
create_dmg=false
# macOS Bash 3.2 + set -u: "${PY_ARGS[@]}" errors when the array is empty — use indexed access.
n_py=${#PY_ARGS[@]}
if (( n_py > 0 )); then
  for ((i = 0; i < n_py; i++)); do
    a="${PY_ARGS[i]}"
    [[ "$a" == --slim ]] && slim=true
    [[ "$a" == --create-dmg ]] && create_dmg=true
  done
fi
if $slim && ! $create_dmg; then
  echo "Error: --slim only applies when building a DMG. Add --dmg." >&2
  exit 1
fi

if (( n_py == 0 )); then
  echo "Using: $PYTHON build_mac_app.py"
else
  echo "Using: $PYTHON build_mac_app.py ${PY_ARGS[*]}"
fi

set +e
if (( n_py == 0 )); then
  "$PYTHON" build_mac_app.py
else
  "$PYTHON" build_mac_app.py "${PY_ARGS[@]}"
fi
exit_code=$?
set -e

if [[ "$KEEP_OPEN" == true || -n "${PRIVOX_BUILD_PAUSE:-}" ]]; then
  echo
  read -r -p "Build finished (exit $exit_code). Press Enter to close this window... " _
fi

exit "$exit_code"
