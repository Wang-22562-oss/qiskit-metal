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
"""Qubit with pads of fillet vertices and tappered arms.

.. code-block::
     ________________________________
    (                                )
    (                                )
    |        __________________      |
    |       (                  )     |
    |       (__________________)     |
    |                 |              |
    |                 x              |
    |        _________|________      |
    |       (                  )     |
    |       (__________________)     |
    |                                |
    (                                )
    (________________________________)
"""

import numpy as np
from qiskit_metal import draw, Dict
from qiskit_metal.qlibrary.core import BaseQubit


class FCFluxonium(BaseQubit):
    """The base `Fillet_Qubit` class.

    Inherits `BaseQubit` class.

    Create a pocket for a ground plane, 
    with two pads with fillet vertices and tappered arms connected by Josephson junctions. 

    Connector lines can be added using the `connection_pads`
    dictionary. Each connector pad has a name and a list of default
    properties.

    Sketch:
        Below is a sketch of the qubit
        ::

                 +1                            +1
                ________________________________
            -1  |______ ____           __________|   +1      Y
                |      |____|         |____|     |           ^
                |        __________________      |           |
                |       |     island       |     |           |----->  X
                |       |__________________|     |
                |                 |              |
                |  pocket         x              |
                |        _________|________      |
                |       |                  |     |
                |       |__________________|     |
                |        ______                  |
                |_______|______|                 |
            -1  |________________________________|   +1
                 
                 -1                            -1

    .. image::
        Fillet_Qubit.png

    .. meta::
        Fillet Qubit

    BaseQubit Default Options:
        * connection_pads: Empty Dict -- The dictionary which contains all active connection lines for the qubit.
        * _default_connection_pads: Empty Dict -- The default values for the (if any) connection lines of the qubit.

    Default Options:
        * arm_width: '8um' -- 
        * arm_length: '50um' -- 
        * arm_fillet: '25um' --
        * pad_gap: '30um' -- The distance between the two charge islands, which is also the resulting 'length' of the pseudo junction
        * pad_width: '150um' -- The width (x-axis) of the charge island pads
        * pad_height: '150um' -- The size (y-axis) of the charge island pads
        * pad_fillet: '20um' -- 
        * pocket_width: '400um' -- Size of the pocket (cut out in ground) along x-axis
        * pocket_height: '600um' -- Size of the pocket (cut out in ground) along y-axis
        * pocket_fillet: '100um' -- 
        * chip: 'C_chip' -- The chip on which the qubit is drawn. 
        * carve_out_chip: 'Q_chip' -- The chip on which the pocket cutout is drawn. Set to None or empty string to disable.
        * carve_out_extend_size: '10um' -- The amount by which the pocket cutout extends beyond the qubit geometry, to ensure a clean cut in fabrication.
    """

    default_options = Dict(
        arm_width='8um', arm_length='50um', arm_fillet='25um',
        pad_gap='30um', pad_width='150um', pad_height='150um', pad_fillet='20um',
        pocket_width='400um', pocket_height='600um', pocket_fillet='100um',
        # 90 has dipole aligned along the +X axis,
        # while 0 has dipole aligned along the +Y axis
        chip='C_chip',
        carve_out_chip='Q_chip',
        carve_out_extend_size='10um',
        pad_sig_layer=5,
        pad_gnd_layer=6,)
    """Default drawing options"""

    component_metadata = Dict(short_name='Pocket',
                              _qgeometry_table_path='True',
                              _qgeometry_table_poly='True',
                              _qgeometry_table_junction='True')
    """Component metadata"""

    TOOLTIP = """The user component `Fillet_Qubit` class."""

    def make(self):
        """Define the way the options are turned into QGeometry.

        The make function implements the logic that creates the geoemtry
        (poly, path, etc.) from the qcomponent.options dictionary of
        parameters, and the adds them to the design, using
        qcomponent.add_qgeometry(...), adding in extra needed
        information, such as layer, subtract, etc.
        """
        self.make_pocket()
        # self.make_connection_pads()

    def make_pocket(self):
        """Makes standard transmon in a pocket."""
        # self.p allows us to directly access parsed values
        p = self.p
        chip = p.chip
        
        # 1. Main Pad (Refactored using the buffer trick)
        p.pad_fillet = min(p.pad_fillet, (p.pad_width-2*p.arm_width)/2, (p.pad_height-p.arm_width)/2)
        
        # A negative buffer followed by a positive buffer rounds the convex (outer) corners perfectly
        main_pad = draw.rectangle(p.pad_width, p.pad_height).buffer(-p.pad_fillet).buffer(p.pad_fillet)
        
        # 2. Arm and Taper (Kept mostly original to preserve your specific concave inner fillet logic)
        arm_fillet = min((p.pad_width-2*p.pad_fillet-p.arm_width)/2, p.arm_length, p.arm_fillet)
        rect3 = draw.rectangle(p.arm_width+2*arm_fillet, arm_fillet)
        cir2 = draw.Point(0,0).buffer(arm_fillet)
        rect4 = draw.rectangle(p.arm_width, p.arm_length-arm_fillet)
        
        x, y = (p.arm_width+2*arm_fillet)/2, -arm_fillet/2
        arm_pad_connect = draw.subtract(rect3, draw.translate(cir2, x, y))
        arm_pad_connect = draw.subtract(arm_pad_connect, draw.translate(cir2,-x, y))
        
        pad_top = draw.union(
            draw.translate(main_pad, 0, p.arm_length+(p.pad_height+p.pad_gap)/2),
            draw.translate(arm_pad_connect, 0, p.arm_length+(p.pad_gap-arm_fillet)/2),
            draw.translate(rect4, 0, (p.arm_length-arm_fillet+p.pad_gap)/2)
        )
        pad_bot = draw.rotate(pad_top, 180, origin=(0,0))
        
        # 3. Josephson Junction
        rect_jj = draw.LineString([(0, -p.pad_gap / 2), (0, +p.pad_gap / 2)])
        
        # 4. Pocket (Refactored using the buffer trick)
        rect_pk = draw.rectangle(p.pocket_width, p.pocket_height).buffer(-p.pocket_fillet).buffer(p.pocket_fillet)

        # 5. Conditional Carve-out
        polys = [rect_jj, pad_top, pad_bot, rect_pk]
        
        # Check if carve_out_chip is defined and not set to a null string
        do_carve_out = bool(p.carve_out_chip and str(p.carve_out_chip).strip().lower() != 'none')
        
        if do_carve_out:
            # carvedout pocket with extra buffer to ensure clean cut in fabrication
            carve_out = draw.rectangle(p.pocket_width+2*p.carve_out_extend_size, 
                                       p.pocket_height+2*p.carve_out_extend_size).buffer(-p.pocket_fillet).buffer(p.pocket_fillet)
            polys.append(carve_out)

        # Rotate and translate all qgeometry as needed (now includes carve_out if it exists).
        polys = draw.rotate(polys, p.orientation, origin=(0, 0))
        polys = draw.translate(polys, p.pos_x, p.pos_y)
        
        if do_carve_out:
            [rect_jj, pad_top, pad_bot, rect_pk, carve_out] = polys
        else:
            [rect_jj, pad_top, pad_bot, rect_pk] = polys
        
        # Use the geometry to create Metal qgeometry
        self.add_qgeometry('poly', dict(pad_top=pad_top), layer=p.pad_sig_layer, chip=chip)
        self.add_qgeometry('poly', dict(pad_bot=pad_bot), layer=p.pad_gnd_layer, chip=chip)
        self.add_qgeometry('poly', dict(rect_pk=rect_pk), subtract=True, chip=chip)
        self.add_qgeometry('junction', dict(rect_jj=rect_jj), width=p.arm_width, chip=chip)
        
        # Add the carve out geometry only if the conditional check passed
        if do_carve_out:
            self.add_qgeometry('poly', dict(carve_out=carve_out), subtract=True, chip=p.carve_out_chip)