# Qiskit Metal Flip-Chip Fork Installation Guide

This repository is a custom fork of Qiskit Metal:

- Upstream project: `https://github.com/qiskit-community/qiskit-metal`
- Custom fork: `https://github.com/Wang-22562-oss/qiskit-metal`

The recommended way to install this fork is:

1. Follow the official "install from source" workflow.
2. Clone this fork instead of the upstream repository.
3. Install the package in editable mode so the custom renderer and user components are available immediately.

This guide is written for Windows users and follows the current official recommendation to prefer Conda on Windows for binary-heavy dependencies such as `shapely` and `gdstk`.

## What Is Included In This Fork

This fork already contains the custom files, so a fresh install does not need a separate manual overwrite step.

- Updated `src/qiskit_metal/config.py`
- Added `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`
- Added or replaced `src/qiskit_metal/qlibrary/user_components/`

If you clone this fork directly, those files come with the repository.

## Recommended Installation (Windows + Conda)

### 1. Install prerequisites

Install the following first:

- Git
- Miniconda or Anaconda

Optional but still useful:

- JupyterLab
- Visual Studio Build Tools

### 2. Clone this fork

```powershell
git clone https://github.com/Wang-22562-oss/qiskit-metal.git
cd qiskit-metal
```

### 3. Create the Conda environment from `environment.yml`

```powershell
conda env create -n qiskit-metal-fc -f environment.yml
conda activate qiskit-metal-fc
python -m pip install --no-deps -e .
```

Notes:

- `python -m pip install --no-deps -e .` matches the current official source-install guidance for the Conda path.
- Editable mode (`-e`) is recommended so local source changes are picked up without reinstalling.

### 4. Optional: register a Jupyter kernel

```powershell
python -m pip install ipykernel
python -m ipykernel install --user --name qiskit-metal-fc --display-name "Qiskit Metal FlipChip"
```

Then start JupyterLab:

```powershell
jupyter lab
```

## Quick Verification

After installation, verify that the package imports and that the custom renderer file is available:

```powershell
python -c "import qiskit_metal; print('qiskit_metal import OK')"
python -c "from qiskit_metal.renderers.renderer_gds.FlipChip_gds_renderer import MyGDSRenderer; print(MyGDSRenderer.__name__)"
```

If you want to confirm the custom user component directory exists:

```powershell
python -c "from pathlib import Path; import qiskit_metal; root = Path(qiskit_metal.__file__).resolve().parent; print(root / 'qlibrary' / 'user_components')"
```

## Alternative: I Already Installed Upstream Qiskit Metal

If you already installed the upstream `qiskit-community/qiskit-metal` source tree and only want to apply the custom flip-chip additions, copy the following paths from this fork into the upstream checkout:

- `src/qiskit_metal/config.py`
- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`
- `src/qiskit_metal/qlibrary/user_components/`

After copying the files, reinstall in editable mode from the repository root:

```powershell
python -m pip install --no-deps -e .
```

## Recommended README Wording

If you want a short version for the repository `README.md`, you can reuse this:

> This repository is a custom fork of Qiskit Metal for flip-chip design workflows. For a new installation, please follow the official source-install process but clone this repository instead of the upstream repository. On Windows, the recommended path is Conda plus `python -m pip install --no-deps -e .`. The fork already includes the custom `config.py`, the `FlipChip_gds_renderer.py` renderer, and the `qlibrary/user_components` additions.

## Release Checklist

Before publishing the installation instructions, verify these items:

- `python -m py_compile src/qiskit_metal/config.py`
- `python -c "import qiskit_metal"`
- The repository does not include unnecessary cache files such as `__pycache__`
- The GitHub README links to this installation guide
