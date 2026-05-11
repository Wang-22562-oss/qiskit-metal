# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2017, 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
import numpy as np
from qiskit_metal import draw, Dict
from qiskit_metal.qlibrary.core.base import QComponent


class FCRoundTee(QComponent):
    """Rounded tee / antenna stub with CPW straight path.

    This version follows the same style as the res_antenna / res_straight
    implementation inside FCQubitPocket:

    - antenna pad is a rounded rectangle polygon
    - CPW center trace is a path
    - CPW ground gap is a wider subtract path
    - pin is added from the CPW path coordinates
    """

    component_metadata = Dict(
        short_name='RoundTee',
        _qgeometry_table_poly='True',
        _qgeometry_table_path='True'
    )

    default_options = Dict(
        # Reference component
        ref_qc=None,

        # Placement relative to reference component
        rel_ori='0',
        shift_x='100um',
        shift_y='100um',

        # CPW dimensions
        cpw_width='10um',
        cpw_gap='6um',
        ext_len='100um',

        # Tee antenna dimensions
        tee_width='50um',
        tee_length='150um',
        tee_fillet='10um',

        # Chip / layer
        chip='C_chip',
        layer=1,

        # Optional opposite-chip carve out
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',
        carve_out_layer=108,

        helper=False,
    )

    TOOLTIP = 'Rounded Tee antenna stub with CPW pin.'

    def make(self):
        p = self.p

        # --------------------------------------------------
        # Reference component handling
        # --------------------------------------------------

        Q = None

        if p.ref_qc is not None:
            if isinstance(p.ref_qc, str):
                Q = self.design.components[p.ref_qc].p
            else:
                Q = p.ref_qc.p

        if Q is not None:
            base_x = Q.pos_x
            base_y = Q.pos_y
            base_ori = float(Q.orientation)
        else:
            base_x = p.pos_x
            base_y = p.pos_y
            base_ori = p.orientation

        total_ori = base_ori + float(p.rel_ori)

        # --------------------------------------------------
        # Local geometry
        # --------------------------------------------------
        #
        # Local convention:
        #
        #   tee antenna pad centered at origin
        #   CPW straight starts at +X edge of tee pad
        #   CPW extends along local +X
        #
        #       tee_pad
        #    ┌─────────┐
        #    │         │────────── cpw_straight
        #    └─────────┘
        #

        radius = min(
            p.tee_fillet,
            p.tee_width / 2 - 1e-3,
            p.tee_length / 2 - 1e-3
        )

        # Tee metal pad
        tee_pad = draw.rectangle(
            p.tee_width,
            p.tee_length,
            0,
            0
        )

        tee_pad = (
            tee_pad
            .buffer(-radius, resolution=32)
            .buffer(radius, resolution=32)
        )

        # CPW center trace
        cpw_start_x = p.tee_width / 2
        cpw_end_x = p.tee_width / 2 + p.ext_len

        cpw_straight = draw.LineString([
            (cpw_start_x, 0),
            (cpw_end_x, 0)
        ])

        # Tee nofill / ground cutout
        nofill_radius = min(
            radius + p.cpw_gap,
            (p.tee_width + 2 * p.cpw_gap) / 2 - 1e-3,
            (p.tee_length + 2 * p.cpw_gap) / 2 - 1e-3
        )

        tee_nofill = draw.rectangle(
            p.tee_width + 2 * p.cpw_gap,
            p.tee_length + 2 * p.cpw_gap,
            0,
            0
        )

        tee_nofill = (
            tee_nofill
            .buffer(-nofill_radius, resolution=32)
            .buffer(nofill_radius, resolution=32)
        )

        # --------------------------------------------------
        # Optional carve-out
        # --------------------------------------------------

        do_carve_out = bool(
            p.carve_out_chip
            and str(p.carve_out_chip).strip().lower() != 'none'
        )

        if do_carve_out:
            cpw_sub_poly = cpw_straight.buffer(
                (p.cpw_width + 2 * p.cpw_gap) / 2,
                cap_style=2
            )

            carve_out = draw.union([
                tee_nofill,
                cpw_sub_poly
            ])

            carve_out = carve_out.buffer(
                p.carve_out_extend_size,
                resolution=32
            )

        # --------------------------------------------------
        # Rotate and translate
        # --------------------------------------------------

        c_items = [
            tee_pad,
            cpw_straight,
            tee_nofill
        ]

        if do_carve_out:
            c_items.append(carve_out)

        c_items = draw.rotate(
            c_items,
            total_ori,
            origin=(0, 0)
        )

        c_items = draw.translate(
            c_items,
            base_x + p.shift_x,
            base_y + p.shift_y
        )

        if do_carve_out:
            tee_pad, cpw_straight, tee_nofill, carve_out = c_items
        else:
            tee_pad, cpw_straight, tee_nofill = c_items

        # --------------------------------------------------
        # Add QGeometry
        # --------------------------------------------------

        # Metal tee pad
        self.add_qgeometry(
            'poly',
            {'tee_pad': tee_pad},
            layer=p.layer,
            chip=p.chip,
            helper=p.helper
        )

        # Metal CPW path
        self.add_qgeometry(
            'path',
            {'cpw_straight': cpw_straight},
            width=p.cpw_width,
            layer=p.layer,
            chip=p.chip,
            helper=p.helper
        )

        # Tee ground cutout
        self.add_qgeometry(
            'poly',
            {'tee_nofill': tee_nofill},
            subtract=True,
            layer=p.layer,
            chip=p.chip,
            helper=p.helper
        )

        # CPW ground cutout
        self.add_qgeometry(
            'path',
            {'cpw_straight_sub': cpw_straight},
            width=p.cpw_width + 2 * p.cpw_gap,
            subtract=True,
            layer=p.layer,
            chip=p.chip,
            helper=p.helper
        )

        # Opposite-chip carve out
        if do_carve_out:
            self.add_qgeometry(
                'poly',
                {'carve_out': carve_out},
                subtract=True,
                chip=p.carve_out_chip,
                layer=p.carve_out_layer,
                helper=True
            )

        # --------------------------------------------------
        # Add CPW pin
        # --------------------------------------------------

        self.add_pin(
            'cpw',
            points=np.array(cpw_straight.coords),
            width=p.cpw_width,
            input_as_norm=True
        )