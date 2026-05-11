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
"""Tee-shaped coupler with fillet for Q components. 
"""
# -*- coding: utf-8 -*-

import numpy as np
from qiskit_metal import draw, Dict
from qiskit_metal.qlibrary.core.base import QComponent


class FCRoundTee(QComponent):

    default_options = Dict(
        ref_qc=None,
        rel_ori="0",
        shift_x="100um",
        shift_y="100um",

        cpw_width="10um",
        cpw_gap="6um",
        ext_len="100um",

        tee_width="5um",
        tee_length="20um",
        tee_fillet="10um",

        chip="C_chip",
        layer=1,

        carve_out_chip="Q_chip",
        carve_out_extend_size="10um",

        helper=False,
    )

    TOOLTIP = "Rounded Tee coupler with CPW pin."

    def make(self):
        p = self.p

        # Gap / subtract geometry
        self.make_round_tee(
            p.cpw_width + 2 * p.cpw_gap,
            p.tee_fillet,
            p.tee_width + 2 * p.cpw_gap,
            subtract=True
        )

        # Metal geometry
        self.make_round_tee(
            p.cpw_width,
            p.tee_fillet,
            p.tee_width,
            subtract=False
        )

    def _get_ref_options(self):
        p = self.p

        if p.ref_qc is None:
            return None

        # ref_qc = "component_name"
        if isinstance(p.ref_qc, str):
            return self.design.components[p.ref_qc].p

        # ref_qc = component object
        return p.ref_qc.p

    def make_round_tee(self, cpw_width, fillet, tee_width, subtract=False):
        p = self.p
        Q = self._get_ref_options()

        if Q is not None:
            base_x = Q.pos_x
            base_y = Q.pos_y
            base_ori = float(Q.orientation)
        else:
            base_x = 0
            base_y = 0
            base_ori = 0

        total_ori = base_ori + float(p.rel_ori)

        # Safety limit for fillet
        fillet = min(
            fillet,
            tee_width / 2 - 1e-3,
            cpw_width / 2 - 1e-3
        )

        # --------------------------------------------------
        # Original-style geometry
        # --------------------------------------------------

        # Main vertical tee pad
        rect_1 = draw.rectangle(
            tee_width,
            p.tee_length
        )

        # Small rectangle used to connect / prepare inner fillet
        rect_2 = draw.rectangle(
            fillet,
            cpw_width + 2 * fillet
        )

        # CPW extension arm
        rect_3 = draw.rectangle(
            p.ext_len,
            cpw_width
        )

        # Round ends of tee pad
        cir_1 = draw.Point(0, 0).buffer(
            tee_width / 2,
            resolution=32
        )

        # Inner concave fillet cutters
        cir_2 = draw.Point(0, 0).buffer(
            fillet,
            resolution=32
        )

        tee = draw.union(
            rect_1,
            draw.translate(rect_2, (tee_width + fillet) / 2, 0),
            draw.translate(rect_3, (tee_width + p.ext_len) / 2, 0),
            draw.translate(cir_1, 0,  p.tee_length / 2),
            draw.translate(cir_1, 0, -p.tee_length / 2),
        )

        tee = draw.subtract(
            tee,
            draw.union(
                draw.translate(
                    cir_2,
                    tee_width / 2 + fillet,
                    cpw_width / 2 + fillet
                ),
                draw.translate(
                    cir_2,
                    tee_width / 2 + fillet,
                    -cpw_width / 2 - fillet
                ),
            )
        )

        # --------------------------------------------------
        # Rotate and translate
        # --------------------------------------------------

        tee = draw.rotate(
            tee,
            total_ori,
            origin=(0, 0)
        )

        tee = draw.translate(
            tee,
            base_x + p.shift_x,
            base_y + p.shift_y
        )

        self.add_qgeometry(
            "poly",
            {f"tee_{'gap' if subtract else 'metal'}": tee},
            chip=p.chip,
            layer=p.layer,
            subtract=subtract,
            helper=p.helper
        )

        # --------------------------------------------------
        # Add CPW pin only for metal
        # --------------------------------------------------

        if not subtract:
            pin_x = tee_width + p.ext_len

            pin_pts = np.array([
                [pin_x, -cpw_width / 2],
                [pin_x,  cpw_width / 2],
            ])

            theta = np.deg2rad(total_ori)

            rot = np.array([
                [np.cos(theta), -np.sin(theta)],
                [np.sin(theta),  np.cos(theta)]
            ])

            pin_pts = pin_pts @ rot.T

            pin_pts[:, 0] += base_x + p.shift_x
            pin_pts[:, 1] += base_y + p.shift_y

            self.add_pin(
                "cpw",
                pin_pts,
                cpw_width
            )

        # --------------------------------------------------
        # Optional carve-out on another chip
        # --------------------------------------------------

        do_carve_out = (
            p.carve_out_chip
            and str(p.carve_out_chip).strip().lower() != "none"
        )

        if do_carve_out:
            carve_out = tee.buffer(
                p.carve_out_extend_size,
                resolution=32
            )

            self.add_qgeometry(
                "poly",
                {"carve_out": carve_out},
                subtract=True,
                helper=True,
                chip=p.carve_out_chip,
                layer=p.layer
            )