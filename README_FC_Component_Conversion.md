# Converting a Planar QComponent into a Flip-Chip Version

This guide explains how this repository converts existing Qiskit Metal planar components into flip-chip-ready components, and how to extend that pattern when you add new components later.

The key reference files in this fork are:

- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/fc_flipchip.py`
- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/transmon_pocket.py`
- `src/qiskit_metal/qlibrary/user_components/fc_usercomponents/meandered.py`
- `src/qiskit_metal/qlibrary/user_components/FC_line_tee.py`
- `src/qiskit_metal/qlibrary/user_components/FC_qubit_pocket.py`

## 1. Two Supported Conversion Patterns

This repository currently uses two different flip-chip conversion styles.

### Pattern A: Thin wrapper around an existing upstream component

Use this when the original planar component already generates the correct metal/subtract geometry and you mainly want to add an opposite-chip carve-out.

This is the preferred pattern for most existing Qiskit Metal library components.

Examples:

- `fc_usercomponents/transmon_pocket.py`
- `fc_usercomponents/line_tee.py`
- `fc_usercomponents/coupled_line_tee.py`
- `fc_usercomponents/meandered.py`

### Pattern B: Full custom flip-chip component

Use this when the planar version is not enough and you need one or more of the following:

- dedicated per-layer routing for signal, ground, and carve-out
- different carve-out widths for different geometry groups
- custom qgeometry naming for renderer semantic rules
- custom pins, ports, or layer mappings
- a geometry flow that is easier to control by rewriting `make()`

Examples:

- `FC_qubit_pocket.py`
- `FC_line_tee.py`
- `FC_coupled_line_tee.py`
- `FC_transition_piece.py`

## 2. The Shared Flip-Chip Helpers

The reusable logic lives in `fc_usercomponents/fc_flipchip.py`.

It provides:

- `build_fc_default_options(base_defaults)`
- `build_fc_route_default_options(base_defaults)`
- `FlipChipCarveOutMixin`
- `FlipChipRouteMixin`

### `build_fc_default_options()`

This helper is used for regular `QComponent` / `BaseQubit` style components.

It adds these options on top of the original defaults:

- `chip`
- `carve_out_chip`
- `carve_out_extend_size`
- `carve_out_layer`

### `build_fc_route_default_options()`

This helper is used for `QRoute` style components.

It adds:

- `chip='C_chip'`
- `carve_out_chip='Q_chip'`
- `carve_out_extend_size`

### `FlipChipCarveOutMixin`

This mixin calls the original `make()` first, then:

1. collects the component's generated `poly` and `path` geometry
2. converts paths into buffered polygons when needed
3. prefers subtract geometry when present
4. unions the footprint
5. expands it by `carve_out_extend_size`
6. writes a subtract polygon named `carve_out` onto `carve_out_chip`

This is ideal for planar components whose existing geometry already describes the correct keep-out footprint.

### `FlipChipRouteMixin`

This mixin is for `QRoute`-based components.

After the original route is generated, it:

1. reads `self.get_points()`
2. rebuilds the route centerline as a `LineString`
3. computes the full CPW width as `trace_width + 2 * trace_gap`
4. adds the extra flip-chip margin
5. writes a subtract path on the opposite chip

This is the cleanest way to convert a planar route into an FC route.

## 3. Recommended Decision Rule

Before you start coding, decide which pattern fits your component.

Use the thin-wrapper mixin pattern if:

- the original component already has clean `poly` / `path` / `junction` output
- the opposite-chip carve-out can be derived from the existing footprint
- you want to preserve the original class behavior as much as possible

Use the full custom rewrite pattern if:

- the FC version needs dedicated signal and ground layers
- different geometry groups need different carve-out margins
- the upstream file is too planar-specific
- the renderer will need stable custom geometry names
- the FC version is conceptually a new primitive, not just an adapted old one

## 4. Pattern A: Thin-Wrapper Conversion

### 4.1 Regular component example

If the original component is a normal planar `QComponent` or `BaseQubit`, create a new file in:

`src/qiskit_metal/qlibrary/user_components/fc_usercomponents/`

Then wrap the upstream class like this:

