# Qiskit Metal Flip-Chip Fork 安裝教學

這個 repository 是一份 Qiskit Metal 的客製 fork：

- 上游專案：`https://github.com/qiskit-community/qiskit-metal`
- 客製 fork：`https://github.com/Wang-22562-oss/qiskit-metal`

建議的安裝方式如下：

1. 依照官方「從原始碼安裝」的流程進行。
2. clone 這個 fork，而不是 clone upstream。
3. 用 editable mode 安裝，讓客製 renderer 和 user components 可以直接使用。

這份教學以 Windows 使用者為主，並遵循目前官方在 Windows 上較推薦的 Conda 路徑，因為像 `shapely`、`gdstk` 這類套件屬於較重的 binary dependency。

## 這個 Fork 內含哪些客製內容

這個 fork 已經包含你需要的客製檔案，所以如果是全新安裝，不需要再額外手動覆蓋一次。

- 已更新 `src/qiskit_metal/config.py`
- 已新增 `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`
- 已新增或覆寫 `src/qiskit_metal/qlibrary/user_components/`

也就是說，只要直接 clone 這個 fork，這些內容就會一起帶下來。

## 建議安裝方式（Windows + Conda）

### 1. 先安裝前置工具

請先準備：

- Git
- Miniconda 或 Anaconda

以下是選配，但通常也很有幫助：

- JupyterLab
- Visual Studio Build Tools

### 2. Clone 這個 fork

```powershell
git clone https://github.com/Wang-22562-oss/qiskit-metal.git
cd qiskit-metal
```

### 3. 用 `environment.yml` 建立 Conda 環境

```powershell
conda env create -n qiskit-metal-fc -f environment.yml
conda activate qiskit-metal-fc
python -m pip install --no-deps -e .
```

補充說明：

- `python -m pip install --no-deps -e .` 是目前官方 source install 在 Conda 路徑下的寫法。
- `-e` 代表 editable mode，之後如果你在本地修改 source code，不需要重裝就能被 Python 環境讀到。

### 4. 選配：註冊 Jupyter kernel

如果你會用 JupyterLab 或 notebook，建議把 kernel 也註冊起來：

```powershell
python -m pip install ipykernel
python -m ipykernel install --user --name qiskit-metal-fc --display-name "Qiskit Metal FlipChip"
```

之後可以用：

```powershell
jupyter lab
```

啟動 JupyterLab。

## 快速驗證安裝是否成功

安裝完成後，可以先做幾個簡單檢查，確認套件和客製 renderer 都有正常載入：

```powershell
python -c "import qiskit_metal; print('qiskit_metal import OK')"
python -c "from qiskit_metal.renderers.renderer_gds.FlipChip_gds_renderer import MyGDSRenderer; print(MyGDSRenderer.__name__)"
```

如果你也想確認客製的 user components 目錄真的在安裝環境中：

```powershell
python -c "from pathlib import Path; import qiskit_metal; root = Path(qiskit_metal.__file__).resolve().parent; print(root / 'qlibrary' / 'user_components')"
```

## 如果你已經安裝過 upstream Qiskit Metal

如果你原本已經安裝的是 `qiskit-community/qiskit-metal`，只是想把 flip-chip 相關客製功能套進去，那就把這個 fork 裡的以下路徑複製到你原本的 upstream checkout：

- `src/qiskit_metal/config.py`
- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`
- `src/qiskit_metal/qlibrary/user_components/`

複製完之後，請在 repository 根目錄重新執行 editable install：

```powershell
python -m pip install --no-deps -e .
```

## 可放進 README 的簡短版本

如果你想在 repository 的 `README.md` 先放一段簡短說明，可以直接用下面這段：

> This repository is a custom fork of Qiskit Metal for flip-chip design workflows. For a new installation, please follow the official source-install process but clone this repository instead of the upstream repository. On Windows, the recommended path is Conda plus `python -m pip install --no-deps -e .`. The fork already includes the custom `config.py`, the `FlipChip_gds_renderer.py` renderer, and the `qlibrary/user_components` additions.

如果你想放中文版本，也可以改成：

> 這個 repository 是 Qiskit Metal 的客製 fork，主要用於 flip-chip 設計流程。建議新使用者直接依照官方 source install 的步驟進行，但把 clone 對象改成這個 fork，而不是 upstream。對 Windows 使用者來說，最推薦的路徑是使用 Conda 建環境，再執行 `python -m pip install --no-deps -e .`。這個 fork 已經包含更新後的 `config.py`、`FlipChip_gds_renderer.py`，以及 `qlibrary/user_components` 內的客製內容。

## 發佈前檢查清單

在正式公開這份安裝教學之前，建議先確認：

- `python -m py_compile src/qiskit_metal/config.py`
- `python -c "import qiskit_metal"`
- repository 裡沒有不必要的快取檔，例如 `__pycache__`
- GitHub README 有連到這份安裝教學
