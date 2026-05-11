# Flip-Chip GDS Renderer Tutorial

This document explains how to use the flip-chip GDS renderer implemented in:

- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`

In this repository, the renderer class is:

- `MyGDSRenderer`

and it is registered in:

- `src/qiskit_metal/config.py`

under the renderer name:

- `FCgds`

So this guide assumes you can already access it as:

```python
renderer = design.renderers.FCgds
```

## 1. What This Renderer Adds

This renderer keeps the normal Qiskit Metal GDS export path, but adds several flip-chip and simulation-oriented features:

- semantic simulation object reconstruction
- multi-chip hierarchical export
- packaging layer support
- semantic sidecar metadata export

Its goal is not to infer connectivity heuristically. Instead, it deterministically reconstructs simulation-object ownership from:

- component naming grammar
- `semantic_rules`
- `semantic_map`

## 2. Naming Grammar

### 2.1 Recommended component naming grammar

Component names should follow:

```text
<SIM_TYPE>__<OBJECT_KEY>__<LOCAL_COMPONENT>
```

or the short form:

```text
<SIM_TYPE>__<OBJECT_KEY>
```

Examples:

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

### 2.2 `OBJECT_KEY`

`OBJECT_KEY` is treated as an opaque semantic token. The renderer should not try to interpret it as topology or numeric structure.

Supported form:

```text
[A-Za-z0-9_-]+
```

Examples:

```text
1
Q1
Q1_Q2
MAIN
LEFT_RIGHT
Q17_XY
BUS_A
```

### 2.3 Avoid malformed names

For example:

```text
FL_FL_top__path1
```

is not valid because it breaks the `__` separator grammar. The correct form is:

```text
FL__FL_top__path1
```

This renderer uses strict naming rules. It is better to fix names at the component level than to rely on renderer-side guessing.

## 3. Minimal Usage Example

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

`naming_map` separates:

- canonical semantic meaning
- exported abbreviation

Example:

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

This means:

- `readout_resonator__Q1` is normalized to `RO__Q1`
- `feedline__FL_top` is normalized to `FL__FL_top`

It is recommended to keep `semantic_rules` and `semantic_map` readable by using canonical names:

```python
"readout_resonator__{object_key}"
```

instead of abbreviations directly:

```python
"RO__{object_key}"
```

## 5. `semantic_rules` and `semantic_map`

These two mechanisms serve different roles.

### 5.1 `semantic_rules`

`semantic_rules` are renderer-wide class-based rules.

- they are keyed by component class name
- they use regex against `qgeometry.name`
- they are best for default policies used across many components

Example:

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

Supported template variables include:

- `type`
- `canonical_type`
- `abbreviation`
- `object_key`
- `local_component`

### 5.2 `semantic_map`

`semantic_map` is a component-local override stored on a specific component instance.

- it lives on `component.options.semantic_map`
- keys are exact `qgeometry.name` matches
- it is best for exceptions or one-off overrides

Example:

```python
design.components["FL__FLTop__CLT"].options["semantic_map"] = {
    "prime_cpw": "feedline__FLTop",
    "second_cpw": "readout_resonator__FLTop",
}
```

### 5.3 Priority order

The renderer resolves geometry ownership in this order:

1. `component.options.semantic_map`
2. `renderer.options.semantic_rules`
3. fallback reconstruction from component naming grammar

Recommended practice:

- put the general policy in `semantic_rules`
- use `semantic_map` only for the exceptions

## 6. Semantic Hierarchy

By default:

```python
renderer.options["semantic_hierarchy"] = "True"
```

When enabled, the exported GDS top hierarchy is organized by semantic objects and package structure instead of exposing raw construction cells directly under `TOP`.

Typical final hierarchy:

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

You should expect:

- `TOP` to contain only the environment cell and chip containers
- internal helper cells such as layer-construction cells not to appear directly in the final `TOP`

## 7. Packaging Support

Use `packaging_dict` to describe vacuum, substrate, and ground layers:

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

Meaning:

- `global.vacuum` creates `ENV__VACUUM`
- each chip can define its own `GROUND` and `SUBSTRATE`
- the ground cell is generated once per chip/layer target to avoid duplicate ground planes

Current package-cell naming is chip-first:

- `C_chip__GROUND`
- `C_chip__SUBSTRATE`
- `Q_chip__GROUND`
- `Q_chip__SUBSTRATE`

## 8. Semantic Cell Naming Options

### 8.1 `semantic_cell_chip_prefix`

Controls whether semantic object cells include chip prefixes:

```python
renderer.options["semantic_cell_chip_prefix"] = "True"
```

Examples:

- `True`: `C_chip__RO__Q1`
- `False`: `RO__Q1`

For multi-chip layouts, keeping this enabled is usually safer because it guarantees uniqueness.

### 8.2 `chip_container_prefix`

Controls whether chip container cells use the `CHIP__<chip>` naming form:

```python
renderer.options["chip_container_prefix"] = "True"
```

### 8.3 `package_cell_chip_prefix`

Controls whether package helper cells are chip-qualified:

```python
renderer.options["package_cell_chip_prefix"] = "True"
```

For multi-chip export, it is usually best to leave this enabled.

## 9. `semantic_component_subcells`

If you want each simulation object to optionally break into per-component child cells, enable:

```python
renderer.options["semantic_component_subcells"] = "True"
```

Behavior:

- `False`: geometry is written directly into the semantic object cell
- `True`: geometry is grouped by semantic object and then split into per-component child cells

Example:

```text
C_chip__CL__Q1
└── C_chip__CL__Q1__COMP__CL__Q1__path
```

This is useful for traceability, but it makes the hierarchy deeper.

If you want the cleanest possible GDS cell tree, keep:

```python
renderer.options["semantic_component_subcells"] = "False"
```

## 10. Useful Helper Methods

### 10.1 `inspect_component_geometry()`

Use this to inspect which `qgeometry.name` values each component class produces:

```python
renderer.inspect_component_geometry(pretty_print=True)
```

This is very helpful when writing `semantic_rules`.

### 10.2 `generate_default_semantic_template()`

Auto-generates a starter `semantic_rules` template:

```python
renderer.generate_default_semantic_template(pretty_print=True)
```

Typical output:

```python
{
    "RouteMeander": {
        "trace": "{canonical_type}__{object_key}",
    }
}
```

### 10.3 `set_semantic_group()` / `set_semantic_groups()`

You can assign multiple components directly into the same semantic object.

Example:

```python
renderer.set_semantic_group("RO__MAIN", ["RO__MAIN__route", "RO__MAIN__tee"])
```

Or several groups at once:

```python
renderer.set_semantic_groups({
    "RO__MAIN": ["RO__MAIN__route", "RO__MAIN__tee"],
    "BUS__LEFT_RIGHT": ["BUS__LEFT_RIGHT__res"],
})
```

### 10.4 `debug_print_final_hierarchy()`

Prints the final exported hierarchy for validation:

```python
renderer.debug_print_final_hierarchy()
```

## 11. Exported Sidecar Files

In addition to the `.gds` file itself, the renderer writes sidecar metadata:

- `semantic_export_map.json`
- `semantic_metadata.json`
- `semantic_naming_map.json`

Meaning:

- `semantic_naming_map.json` stores canonical type to abbreviation mappings
- `semantic_export_map.json` maps semantic cells back to their source geometry entries

These files are useful for downstream HFSS/Q3D or other automated simulation flows.

## 12. Common Questions

### 12.1 Why did some geometry not end up in the expected semantic object?

Check these first:

1. does the component name follow the strict grammar?
2. does the `semantic_rules` regex actually match the `qgeometry.name`?
3. does the component have a local `semantic_map` overriding the rule?

### 12.2 Why does a route look like it tapers near a component pin?

Often this is not a renderer issue. It is usually a pin-definition issue.

For `QRoute`, lead generation depends on the pin's:

- `middle`
- `normal`

If the pin is placed too far inside the component rather than on the true connection boundary, route trace or subtract geometry can overlap the component interior and visually resemble a taper.

Recommended fix:

- place pins on the actual connection boundary
- make sure pin normals point in the intended route direction

### 12.3 Should the renderer automatically tolerate malformed names?

Usually no.

Loose tolerance tends to hide real naming problems and makes semantic reconstruction less reliable.

## 13. Recommended Workflow

The cleanest workflow is:

1. make component names follow the grammar
2. inspect geometry names with `inspect_component_geometry()`
3. define broad `semantic_rules`
4. add `semantic_map` only for exceptions
5. validate with `debug_print_final_hierarchy()`
6. export the GDS

## 14. Summary

This renderer is especially useful for:

- multi-chip superconducting layouts
- semantic grouping of feedlines, resonators, qubits, and couplers
- GDS exports that feed later HFSS / Q3D automation

Its core design principle is:

- geometry generation remains the job of QComponents
- the renderer performs deterministic semantic reconstruction
- topology and connectivity should not be guessed at GDS export time
