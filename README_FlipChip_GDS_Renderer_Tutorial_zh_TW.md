# Flip-Chip GDS Renderer 教學

這份文件說明這個 repository 內的 flip-chip GDS renderer 要怎麼使用。它的實作檔案在：

- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`

在這個 fork 裡，renderer class 名稱是：

- `MyGDSRenderer`

而它在：

- `src/qiskit_metal/config.py`

裡被註冊成：

- `FCgds`

所以這份教學假設你現在已經能這樣取到它：

```python
renderer = design.renderers.FCgds
```

## 1. 這個 Renderer 多做了什麼

這個 renderer 保留了原本 Qiskit Metal 的 GDS 幾何輸出流程，但另外加進了幾個針對 flip-chip 與 simulation workflow 很重要的能力：

- semantic simulation object reconstruction
- multi-chip hierarchical export
- packaging layer support
- semantic sidecar metadata export

它的目標不是用啟發式方式去猜 topology，而是根據：

- component naming grammar
- `semantic_rules`
- `semantic_map`

去穩定且可重現地重建 simulation-object ownership。

## 2. 命名規則

### 2.1 建議的 component naming grammar

component name 建議遵守：

```text
<SIM_TYPE>__<OBJECT_KEY>__<LOCAL_COMPONENT>
```

或短格式：

```text
<SIM_TYPE>__<OBJECT_KEY>
```

例如：

```text
FQ__Q1
RO__Q1__route
RO__MAIN__tee
CL__FAST
CPL__Q1_Q2__cap
BUS__LEFT_RIGHT__res
FL__FL_top
PF__RO1
```

這個 grammar 最好把每一段想成各自有不同職責。

- `SIM_TYPE`
  代表這個 simulation object 的語意類型，例如 qubit、readout resonator、feedline、coupler。
- `OBJECT_KEY`
  代表同一個 simulation object 共享的身份識別。
- `LOCAL_COMPONENT`
  代表可選的本地子名稱，用來說明是哪個局部結構或哪個來源 component 產生這段幾何。

一個很重要的預設行為是：

- renderer 不會把完整三段名稱直接當成最後的 ownership key
- 在預設情況下，它會把 ownership 收斂成 `<ABBREVIATION>__<OBJECT_KEY>`
- 所以 `LOCAL_COMPONENT` 主要是幫助可讀性，本身不會自動拆成新的 simulation object

例如：

```text
RO__Q1__tee
RO__Q1__route
RO__Q1__pad
```

預設都會歸到同一個 simulation object：

```text
RO__Q1
```

### 2.2 `SIM_TYPE` 到底代表什麼

`SIM_TYPE` 用來表示這個 object 的語意類型。

它可以用兩種寫法：

- canonical name，例如 `readout_resonator`
- abbreviation，例如 `RO`

renderer 會透過 `naming_map` 把這兩種寫法正規化。

例如下面兩個名稱：

```text
readout_resonator__Q1__tee
RO__Q1__tee
```

對 renderer 來說是等價的，最後都會正規化成：

```text
RO__Q1
```

實務上可以這樣理解：

- `semantic_rules` 和 `semantic_map` 內建議用 canonical name，比較好讀
- 匯出後的 cell name 則會使用 abbreviation，名稱比較短

常見的 `SIM_TYPE` 例子：

- `FQ` 或 `fluxonium_qubit`
- `TQ` 或 `transmon_qubit`
- `RO` 或 `readout_resonator`
- `CL` 或 `charge_line`
- `FL` 或 `feedline`
- `CPL` 或 `coupler`

### 2.3 `OBJECT_KEY` 到底代表什麼

`OBJECT_KEY` 會被當成 opaque semantic token，renderer 不應該把它當成 topology 或數值資訊去解析。

建議支援格式：

```text
[A-Za-z0-9_-]+
```

例如：

```text
1
Q1
Q1_Q2
MAIN
LEFT_RIGHT
Q17_XY
BUS_A
```

`OBJECT_KEY` 最重要的是一致性，不是它內部長什麼樣。

例如：

- `RO__Q1__tee` 和 `RO__Q1__route` 會被視為同一個 simulation object，因為兩者都用了 `Q1`
- `RO__Q1__tee` 和 `RO__Q2__tee` 會被視為不同 simulation object，因為 `OBJECT_KEY` 不同

好的 `OBJECT_KEY` 用法：

- qubit id，例如 `Q1`
- 成對 id，例如 `Q1_Q2`
- bus id，例如 `LEFT_RIGHT`
- 特別命名物件，例如 `MAIN`

不好的用法：

- tee 用一個 key、route 用另一個 key、pad 再用第三個 key，但其實它們本來應該屬於同一個 readout object

### 2.4 `LOCAL_COMPONENT` 到底代表什麼

`LOCAL_COMPONENT` 是可選欄位。

當多個來源 component 或多個局部子結構其實都屬於同一個 semantic object，但你又希望名稱保持可讀性時，就很適合加這一段。

常見例子：

- `RO__Q1__tee`
- `RO__Q1__route`
- `RO__Q1__cap`
- `FL__MAIN__left_arm`

預設情況下：

- `LOCAL_COMPONENT` 不會自動生成新的 simulation object
- 它主要是人類可讀的後綴
- 如果你需要，它也可以在 `semantic_rules` template 中透過 `{local_component}` 被使用

這對於「一個 semantic object 是由多個 QComponent 組起來」或「一個 QComponent 內有多種 geometry 群組」的情況很有幫助。

### 2.5 Renderer 會怎麼用這三段資訊

在只靠 naming grammar 的預設情況下，renderer 的流程大致是：

1. 先解析 `SIM_TYPE`
2. 再透過 `naming_map` 把它正規化
3. 保留 `OBJECT_KEY`
4. 除非 `semantic_rules` 或 `semantic_map` 額外使用，否則 `LOCAL_COMPONENT` 不會進入最後的 ownership key

所以像下面這幾個名稱：

```text
readout_resonator__Q1__tee
readout_resonator__Q1__route
RO__Q1__pad
```

最後都會收斂成：

```text
RO__Q1
```

這是理解這個 renderer 最重要的觀念之一：

- `SIM_TYPE` 告訴 renderer「這是什麼類型的物件」
- `OBJECT_KEY` 告訴 renderer「這是哪一個物件實例」
- `LOCAL_COMPONENT` 告訴 renderer「這是這個物件的哪一個局部結構」

### 2.6 分隔規則與常見錯法

例如這種名稱：

```text
FL_FL_top__path1
```

並不符合 grammar，因為前兩段之間少了一個 `__`。正確應該是：

```text
FL__FL_top__path1
```

這個 renderer 目前採用 strict naming，不建議依賴 renderer 幫你容錯或猜測原意。

另外也要注意：

- `OBJECT_KEY` 和 `LOCAL_COMPONENT` 內可以有單一底線 `_`
- 雙底線 `__` 是保留給 grammar 分段用的
- 空白或超出 `[A-Za-z0-9_-]` 的符號都不合法

好的例子：

```text
RO__Q1_Q2__left_stub
FL__MAIN_BUS__segment_a
```

不好的例子：

```text
RO__Q1__left__stub
FL__MAIN BUS__segment
RO__Q1/2__tee
```

## 3. 最小使用範例

```python
renderer = design.renderers.FCgds

