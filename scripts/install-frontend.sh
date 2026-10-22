#!/usr/bin/env bash
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
if ! command -v rustup >/dev/null 2>&1; then
  installer="$(mktemp)"
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error https://sh.rustup.rs -o "$installer"
  sh "$installer" -y --profile minimal --default-toolchain 1.99.1
  rm -f "$installer"
fi
rustup toolchain install 1.99.1 --profile minimal --component rustfmt --target wasm32-unknown-unknown
if ! command -v trunk >/dev/null 2>&1 || [[ "$(trunk --version)" != "trunk 0.21.14" ]]; then
  cargo +1.99.1 install trunk --locked --version 0.21.14 --force
fi
