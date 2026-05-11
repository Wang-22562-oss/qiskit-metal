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


class FCLumpPort(QComponent):
    """Create a lumped port component specifically designed for flip-chip architectures.

    Inherits QComponent class.

    Lumped Port Geometry and Flip-Chip Carve Out:
        * cpw_center_width - Width of the port's center trace.
        * cpw_gap - Width of the gap between the center trace and ground.
        * port_length - Overall length of the port geometry.
        * carve_out_extend_size - Buffer distance for the clearance cavity on the opposing chip.
          This pocket is a negative shape that is cut out of the target flip-chip ground plane.

    Pins:
        There are two pins on the lumped port:
        * 'gnd_end' connects at the top of the port.
        * 'cpw_port' connects at the bottom of the port to interface with a trace.

    Sketch:
        Below is a sketch of the component
        ::
        
            Pin 'gnd_end' (top, y=0)
            -------------------
            |                 |
            |      trace      |  (Ground Gap surrounding)
            |                 |
            -------------------
            Pin 'cpw_port' (bottom, y=-h)

    .. image::
        FCLumpPort.png

    .. meta::
        :description: Flip-Chip Lumped Port

    Default Options:
        * pos_x: '0um'
        * pos_y: '0um'
        * cpw_center_width: '10um'
        * cpw_gap: '6um'
        * port_length: '10um'
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

        orientation='0',

        chip='main',
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',

        layer=1291
    )
    """Default drawing options"""

    TOOLTIP = """Create a flip-chip lumped port with cross-chip ground carve-out."""

    def make(self):
        """This is executed by the user to generate the qgeometry for the
        component."""
        p = self.p

        # === parse values ===
        x = self.parse_value(p.pos_x)
        y = self.parse_value(p.pos_y)

        w_top = self.parse_value(p.cpw_center_width)
        w_bot = w_top + self.parse_value('2nm')  # Smart trick for mesher tolerance
        h = self.parse_value(p.port_length)
        w_gap = self.parse_value(p.cpw_gap)

        angle = self.parse_value(p.orientation)

        # === trapezoid (Shifted down so top is at y=0) ===
        pts = [
            (-w_bot/2, -h),
            ( w_bot/2, -h),
            ( w_top/2,  0),
            (-w_top/2,  0)
        ]

        trap = draw.Polygon(pts)
        trap = draw.rotate(trap, angle, origin=(0, 0))
        trap = draw.translate(trap, x, y)
        
        # === ground cut / gap (Shifted down by h/2) ===
        rect = draw.rectangle(
            w_top + 2*w_gap,
            h,
            0, -h/2  
        )
        rect = draw.rotate(rect, angle, origin=(0, 0))
        rect = draw.translate(rect, x, y)

        # === add geometry ===
        self.add_qgeometry('poly', dict(trap=trap), layer=p.layer)
        self.add_qgeometry('poly', dict(gap=rect), layer=p.layer, subtract=True)

        # === carve out (flip chip) ===
        do_carve_out = bool(p.carve_out_chip and str(p.carve_out_chip).lower() != 'none')

        if do_carve_out:
            carve = rect.buffer(self.parse_value(p.carve_out_extend_size))
            self.add_qgeometry(
                'poly',
                dict(carve_out=carve),
                layer=p.layer,
                chip=p.carve_out_chip,
                subtract=True
            )

        # === pin definitions ===
        # Top pin at y=0. Drawn Right-to-Left so normal points UP (outward)
        pin_top_line = draw.LineString([
            [ -w_top/2, 0],
            [ w_top/2, 0]
        ])

        # Bottom pin at y=-h. Drawn Left-to-Right so normal points DOWN (outward)
        pin_bot_line = draw.LineString([
            [ w_bot/2, -h],
            [-w_bot/2, -h]
        ])

        # Apply transforms: rotate then translate
        pin_top_line = draw.translate(draw.rotate(pin_top_line, angle, origin=(0, 0)), x, y)
        pin_bot_line = draw.translate(draw.rotate(pin_bot_line, angle, origin=(0, 0)), x, y)

        # Convert back to numpy arrays for add_pin
        pin_top = np.array(pin_top_line.coords)
        pin_bot = np.array(pin_bot_line.coords)

        # Generates its own pins
        self.add_pin('narrow_edge', points=pin_top, width=w_top)
        self.add_pin('wide_edge', points=pin_bot, width=w_bot)