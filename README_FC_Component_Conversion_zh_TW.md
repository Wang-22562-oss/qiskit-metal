# 如何把平面 QComponent 轉成 Flip-Chip 版本

這份教學說明這個 repository 目前是如何把既有的 Qiskit Metal 平面元件改造成 flip-chip 元件，以及之後如果你新增新的 planar component，建議怎麼延續這個模式。

最重要的參考檔案如下：

- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/fc_flipchip.py`
- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/transmon_pocket.py`
- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/meandered.py`
- `src/qiskit_metal/qlibrary/user_components/FC_line_tee.py`
- `src/qiskit_metal/qlibrary/user_components/FC_qubit_pocket.py`

## 1. 目前支援的兩種轉換模式

這個 repository 目前主要使用兩種 flip-chip 轉換方式。

### 模式 A：包一層薄 wrapper，沿用 upstream component

當原本的 planar component 已經能正確生成 metal/subtract 幾何，而你只是想額外加上對側晶片的 carve-out 時，最適合用這種方式。

這是目前最推薦、也最容易維護的做法。

範例：

- `fc_usercomponents/transmon_pocket.py`
- `fc_usercomponents/line_tee.py`
- `fc_usercomponents/coupled_line_tee.py`
- `fc_usercomponents/meandered.py`

### 模式 B：完整重寫一個 FC 元件

如果原本的 planar 版本不夠用，而你需要以下其中一種能力，就比較適合直接寫一個新的 FC 元件：

- signal、ground、carve-out 要分不同 layer
- 不同幾何群組需要不同的 carve-out buffer
- renderer semantic rules 需要穩定且客製的 qgeometry 名稱
- pins、ports、layer mapping 需要重新定義
- 幾何流程本身就更適合直接重寫 `make()`

範例：

- `FC_qubit_pocket.py`
- `FC_line_tee.py`
- `FC_coupled_line_tee.py`
- `FC_transition_piece.py`

## 2. 共用的 Flip-Chip Helper 在哪裡

核心共用邏輯放在 `fc_usercomponents/fc_flipchip.py`。

它提供了：

- `build_fc_default_options(base_defaults)`
- `build_fc_route_default_options(base_defaults)`
- `FlipChipCarveOutMixin`
- `FlipChipRouteMixin`

### `build_fc_default_options()`

這個 helper 主要給一般 `QComponent` / `BaseQubit` 類型的元件使用。

它會在原本的 default options 上再加上：

- `chip`
- `carve_out_chip`
- `carve_out_extend_size`
- `carve_out_layer`

### `build_fc_route_default_options()`

這個 helper 是給 `QRoute` 類型元件使用的。

它會補上：

- `chip='C_chip'`
- `carve_out_chip='Q_chip'`
- `carve_out_extend_size`

### `FlipChipCarveOutMixin`

這個 mixin 會先呼叫原本元件的 `make()`，接著：

1. 收集元件產生的 `poly` 與 `path` 幾何
2. 必要時把 path buffer 成 polygon
3. 如果有 subtract geometry，優先使用 subtract footprint
4. 把幾何 union 成一個整體 footprint
5. 用 `carve_out_extend_size` 再往外 buffer
6. 在 `carve_out_chip` 上新增一個名為 `carve_out` 的 subtract polygon

這很適合拿來處理原本 footprint 就已經很合理的 planar 元件。

### `FlipChipRouteMixin`

這個 mixin 專門給 `QRoute` 類型元件用。

在原本 route 生完之後，它會：

1. 讀取 `self.get_points()`
2. 重建 route centerline 的 `LineString`
3. 用 `trace_width + 2 * trace_gap` 算完整 CPW 寬度
4. 加上 flip-chip 額外 buffer
5. 在對側晶片上寫入 subtract path

如果你的元件本質上是一條 route，這通常是最乾淨的改法。

## 3. 如何判斷該用哪一種模式

在開始寫之前，先判斷你的元件比較適合哪一種。

適合用薄 wrapper mixin 的情況：

- 原本元件已經有乾淨的 `poly` / `path` / `junction` 輸出
- 對側晶片 carve-out 可以直接由既有 footprint 推出
- 你希望最大程度保留原本 class 的行為

適合用完整重寫 FC 元件的情況：

- FC 版本需要專門的 signal / ground layer 分工
- 不同幾何群組要用不同 carve-out margin
- upstream 原始檔太偏 planar-only
- renderer 需要穩定的客製 geometry naming
- 這個 FC 版本本質上已經是新 primitive，不只是舊元件加一層口袋

## 4. 模式 A：薄 Wrapper 轉換法

### 4.1 一般 component 範例

如果原本元件是一般 planar `QComponent` 或 `BaseQubit`，就在：

`src/qiskit_metal/qlibrary/user_components/fc_usercomponents/`

下面新增一個檔案，寫法可以像這樣：

```python
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket as _TransmonPocket

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocket(FlipChipCarveOutMixin, _TransmonPocket):
    default_options = build_fc_default_options(_TransmonPocket.default_options)
```

這樣做的好處是：

- 原本的 geometry 生成邏輯不用動
- FC 行為是在 `super().make()` 之後額外補上
- class name 可以維持原本名稱，renderer rule 也比較容易延續

### 4.2 Route 元件範例

如果原本是 `QRoute` 類型，就改用 route mixin：

```python
from qiskit_metal.qlibrary.tlines.meandered import RouteMeander as _RouteMeander

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteMeander(FlipChipRouteMixin, _RouteMeander):
    default_options = build_fc_route_default_options(_RouteMeander.default_options)
