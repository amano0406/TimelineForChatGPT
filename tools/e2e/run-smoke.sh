#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ps1_path="$(wslpath -w "$script_dir/run-smoke.ps1")"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$ps1_path" "$@"