renderer.options.cheese.view_in_file = {}
renderer.options.no_cheese.view_in_file = {}

renderer.options["packaging_dict"] = {
    "global": {
        "vacuum": 2001,
    },
    "C_chip": {
        "ground": 8,
        "substrate": 1201,
    },
    "Q_chip": {
        "ground": 108,
        "substrate": 1301,
    },
}

renderer.options.naming_map = {
    "readout_resonator": "RO",
    "charge_line": "CL",
    "fluxonium_qubit": "FQ",
    "transmon_qubit": "TQ",
    "coupler": "CPL",
    "feedline": "FL",
    "purcell_filter": "PF",
}

renderer.options.semantic_rules = {
    "FCQubitPocket": {
        r"res_.*": "readout_resonator__{object_key}",
        r"chg_.*": "charge_line__{object_key}",
        r".*pad.*": "fluxonium_qubit__{object_key}",
        r".*_jj.*": "fluxonium_qubit__{object_key}",
    },
}

renderer.export_to_gds("flipchip_layout.gds")
```

## 4. `naming_map`

`naming_map` 的作用，是把：

- canonical semantic meaning
- exported abbreviation

分開處理。

範例：

```python
renderer.options.naming_map = {
    "readout_resonator": "RO",
    "charge_line": "CL",
    "fluxonium_qubit": "FQ",
    "transmon_qubit": "TQ",
    "coupler": "CPL",
    "feedline": "FL",
    "purcell_filter": "PF",
}
```

這代表：

- `readout_resonator__Q1` 會被正規化成 `RO__Q1`
- `feedline__FL_top` 會被正規化成 `FL__FL_top`

建議在 `semantic_rules` 和 `semantic_map` 內盡量用 canonical name，會比較好讀：

```python
"readout_resonator__{object_key}"
```

而不是直接寫縮寫：

```python
"RO__{object_key}"
```

## 5. `semantic_rules` 與 `semantic_map`

這兩者扮演的角色不同。

### 5.1 `semantic_rules`

`semantic_rules` 是 renderer-wide 的類別規則。

- key 是 component class name
- 用 regex 去比對 `qgeometry.name`
- 適合當作很多元件共用的預設政策

範例：

```python
renderer.options.semantic_rules = {
    "RouteStraight": {
        r"trace": "{canonical_type}__{object_key}",
    },
    "CoupledLineTee": {
        r"prime_.*": "feedline__{object_key}",
        r"second_.*": "readout_resonator__{object_key}",
    },
}
```

可用的 template variable 包括：

- `type`
- `canonical_type`
- `abbreviation`
- `object_key`
- `local_component`

### 5.2 `semantic_map`

`semantic_map` 是掛在單一 component instance 上的 local override。

- 它存在 `component.options.semantic_map`
- key 是 `qgeometry.name` 的 exact match
- 適合處理少數特例

範例：

```python
design.components["FL__FLTop__CLT"].options["semantic_map"] = {
    "prime_cpw": "feedline__FLTop",
    "second_cpw": "readout_resonator__FLTop",
}
```

### 5.3 優先順序

renderer 會依這個順序決定 geometry 屬於哪個 semantic object：

1. `component.options.semantic_map`
2. `renderer.options.semantic_rules`
3. 從 component naming grammar 做 fallback reconstruction

建議的做法是：

- 大部分規則放在 `semantic_rules`
- 真的少數例外再用 `semantic_map`

## 6. Semantic Hierarchy

預設值是：

```python
renderer.options["semantic_hierarchy"] = "True"
```

啟用後，最後輸出的 GDS hierarchy 會以 semantic object 與 packaging 結構為主，而不是把 raw construction cells 直接暴露在 `TOP` 底下。

典型結果如下：

```text
TOP
├── ENV__VACUUM
├── CHIP__C_chip
│   ├── C_chip__SUBSTRATE
│   ├── C_chip__GROUND
│   ├── C_chip__RO__Q1
│   ├── C_chip__CL__Q1
│   └── ...
└── CHIP__Q_chip
    ├── Q_chip__SUBSTRATE
    ├── Q_chip__GROUND
    ├── Q_chip__FQ__Q1
    └── ...
