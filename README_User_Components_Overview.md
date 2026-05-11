# Overview of `qlibrary/user_components`

This document gives a practical overview of what the current

`src/qiskit_metal/qlibrary/user_components/`

folder is doing inside this fork.

At a high level, this folder is the local extension library for flip-chip work. It contains:

- lightweight adapters that turn stock Qiskit Metal components into FC-aware versions
- fully custom FC-native primitives with explicit layer mapping
- ports, transitions, and helper geometry used in FC layouts
- a small set of utilities, templates, and experimental components

## 1. Main Structure

The folder is easiest to understand as three groups.

### Group A: `fc_usercomponents/`

This subfolder contains thin wrapper versions of existing Qiskit Metal components.

These files do not usually rewrite the original geometry logic. Instead, they:

- import the upstream component
- inherit from `FlipChipCarveOutMixin` or `FlipChipRouteMixin`
- add FC default options
- automatically create opposite-chip carve-out geometry

Representative examples:

- `transmon_pocket.py`
- `transmon_cross.py`
- `line_tee.py`
- `coupled_line_tee.py`
- `meandered.py`
- `straight_path.py`
- `pathfinder.py`

This is the recommended path when you want an FC version of a stock planar component without redesigning the component from scratch.

### Group B: root-level `FC_*.py` files

These are custom FC-native components.

They are typically used when the mixin approach is not enough and the component needs:

- explicit flip-chip layer mapping
- separate signal / subtract / carve-out handling
- FC-specific geometry naming
- custom ports or layout behavior

Important examples:

- `FC_qubit_pocket.py`
  A generic FC qubit pocket primitive with dedicated pad, antenna, subtract, and carve-out handling.

- `FC_line_tee.py`
  A flip-chip tee / hanger-style coupler with explicit carve-out generation.

- `FC_coupled_line_tee.py`
  An FC version of a coupled tee structure with direct geometry control.

- `FC_cap_n_interdigital.py`
- `FC_cap_n_interdigital_tee.py`
- `FC_round_cap_n_interdigital.py`
- `FC_round_cap_n_interdigital_tee.py`
- `FC_round_tee.py`
  FC coupler and capacitor primitives, including rounded variants.

- `FC_tunable_coupler_01.py`
- `FC_tunable_coupler_02.py`
  Flip-chip tunable coupler implementations.

- `FC_Fluxonium.py`
  A custom FC-oriented qubit implementation.

- `FC_lump_port.py`
- `FC_lump_port_inline.py`
  Lumped port helpers for simulation setups.

- `FC_transition_piece.py`
  A transition / taper helper for FC CPW connections.

### Group C: utility, template, and auxiliary files

These files support development, experiments, or special devices rather than serving as the main FC wrapper path.

Examples:

- `BridgeFreeJJ.py`
  Bridge-free Josephson junction geometry.

- `fillet_q.py`
  Filleted qubit geometry.

- `self_define.py`
  Small reusable geometry primitives such as `Cross`, `Fillet_vertex`, and `Rect_fillet`.

- `my_qcomponent.py`
  A minimal template for building new components.

- `round_tee.py`
- `round_cap_n_interdigital_tee.py`
- `FC_RouteMeander.py`
  Alternate or earlier-style implementations that are still useful as references when authoring new FC components.

## 2. What the Folder Does Functionally

From a workflow point of view, this folder provides four main capabilities.

### Capability 1: turn planar components into FC-aware components

The `fc_usercomponents/` wrappers take existing upstream Qiskit Metal components and add:

- `chip`
- `carve_out_chip`
- `carve_out_extend_size`
- optional carve-out layer behavior

This makes standard planar components usable in a two-chip or FC-oriented layout flow with minimal code duplication.

### Capability 2: provide FC-native primitives where wrappers are not enough

Some FC structures need more control than a wrapper can provide. The root-level `FC_*.py` files cover those cases by directly controlling:

- source-chip metal
- subtract geometry
- opposite-chip carve-out
- explicit layer mapping
- geometry names expected by the FC renderer

### Capability 3: support simulation-oriented layout pieces

Several files exist specifically to help downstream EM or GDS workflows, for example:

- lumped ports
- inline ports
- transition pieces
- tunable couplers
- bridge-free junction structures

These are especially useful when the layout is intended for semantic GDS export or EM model generation.

### Capability 4: provide a local sandbox for geometry development

Some files in this folder are clearly useful as templates or geometry references for future work.

This includes:

- trying new fillet logic
- prototyping new FC primitives
- testing custom geometry naming
- keeping local design helpers outside the upstream core library

## 3. Recommended Interpretation of the Folder

In practice, it is helpful to think of this folder as:

- a local FC adaptation layer for stock library components
- a home for FC-specific primitives that do not belong upstream unchanged
- a development area for new component ideas tied to your flip-chip workflow

## 4. Recommended Usage Going Forward

For future maintenance, the cleanest convention is:

- use `fc_usercomponents/` when adapting an upstream planar component
- use a root-level `FC_*.py` file when building a genuinely new FC-native component
- keep geometry naming stable if the component will be exported by `design.renderers.FCgds`
- use `my_qcomponent.py` or an existing FC component as the starting template for new work

## 5. Relationship to the FC GDS Renderer

This folder is closely tied to:

- `src/qiskit_metal/renderers/renderer_gds/FlipChip_gds_renderer.py`

That renderer relies on:

- stable class names
- stable `qgeometry.name` values
- consistent chip/layer placement

So the components in `user_components/` are not just layout generators. They are also the source objects that feed the repository's flip-chip-aware GDS export pipeline.