```

這也是目前這個 repository 已經在用的模式：

- `fc_usercomponents/meandered.py`
- `fc_usercomponents/straight_path.py`
- `fc_usercomponents/framed_path.py`
- `fc_usercomponents/mixed_path.py`
- `fc_usercomponents/anchored_path.py`
- `fc_usercomponents/pathfinder.py`

### 4.3 薄 Wrapper 的檢查清單

當你用薄 wrapper 模式時，建議確認：

1. import upstream component 時先取一個私有 alias，例如 `_TransmonPocket`
2. inheritance 順序要讓 mixin 放在前面
3. `default_options` 要用 helper 重建
4. 除非真的有必要，不然 class name 盡量維持穩定
5. 測試時要確認 source chip 與 opposite-chip carve-out 都有生成

## 5. 模式 B：完整重寫 FC 元件

有些元件只靠 mixin 不夠。

`FC_qubit_pocket.py` 和 `FC_line_tee.py` 就是很好的例子：

- 它們直接定義 FC 專用的 options
- 它們自己控制 layer 分配
- 它們自己決定哪些幾何是 signal、subtract、carve-out
- 它們也能維持 renderer 需要的穩定 geometry naming

### 5.1 常見結構

一個完整的 FC 元件通常在 `make()` 內會做這些事：

1. 先建立核心 metal geometry
2. 建立 subtract / no-fill geometry
3. 如果需要，另外建立 carve-out footprint
4. 把所有幾何一起 rotate / translate
5. 用明確 layer 寫入 source chip
6. 用明確 FC layer 寫入 opposite-chip carve-out
7. 最後再加 pins

### 5.2 骨架範例

```python
from qiskit_metal import Dict, draw
from qiskit_metal.qlibrary.core import QComponent


class FCNewComponent(QComponent):
    default_options = Dict(
        chip='C_chip',
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',
        layer_sig=1,
        layer_gnd=8,
        layer_carve_out=108,
    )

    def make(self):
        p = self.p

        signal_geom = ...
        subtract_geom = ...
        carve_out = ...

        items = [signal_geom, subtract_geom, carve_out]
        items = draw.rotate(items, p.orientation, origin=(0, 0))
        items = draw.translate(items, p.pos_x, p.pos_y)
        signal_geom, subtract_geom, carve_out = items

        self.add_qgeometry('poly',
                           {'signal_geom': signal_geom},
                           chip=p.chip,
                           layer=p.layer_sig)

        self.add_qgeometry('poly',
                           {'subtract_geom': subtract_geom},
                           chip=p.chip,
                           layer=p.layer_gnd,
                           subtract=True)

        self.add_qgeometry('poly',
                           {'carve_out': carve_out},
                           chip=p.carve_out_chip,
                           layer=p.layer_carve_out,
                           subtract=True)

        self.add_pin(...)
```

## 6. 命名與 Renderer 相容性

如果這個 FC 元件未來要交給 `design.renderers.FCgds` 匯出，請注意：

- class name 很重要，因為 `semantic_rules` 是用 QComponent class name 當 key
- `add_qgeometry()` 裡的名稱也很重要，因為 renderer 會用 `qgeometry.name` 去做對應
- 命名愈穩定、愈可預期，之後愈好維護

對薄 wrapper 來說，保留原本 class name 通常是有利的。

對完整客製 FC 元件來說，請一開始就選定穩定的 geometry naming。

這個 repository 目前已經使用的例子有：

- `res_ant`
- `chg_ant`
- `res_straight`
- `chg_straight`
- `top_pad`
- `bot_pad`
- `carve_out`

## 7. 新元件建議工作流程

之後如果你要在這個 repository 內新增一個 flip-chip component，最推薦的流程是：

1. 先找到 upstream source component，讀它的 `make()`
2. 判斷薄 wrapper mixin 是否就夠了
3. 如果夠，就放進 `fc_usercomponents/`
4. 如果不夠，就從 upstream 程式改寫出新的 `FC_*.py`
5. 幾何名稱盡量維持穩定且有意義
6. 驗證兩邊 chip 的 qgeometry table
7. 如果要走 `FCgds` 匯出，就一併補 renderer `semantic_rules`

## 8. 建議的本地測試方式

新增完元件之後，建議先檢查：

```python
component = ...

design.qgeometry.tables['poly'][['component', 'name', 'chip', 'layer', 'subtract']]
design.qgeometry.tables['path'][['component', 'name', 'chip', 'layer', 'subtract']]
```

確認以下幾點：

- 原始幾何有沒有落在你預期的 source chip
- opposite-chip carve-out 有沒有真的生成
- subtract flag 是否正確
- layer mapping 是否正確
- pins 是否仍然在預期位置

如果是 route 類型元件，也建議確認：

- `self.get_points()` 真的回傳了你預期的 route path
- carve-out 的 fillet 效果和 route 本身夠一致

## 9. 這個 Repository 建議延續的慣例

之後在這個 fork 裡，最乾淨的維護方式是：

- `fc_usercomponents/` 專門放「改造自 upstream library」的元件
- 根目錄的 `FC_*.py` 專門放「真正 FC-native 的新 primitive」
- 預設先用 mixin 模式
- 只有在 FC 需求真的和原始 planar 元件差很多時，再重寫 `make()`

這樣之後要維護、要對 upstream 同步，也會容易得多。
