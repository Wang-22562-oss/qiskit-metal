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

from qiskit_metal import draw
from qiskit_metal.toolbox_python.attr_dict import Dict
from qiskit_metal.qlibrary.core import QComponent
import numpy as np

class FCTransitionPiece(QComponent):
    """Create a linear CPW transition (taper) piece with optional cross-chip carve-out.

    Inherits QComponent class.

    This creates a trapezoidal center trace and a conformal trapezoidal ground gap.
    It is drawn linearly from left (x=0) to right (x=length) before any rotations.

    Geometry Parameters:
        * trace_width_start - Width of the trace at pin1.
        * trace_width_end - Width of the trace at pin2.
        * gap_width_start - Width of the ground gap at pin1.
        * gap_width_end - Width of the ground gap at pin2.
        * length - Total length of the transition piece.
        * carve_out_extend_size - Buffer distance for the clearance cavity on the opposing chip.

    Pins:
        * 'pin1' is located at the start (x=0) and faces outward (left).
        * 'pin2' is located at the end (x=length) and faces outward (right).

    Default Options:
        * pos_x: '0um'
        * pos_y: '0um'
        * orientation: '0'
        * trace_width_start: '10um'
        * gap_width_start: '6um'
        * trace_width_end: '20um'
        * gap_width_end: '12um'
        * length: '50um'
        * chip: 'main'
        * carve_out_chip: 'Q_chip'
        * carve_out_extend_size: '10um'
        * layer: 1
    """

    default_options = Dict(
        pos_x='0um',
        pos_y='0um',
        orientation='0',
        trace_width_start='10um',
        gap_width_start='6um',
        trace_width_end='20um',
        gap_width_end='12um',
        length='50um',
        chip='main',
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',
        layer=1
    )

    TOOLTIP = """Create a linear CPW taper transition piece with ground carve-out."""

    def make(self):
        p = self.p

        # === parse values ===
        x = self.parse_value(p.pos_x)
        y = self.parse_value(p.pos_y)
        angle = self.parse_value(p.orientation)

        w_start = self.parse_value(p.trace_width_start)
        w_end = self.parse_value(p.trace_width_end)
        g_start = self.parse_value(p.gap_width_start)
        g_end = self.parse_value(p.gap_width_end)
        length = self.parse_value(p.length)

        # === Trace Polygon ===
        # Drawn from x=0 to x=length, centered on y=0
        trace_pts = [
            (0,       w_start/2),
            (length,  w_end/2),
            (length, -w_end/2),
            (0,      -w_start/2)
        ]
        trace_poly = draw.Polygon(trace_pts)

        # === Gap Polygon ===
        # Conformal gap surrounding the trace
        gap_pts = [
            (0,       w_start/2 + g_start),
            (length,  w_end/2 + g_end),
            (length, -(w_end/2 + g_end)),
            (0,      -(w_start/2 + g_start))
        ]
        gap_poly = draw.Polygon(gap_pts)

        # === Apply Transforms ===
        # Rotate around the origin (pin1), then translate to (pos_x, pos_y)
        trace_poly = draw.translate(draw.rotate(trace_poly, angle, origin=(0, 0)), x, y)
        gap_poly = draw.translate(draw.rotate(gap_poly, angle, origin=(0, 0)), x, y)

        # === Add Geometry ===
        self.add_qgeometry('poly', dict(trace=trace_poly), layer=p.layer)
        self.add_qgeometry('poly', dict(gap=gap_poly), layer=p.layer, subtract=True)

        # === Carve out (flip chip) ===
        do_carve_out = bool(p.carve_out_chip and str(p.carve_out_chip).lower() != 'none')

        if do_carve_out:
            carve = gap_poly.buffer(self.parse_value(p.carve_out_extend_size))
            self.add_qgeometry(
                'poly',
                dict(carve_out=carve),
                layer=p.layer,
                chip=p.carve_out_chip,
                subtract=True
            )

        # === Pin Definitions ===
        # Pin 1 at x=0. Drawn Bottom-to-Top so outward normal points LEFT
        pin1_line = draw.LineString([
            [0, -w_start/2],
            [0,  w_start/2]
        ])

        # Pin 2 at x=length. Drawn Top-to-Bottom so outward normal points RIGHT
        pin2_line = draw.LineString([
            [length,  w_end/2],
            [length, -w_end/2]
        ])

        # Apply transforms to pins
        pin1_line = draw.translate(draw.rotate(pin1_line, angle, origin=(0, 0)), x, y)
        pin2_line = draw.translate(draw.rotate(pin2_line, angle, origin=(0, 0)), x, y)

        # Convert to numpy arrays and add pins
        self.add_pin('pin1', points=np.array(pin1_line.coords), width=w_start)
        self.add_pin('pin2', points=np.array(pin2_line.coords), width=w_end)