```python
from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket as _TransmonPocket

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocket(FlipChipCarveOutMixin, _TransmonPocket):
    default_options = build_fc_default_options(_TransmonPocket.default_options)
```

Why this works:

- the original geometry creation stays untouched
- the FC behavior is added after `super().make()`
- the original class name is preserved, which keeps renderer rules simpler

### 4.2 Route component example

For a `QRoute` component, use the route mixin:

```python
from qiskit_metal.qlibrary.tlines.meandered import RouteMeander as _RouteMeander

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteMeander(FlipChipRouteMixin, _RouteMeander):
    default_options = build_fc_route_default_options(_RouteMeander.default_options)
```

This is the pattern already used by:

- `fc_usercomponents/meandered.py`
- `fc_usercomponents/straight_path.py`
- `fc_usercomponents/framed_path.py`
- `fc_usercomponents/mixed_path.py`
- `fc_usercomponents/anchored_path.py`
- `fc_usercomponents/pathfinder.py`

### 4.3 Thin-wrapper checklist

When using the thin-wrapper pattern:

1. import the upstream component under a private alias such as `_TransmonPocket`
2. put the mixin before the upstream class in the inheritance list
3. rebuild `default_options` with the helper
4. keep the class name stable unless you have a strong reason to rename it
5. test that both source-chip geometry and opposite-chip carve-out appear

## 5. Pattern B: Full Custom FC Rewrite

For some components, a mixin is not enough.

`FC_qubit_pocket.py` and `FC_line_tee.py` are good examples:

- they define FC-specific options directly
- they control dedicated layer assignment
- they decide exactly which geometry becomes signal, subtract, or carve-out
- they preserve stable geometry names for the renderer

### 5.1 Typical structure

A full custom FC component usually does the following inside `make()`:

1. define the core metal geometry
2. define subtract / no-fill geometry
3. optionally define a separate carve-out footprint
4. rotate and translate everything together
5. add geometry to the source chip with explicit layers
6. add the opposite-chip carve-out with explicit FC layer mapping
7. add pins

### 5.2 Skeleton example

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

## 6. Naming and Renderer Compatibility

If the FC version will be exported through `design.renderers.FCgds`, keep these points in mind:

- class names matter because `semantic_rules` are keyed by QComponent class name
- `add_qgeometry()` entry names matter because renderer rules often match `qgeometry.name`
- stable naming is better than clever naming

For thin-wrapper components, preserving the original class name is usually helpful.

For full custom components, choose names that are predictable and document them early.

Examples already used in this repository:

- `res_ant`
- `chg_ant`
- `res_straight`
- `chg_straight`
- `top_pad`
- `bot_pad`
- `carve_out`

## 7. Practical Workflow for New FC Conversions

When you convert a new planar component in this repository, the recommended workflow is:

1. Find the upstream source component and inspect its `make()`.
2. Decide whether the thin-wrapper mixin pattern is enough.
3. If yes, add a file under `fc_usercomponents/`.
4. If no, start from a copy or adaptation of the upstream code and create a new `FC_*.py` component.
5. Keep geometry names stable and meaningful.
6. Verify the qgeometry tables on both chips.
7. If the component will be exported by `FCgds`, add or update renderer `semantic_rules` as needed.

## 8. Suggested Local Test Procedure

After creating a new FC component, test these items:

```python
component = ...

design.qgeometry.tables['poly'][['component', 'name', 'chip', 'layer', 'subtract']]
design.qgeometry.tables['path'][['component', 'name', 'chip', 'layer', 'subtract']]
```

Check that:

- the original geometry is on the intended source chip
- the opposite-chip carve-out exists
- subtract flags are correct
- layer mapping is correct
- pins still attach in the expected locations

If the component is route-based, also verify:

- `self.get_points()` returns the expected route path
- fillet behavior on the carve-out matches the route behavior closely enough

## 9. Recommended Repository Convention

For future work in this fork, this is the cleanest convention:

- use `fc_usercomponents/` for adapted upstream library components
- use root-level `FC_*.py` files for new FC-native primitives
- use the mixin pattern by default
- only rewrite `make()` when the FC requirements truly differ from the planar original

That keeps the codebase easier to maintain and makes future upstream sync work much simpler.
