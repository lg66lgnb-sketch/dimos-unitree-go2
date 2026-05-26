# RUNBOOK_UBUNTU_VM.md

## Goal

Use Ubuntu/UTM only as an optional offline development environment. The final DogOps build must validate in the full DimOS checkout on the Mac because the real Go2 is available there.

Do not spend time debugging Go2 networking inside the VM unless the VM is explicitly bridged onto the same robot network and the user asks for that path.

## Recommended VM Profile

| Resource | Minimum | Better |
|---|---:|---:|
| CPU | 4 cores | 8+ cores |
| RAM | 12 GB | 24-32 GB |
| Disk | 25 GB free | 50+ GB free |
| OS | Ubuntu 22.04/24.04 | Ubuntu 24.04 |

GPU is not required for the base DogOps flow.

## System Setup

```bash
sudo apt-get update
sudo apt-get install -y \
  bash-completion build-essential curl fd-find ffmpeg g++ git git-lfs jq \
  libegl1 libgl1 libglib2.0-0 libjpeg-turbo8 libsm6 libturbojpeg \
  libxext6 libxrender1 make pkg-config portaudio19-dev pre-commit \
  python3-dev ripgrep unzip

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

If `fd` is installed as `fdfind`:

```bash
mkdir -p ~/.local/bin
ln -sf "$(command -v fdfind)" ~/.local/bin/fd
```

## Clone DimOS For Offline Work

```bash
export GIT_LFS_SKIP_SMUDGE=1
mkdir -p ~/code
cd ~/code
git clone https://github.com/dimensionalOS/dimos.git
cd dimos
git checkout -b dogops/siteops-agent origin/main
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv sync --extra base --extra apriltag --extra visualization --extra web --group tests --group lint
```

Add `--extra unitree` only if you need import coverage for robot paths in the VM.

## Copy Project Files

```bash
cd ~/code/dimos
cp -R $DOGOPS_REPO/. .
mkdir -p examples/dogops
cp config/*.yaml examples/dogops/
```

Keep `.dogops/`, generated media, and local logs untracked.

## Offline Checks

```bash
uv run python --version
uv run pytest -q dimos/utils/cli/test_apriltag.py
uv run dimos apriltag --ids '10,20,101-104' --size-mm 100 --family tag36h11 --out /tmp/dogops-tags.pdf
```

After implementation:

```bash
uv run pytest -q dimos/experimental/dogops
uv run python -m dimos.experimental.dogops.cli simulate --out .dogops/runs/latest
uv run python -m dimos.experimental.dogops.cli serve --run .dogops/runs/latest --port 8765
```

## Hand Back To Mac

Before final validation, move the branch/changes to `$DIMOS_ROOT` on the Mac and run [RUNBOOK_MAC_GO2.md](RUNBOOK_MAC_GO2.md).

The VM is not a substitute for:

- `uv run dimos list | rg dogops` in the Mac/full DimOS checkout;
- real `unitree-go2` hardware smoke;
- the 90-second real or guided Go2 demo video.
