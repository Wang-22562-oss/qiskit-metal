# `qlibrary/user_components` 功能總覽

這份文件用比較實務的方式說明目前這個 fork 裡的

`src/qiskit_metal/qlibrary/user_components/`

資料夾到底在做什麼。

整體來看，這個資料夾就是你這個 flip-chip workflow 的本地延伸元件庫，裡面主要包含：

- 把原本 Qiskit Metal 元件轉成 FC-aware 版本的薄包裝
- 真正為 flip-chip 需求設計的客製 FC-native 元件
- 給 FC layout 與 simulation 用的 port、transition、特殊幾何
- 一些工具型、模板型、實驗型元件

## 1. 主要結構

最容易理解的方式，是把這個資料夾分成三大群。

### 類別 A：`fc_usercomponents/`

這個子資料夾主要放的是「既有 Qiskit Metal 元件的薄 wrapper 版」。

這些檔案通常不會重寫原本的幾何邏輯，而是：

- import upstream component
- 繼承 `FlipChipCarveOutMixin` 或 `FlipChipRouteMixin`
- 加上 FC 預設 options
- 自動產生 opposite-chip carve-out 幾何

代表性例子：

- `transmon_pocket.py`
- `transmon_cross.py`
- `line_tee.py`
- `coupled_line_tee.py`
- `meandered.py`
- `straight_path.py`
- `pathfinder.py`

如果你只是想把 stock planar component 變成 FC 版本，而不想整個從頭重寫，這是最推薦的路。

### 類別 B：根目錄下的 `FC_*.py`

這些檔案是「真正客製化的 FC-native 元件」。

通常是因為單靠 mixin 不夠，所以需要自己明確控制：

- flip-chip layer mapping
- signal / subtract / carve-out 的分工
- FC 專用的 geometry naming
- 客製 ports 或 layout 行為

重要例子：

- `FC_qubit_pocket.py`
  一個較通用的 FC qubit pocket primitive，自己控制 pads、antennas、subtract 與 carve-out。

- `FC_line_tee.py`
  flip-chip tee / hanger 類 coupler，自己生成 carve-out。

- `FC_coupled_line_tee.py`
  耦合 tee 結構的 FC 版本，直接控制幾何生成。

- `FC_cap_n_interdigital.py`
- `FC_cap_n_interdigital_tee.py`
- `FC_round_cap_n_interdigital.py`
- `FC_round_cap_n_interdigital_tee.py`
- `FC_round_tee.py`
  各種 FC coupler / capacitor primitive，包含 rounded 版本。

- `FC_tunable_coupler_01.py`
- `FC_tunable_coupler_02.py`
  flip-chip tunable coupler。

- `FC_Fluxonium.py`
  客製的 FC 取向 qubit 實作。

- `FC_lump_port.py`
- `FC_lump_port_inline.py`
  模擬流程用的 lumped port 元件。

- `FC_transition_piece.py`
  FC CPW 連接用的 transition / taper 幫手元件。

### 類別 C：工具型、模板型、輔助型檔案

這些檔案比較像支援開發、幾何實驗或特殊裝置，而不是主要的 FC wrapper 主線。

例子：

- `BridgeFreeJJ.py`
  bridge-free Josephson junction 幾何。

- `fillet_q.py`
  帶 fillet 的 qubit 幾何。

- `self_define.py`
  一些可重複利用的小幾何 primitive，例如 `Cross`、`Fillet_vertex`、`Rect_fillet`。

- `my_qcomponent.py`
  建新元件時可以參考的最小模板。

- `round_tee.py`
- `round_cap_n_interdigital_tee.py`
- `FC_RouteMeander.py`
  這些可視為輔助或較早期風格的實作，之後若要寫新 FC 元件，也很適合拿來當參考。

## 2. 這個資料夾在功能上做了什麼

如果從工作流程的角度來看，這個資料夾主要提供四種能力。

### 功能 1：把 planar component 轉成 FC-aware component

`fc_usercomponents/` 這批 wrapper 的作用，是把 upstream Qiskit Metal component 加上：

- `chip`
- `carve_out_chip`
- `carve_out_extend_size`
- 必要時的 carve-out layer 行為

這樣就能用最少的程式重複，把既有 planar 元件拉進雙晶片或 flip-chip layout 流程。

### 功能 2：提供 mixin 不夠用時的 FC-native primitive

有些 flip-chip 結構不能只靠 wrapper。根目錄下的 `FC_*.py` 就是在補這一塊，直接控制：

- source-chip 的 metal
- subtract geometry
- opposite-chip carve-out
- 明確 layer mapping
- FC renderer 會依賴的 geometry naming

### 功能 3：支援 simulation 導向的 layout 元件

這個資料夾裡有不少檔案其實是為了後續 EM 或 GDS workflow 服務，例如：

- lumped ports
- inline ports
- transition pieces
- tunable couplers
- bridge-free junction structures

如果你的 layout 之後要進 semantic GDS export 或 EM model generation，這些元件會很有用。

### 功能 4：提供本地幾何開發與實驗空間

這裡有些檔案也很適合當作之後擴充的模板或實驗場。

例如：

- 測試新的 fillet 做法
- 試作新的 FC primitive
- 嘗試新的 geometry naming
- 把與你 workflow 高度綁定的 helper 留在本地，不必硬塞回 upstream core library

## 3. 這個資料夾最實際的定位

實務上，可以把這個資料夾理解成：

- 既有 library component 的本地 FC adaptation layer
- 不適合原封不動放回 upstream 的 FC 專用 primitive 集合
- 你自己的 flip-chip workflow 開發區

## 4. 往後建議的使用方式

之後要維護這個資料夾，最乾淨的慣例是：

- 如果是改造 upstream planar component，就優先放在 `fc_usercomponents/`
- 如果是全新的 FC-native primitive，就放根目錄的 `FC_*.py`
- 如果元件會交給 `design.renderers.FCgds` 匯出，命名要維持穩定
- 新開發時可以直接從 `my_qcomponent.py` 或既有 FC component 當模板開始

## 5. 和 FC GDS Renderer 的關係

這個資料夾和：

- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`

之間有非常直接的關係。

因為 renderer 會依賴：

- 穩定的 class name
- 穩定的 `qgeometry.name`
- 一致的 chip / layer 放置方式

所以 `user_components/` 裡的元件不只是畫 layout 的工具而已，它們同時也是整條 flip-chip GDS export pipeline 的來源物件。
