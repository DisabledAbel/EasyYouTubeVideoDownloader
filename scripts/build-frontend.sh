#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
# Trunk expects a boolean even when a CI host uses NO_COLOR=1.
export NO_COLOR=true
cd "$(dirname "$0")/../frontend"
trunk build --release --locked