```

正常情況下你應該看到：

- `TOP` 底下只有 environment cell 與 chip container
- 內部 helper cells 不會直接裸露在 final `TOP`

## 7. Packaging 支援

`packaging_dict` 用來描述 vacuum、substrate、ground layer：

```python
renderer.options["packaging_dict"] = {
    "global": {
        "vacuum": 2001,
    },
    "C_chip": {
        "ground": 8,
        "substrate": 1201,
    },
    "Q_chip": {
        "ground": 108,
        "substrate": 1301,
    },
}
```

語意如下：

- `global.vacuum` 會建立 `ENV__VACUUM`
- 每個 chip 可以有自己的 `GROUND` 與 `SUBSTRATE`
- ground cell 會以每個 chip / layer target 只建立一次，避免重複 ground plane

目前 package cell 的命名是 chip-first：

- `C_chip__GROUND`
- `C_chip__SUBSTRATE`
- `Q_chip__GROUND`
- `Q_chip__SUBSTRATE`

## 8. Semantic Cell 命名選項

### 8.1 `semantic_cell_chip_prefix`

控制 semantic object cell 是否帶 chip prefix：

```python
renderer.options["semantic_cell_chip_prefix"] = "True"
```

例如：

- `True`：`C_chip__RO__Q1`
- `False`：`RO__Q1`

在 multi-chip layout 下，通常建議保留開啟，避免 cell name 衝突。

### 8.2 `chip_container_prefix`

控制 chip container cell 是否採用 `CHIP__<chip>` 形式：

```python
renderer.options["chip_container_prefix"] = "True"
```

### 8.3 `package_cell_chip_prefix`

控制 package helper cells 是否用 chip-qualified naming：

```python
renderer.options["package_cell_chip_prefix"] = "True"
```

對 multi-chip export 來說，通常也建議維持開啟。

## 9. `semantic_component_subcells`

如果你想讓每個 simulation object 底下還能再拆成 per-component child cells，可以開啟：

```python
renderer.options["semantic_component_subcells"] = "True"
```

效果如下：

- `False`：geometry 直接寫進 semantic object cell
- `True`：geometry 先依 semantic object 分組，再拆成每個 component 的 child cell

例如：

```text
C_chip__CL__Q1
└── C_chip__CL__Q1__COMP__CL__Q1__path
```

這樣比較利於追蹤來源，但 hierarchy 會更深。

如果你想讓 GDS cell tree 最乾淨，建議維持：

```python
renderer.options["semantic_component_subcells"] = "False"
```

## 10. 常用 Helper Method

### 10.1 `inspect_component_geometry()`

用來快速檢查每種 component class 產生了哪些 `qgeometry.name`：

```python
renderer.inspect_component_geometry(pretty_print=True)
```

這對寫 `semantic_rules` 非常有幫助。

### 10.2 `generate_default_semantic_template()`

自動產生一份可當起點的 `semantic_rules` template：

```python
renderer.generate_default_semantic_template(pretty_print=True)
```

輸出會類似：

```python
{
    "RouteMeander": {
        "trace": "{canonical_type}__{object_key}",
    }
}
```

### 10.3 `set_semantic_group()` / `set_semantic_groups()`

你可以直接把多個 component 指定到同一個 semantic object。

例如：

```python
renderer.set_semantic_group("RO__MAIN", ["RO__MAIN__route", "RO__MAIN__tee"])
```

也可以一次設多組：

```python
renderer.set_semantic_groups({
    "RO__MAIN": ["RO__MAIN__route", "RO__MAIN__tee"],
    "BUS__LEFT_RIGHT": ["BUS__LEFT_RIGHT__res"],
})
```

### 10.4 `debug_print_final_hierarchy()`

輸出最後的 hierarchy 方便檢查：

```python
renderer.debug_print_final_hierarchy()
```

## 11. 輸出的 Sidecar 檔案

除了 `.gds` 本體之外，renderer 還會輸出幾個 sidecar metadata 檔案：

- `semantic_export_map.json`
- `semantic_metadata.json`
- `semantic_naming_map.json`

它們的意義大致如下：

- `semantic_naming_map.json`：保存 canonical type 到 abbreviation 的對應
- `semantic_export_map.json`：保存 semantic cell 對應回來源 geometry 的資訊

如果你後面要接 HFSS/Q3D 或其他自動化流程，這些檔案會很有用。

## 12. 常見問題

### 12.1 為什麼有些 geometry 沒有被分到預期的 semantic object？

先檢查這三件事：

1. component name 是否符合 strict grammar
2. `semantic_rules` 的 regex 是否真的 match 到 `qgeometry.name`
3. component 上是否有 local `semantic_map` 覆蓋掉全域規則

### 12.2 為什麼 route 在 pin 附近看起來像 taper？

很多時候這不是 renderer 的問題，而是 pin 定義的位置或方向問題。

對 `QRoute` 來說，lead 的生成會依賴 pin 的：

- `middle`
- `normal`

如果 pin 放太裡面，而不是放在真正的連接邊界，route 的 trace 或 subtract 幾何可能就會和元件內部重疊，視覺上像 taper。

建議修正方式：

- pin 放在真正的連接邊界
- pin 的 normal 要朝 route 預期離開元件的方向

### 12.3 Renderer 要不要自動容忍錯誤命名？

通常不建議。

太寬鬆的容忍反而會把真正的 naming 問題藏起來，也會讓 semantic reconstruction 變得不穩定。

## 13. 建議工作流程

最乾淨的流程通常是：

1. 先把 component naming 整理成符合 grammar
2. 用 `inspect_component_geometry()` 看幾何名稱
3. 先定義大範圍的 `semantic_rules`
4. 只有少數例外才補 `semantic_map`
5. 用 `debug_print_final_hierarchy()` 驗證結果
6. 最後再 export GDS

## 14. 總結

這個 renderer 特別適合用在：

- multi-chip superconducting layouts
- feedline、resonator、qubit、coupler 的 semantic grouping
- 之後還要接 HFSS / Q3D automation 的 GDS workflow

它的核心設計原則是：

- 幾何生成仍由 QComponents 負責
- renderer 只做 deterministic semantic reconstruction
- 不在 GDS 匯出階段猜 topology 或 connectivity
