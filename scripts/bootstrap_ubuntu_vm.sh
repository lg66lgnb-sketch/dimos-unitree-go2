#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
  bash-completion \
  build-essential \
  curl \
  fd-find \
  ffmpeg \
  g++ \
  git \
  git-lfs \
  jq \
  libegl1 \
  libgl1 \
  libglib2.0-0 \
  libjpeg-turbo8 \
  libsm6 \
  libturbojpeg \
  libxext6 \
  libxrender1 \
  make \
  pkg-config \
  portaudio19-dev \
  pre-commit \
  python3-dev \
  ripgrep \
  unzip

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "Ubuntu VM bootstrap complete. Next: clone repo, create venv, run uv sync."
