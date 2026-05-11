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


class FCLumpPortInline(QComponent):
    """Create an inline lumped port component with CPW connections on both sides.

    Inherits QComponent class.

    Lumped Port & Extension Geometry:
        * cpw_center_width - Width of the port's center trace at the top pin.
        * cpw_gap - Constant gap width surrounding the entire structure.
        * port_length - Length of the initial lumped port trapezoid.
        * cpw_ext_width - Width of the CPW trace at the bottom pin.
        * cpw_ext_length - Length of the second trapezoid (CPW extension).
        * carve_out_extend_size - Buffer distance for the clearance cavity on the opposing chip.

    Pins:
        * 'pin1' connects at the top of the port (y = 0).
        * 'pin2' connects at the bottom of the CPW extension (y = -(port_length + cpw_ext_length)).

    Default Options:
        * pos_x: '0um'
        * pos_y: '0um'
        * cpw_center_width: '10um'
        * cpw_gap: '6um'
        * port_length: '10um'
        * cpw_ext_width: '10um'
        * cpw_ext_length: '20um'
        * orientation: '0'
        * chip: 'main'
        * carve_out_chip: 'Q_chip'
        * carve_out_extend_size: '10um'
        * layer: 1291
    """

    default_options = Dict(
        pos_x='0um',
        pos_y='0um',
        cpw_center_width='10um',
        cpw_gap='6um',
        port_length='10um',
        # New parameters for the second trapezoid (CPW connection)
        cpw_ext_width='10um',
        cpw_ext_gap='6um',
        cpw_ext_length='20um',
        orientation='0',
        chip='main',
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',
        lump_port_layer=1291,
        cpw_layer=1
    )

    TOOLTIP = """Create an inline flip-chip lumped port with CPW extensions."""

    def make(self):
        p = self.p

        # === parse values ===
        x = self.parse_value(p.pos_x)
        y = self.parse_value(p.pos_y)

        w_top = self.parse_value(p.cpw_center_width)
        w_bot = w_top + self.parse_value('2nm')  # Mesher tolerance trick
        h = self.parse_value(p.port_length)
        w_gap = self.parse_value(p.cpw_gap)

        # CPW extension parameters
        w_cpw = self.parse_value(p.cpw_ext_width)
        cpw_gap = self.parse_value(p.cpw_ext_gap)
        h_cpw = self.parse_value(p.cpw_ext_length)

        angle = self.parse_value(p.orientation)

        # === Trace Polygon ===
        lump_port_trace_pts = [
            ( w_top/2,  0),                   # Top Right
            ( w_bot/2, -h),                   # Mid Right
            (-w_bot/2, -h),                   # Mid Left
            (-w_top/2,  0)                    # Top Left
        ]
        lump_port_trace_poly = draw.Polygon(lump_port_trace_pts)
        cpw_trace_pts = [
            ( w_bot/2, -h),                   # Mid Right
            ( w_cpw/2, -(h + h_cpw)),         # Bottom Right
            (-w_cpw/2, -(h + h_cpw)),         # Bottom Left
            (-w_bot/2, -h),                   # Mid Left
        ]
        cpw_trace_poly = draw.Polygon(cpw_trace_pts)
        # === Gap Polygon ===
        # Conformal gap that maintains w_gap distance everywhere
        lump_port_gap_pts = [
            ( w_top/2 + w_gap,  0),           # Top Right
            ( w_bot/2 + w_gap, -h),           # Mid Right
            (-w_bot/2 - w_gap, -h),           # Mid Left
            (-w_top/2 - w_gap,  0)            # Top Left
        ]
        lump_port_gap_poly = draw.Polygon(lump_port_gap_pts)
        cpw_gap_pts = [
            ( w_bot/2 + w_gap, -h),           # Mid Right
            ( w_cpw/2 + cpw_gap, -(h + h_cpw)), # Bottom Right
            (-(w_cpw/2 + cpw_gap), -(h + h_cpw)), # Bottom Left
            (-(w_bot/2 + w_gap), -h)           # Mid Left
        ]
        cpw_gap_poly = draw.Polygon(cpw_gap_pts)

        # Apply transforms: rotate then translate
        lump_port_trace_poly = draw.translate(draw.rotate(lump_port_trace_poly, angle, origin=(0, 0)), x, y)
        cpw_trace_poly = draw.translate(draw.rotate(cpw_trace_poly, angle, origin=(0, 0)), x, y)
        lump_port_gap_poly = draw.translate(draw.rotate(lump_port_gap_poly, angle, origin=(0, 0)), x, y)
        cpw_gap_poly = draw.translate(draw.rotate(cpw_gap_poly, angle, origin=(0, 0)), x, y)

        # === add geometry ===
        self.add_qgeometry('poly', dict(trace=lump_port_trace_poly), layer=p.lump_port_layer)
        self.add_qgeometry('poly', dict(gap=lump_port_gap_poly), layer=p.lump_port_layer, subtract=True)
        self.add_qgeometry('poly', dict(trace=cpw_trace_poly), layer=p.cpw_layer)
        self.add_qgeometry('poly', dict(gap=cpw_gap_poly), layer=p.cpw_layer, subtract=True)
        # === carve out (flip chip) ===
        do_carve_out = bool(p.carve_out_chip and str(p.carve_out_chip).lower() != 'none')

        if do_carve_out:
            carve_port = lump_port_gap_poly.buffer(self.parse_value(p.carve_out_extend_size))
            self.add_qgeometry(
                'poly',
                dict(carve_out_port=carve_port),
                layer=p.lump_port_layer,
                chip=p.carve_out_chip,
                subtract=True
            )
            carve_cpw = cpw_gap_poly.buffer(self.parse_value(p.carve_out_extend_size))
            self.add_qgeometry(
                'poly',
                dict(carve_out_cpw=carve_cpw),
                layer=p.cpw_layer,
                chip=p.carve_out_chip,
                subtract=True
            )

        # === pin definitions ===
        # Top pin at y=0. Drawn Right-to-Left so normal points UP (outward)
        pin1_line = draw.LineString([
            [-w_top/2, 0],
            [ w_top/2, 0]
        ])

        # Bottom pin at y=-(h+h_cpw). Drawn Left-to-Right so normal points DOWN (outward)
        pin2_line = draw.LineString([
            [ w_cpw/2, -(h + h_cpw)],
            [-w_cpw/2, -(h + h_cpw)]
        ])

        # Apply transforms to pins
        pin1_line = draw.translate(draw.rotate(pin1_line, angle, origin=(0, 0)), x, y)
        pin2_line = draw.translate(draw.rotate(pin2_line, angle, origin=(0, 0)), x, y)

        # Convert back to numpy arrays for add_pin
        self.add_pin('narrow_edge', points=np.array(pin1_line.coords), width=w_top)
        self.add_pin('wide_edge', points=np.array(pin2_line.coords), width=w_cpw)