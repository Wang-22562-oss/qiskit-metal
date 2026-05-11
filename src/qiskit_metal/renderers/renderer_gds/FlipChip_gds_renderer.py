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
"""This module has a QRenderer to export QDesign to a GDS file."""
# pylint: disable=too-many-lines

import math
import os
import re
import json
from collections import defaultdict
from copy import deepcopy
from operator import itemgetter
from pprint import pprint
from typing import TYPE_CHECKING, Optional, Tuple, Union
from typing import Dict as DictType

import gdstk
import geopandas
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import distance
from shapely.geometry import LineString

from qiskit_metal import Dict, config, draw
from qiskit_metal.renderers.renderer_base import QRenderer
from qiskit_metal.renderers.renderer_gds.make_cheese import Cheesing
from qiskit_metal.toolbox_metal.parsing import is_true

if not config.is_building_docs():
    from qiskit_metal.toolbox_python.utility_functions import (
        can_write_to_path,
        get_range_of_vertex_to_not_fillet,
    )

if TYPE_CHECKING:
    # For linting typechecking, import modules that can't be loaded here under normal conditions.
    # For example, I can't import QDesign, because it requires QRenderer first. We have the
    # chicken and egg issue.
    from qiskit_metal.designs import QDesign


class MyGDSRenderer(QRenderer):
    """Extends QRenderer to export GDS formatted files. The methods which a
    user will need for GDS export should be found within this class.

    All chips within design should be exported to one gds file.
    For the "subtraction box":
    1. If user wants to export the entire design, AND if the base class of
    QDesign._chips[chip_name]['size'] has dict following below example:
    {'center_x': 0.0, 'center_y': 0.0, 'size_x': 9, 'size_y': 6}
    then this box will be used for every layer within a chip.

    2. If user wants to export entire design, BUT there is no information in
    QDesign._chips[chip_name]['size'], then the renderer will calculate the
    size of all of the components and use that size for the "subtraction box"
    for every layer within a chip.

    3. If user wants to export a list of explicit components, the bounding
    box will be calculated by size of QComponents in the QGeometry table.
    Then be scaled by bounding_box_scale_x and bounding_box_scale_y.

    4. Note: When using the Junction table, the cell for Junction should
    be "x-axis" aligned and then GDS rotates based on LineString given
    in Junction table.


    datatype:
        * 10 Polygon
        * 11 Flexpath

    Default Options:
        * short_segments_to_not_fillet: 'True'
        * check_short_segments_by_scaling_fillet: '2.0'
        * gds_unit: '1'
        * ground_plane: 'True'
        * packaging_dict=Dict()
        * negative_mask: Dict(main=[])
        * corners: 'natural'
        * tolerance: '0.00001'
        * precision: '0.000000001'
        * width_LineString: '10um'
        * path_filename: '../resources/Fake_Junctions.GDS'
        * junction_pad_overlap: '5um'
        * max_points: '199'
        * fabricate: 'False'
        * cheese: Dict
            * datatype: '100'
            * shape: '0'
            * cheese_0_x: '50um'
            * cheese_0_y: '50um'
            * cheese_1_radius: '100um'
            * delta_x='100um',
            * delta_y='100um',
            * edge_nocheese='200um',
            * view_in_file: Dict(main={1: True})
        * no_cheese: Dict
            * datatype: '99'
            * buffer: '25um'
            * cap_style: '2'
            * join_style: '2'
            * view_in_file: Dict(main={1: True})
        * bounding_box_scale_x: '1.2'
        * bounding_box_scale_y: '1.2'
    """

    # Default options, over-written by passing ``options` dict to
    # render_options.
    # Type: Dict[str, str]
    default_options = Dict(
        # Before converting LINESTRING to FlexPath for GDS, check for fillet
        # errors for LINESTRINGS in QGeometry in QGeometry due to short
        # segments.  If true, break up the LINESTRING so any segment which is
        # shorter than the scaled-fillet by "fillet_scale_factor" will be
        # separated so the short segment will not be fillet'ed.
        short_segments_to_not_fillet="True",
        check_short_segments_by_scaling_fillet="2.0",
        # DO NOT MODIFY `gds_unit`. Gets overwritten by ``set_units``.
        # gdstk unit is 1 meter.  gds_units appear to ONLY be used during
        # write_gds().  Note that gds_unit will be overwritten from the design
        # units, during init().
        # Moving to Gdstk, the default unit is 1 µm (10⁻⁶ m), but we overwrite this.
        # WARNING: this cannot be changed since it is only used during the
        # init once.
        gds_unit="1",  # 1m (one meter, if you want to set 1 um, set 1e-6)
        # Implement creating a ground plane which is scaled from largest
        # bounding box, then QGeometry which is marked as subtract will be
        # removed from ground_plane.  Then the balance of QGeometry will be
        # placed placed in same layer as ground_plane.
        ground_plane="True",
        # Reconstruct simulation objects from qgeometry metadata using
        # regex rules keyed by QComponent class name.
        semantic_rules=Dict(),
        # Map canonical simulation object types to project-specific
        # abbreviations used in exported GDS hierarchy names.
        naming_map=Dict(
            readout_resonator="RO",
            charge_line="CL",
            fluxonium_qubit="FQ",
            transmon_qubit="TQ",
            coupler="CPL",
            feedline="FL",
            purcell_filter="PF",
        ),
        # When true, export only the semantic chip/package hierarchy from TOP.
        semantic_hierarchy="True",
        # When true, semantic simulation-object cells are prefixed with chip
        # names to guarantee global uniqueness in multi-chip exports.
        semantic_cell_chip_prefix="True",
        # When true, chip container cells are named ``CHIP__<chip>``.
        # When false, they use the raw chip name directly.
        chip_container_prefix="True",
        # When true, package helper cells are named
        # ``<chip>__GROUND`` / ``<chip>__SUBSTRATE``.
        # When false and only one chip is exported, they become
        # ``GROUND`` / ``SUBSTRATE``.
        package_cell_chip_prefix="True",
        # When true, each simulation-object cell can optionally contain
        # per-component child cells instead of holding all geometry directly.
        semantic_component_subcells="False",
        # By default, export_to_gds() will create a positive_mask for every
        # chip and layer.  Within the Dict, there needs to be an entry for each
        # chip.  Each chip has a list of layers that should export as a
        # negative mask.  If layer number in list, the mask will be negative
        # for that layer.  If user wants to export to a negative_mask for all
        # layers, every layer_number MUST be in list.
        negative_mask=Dict(main=[]),
        # For the gds file, Show/Don't Show intermediate steps?
        # If false, show the intermediate steps in the exported gds file.
        # If true, show the geometries on either neg_datatype_fabricate or pos_datatype_fabricate.
        #   Example:  # denotes the layer number
        #           delete for negative mask: TOP_main_#_NoCheese_99, TOP_main_#_one_hole
        #           delete for positive mask: TOP_main_#_NoCheese_99, TOP_main_#_one_hole,
        #                                       ground_main_#
        fabricate="False",
        # corners: ("natural", "miter", "bevel", "round", "smooth", callable)
        # Type of joins. A callable must receive 6 arguments
        # (vertex and direction vector from both segments being joined,
        # the center and width of the path)
        # and return a list of vertices that make the join.
        # A list can be used to define the join for each parallel path.
        corners="natural",
        # tolerance > precision
        # Precision used for gds lib, boolean operations and FlexPath should
        # likely be kept the same.  They can be different, but increases odds
        # of weird artifacts or misalignment.  Some of this occurs regardless
        # (might be related to offset of a curve when done as a
        # boolean vs. rendered), but they are <<1nm, which isn't even picked
        # up by any fab equipment (so can be ignored).  Numerical errors start
        # to pop up if set precision too fine,
        # but 1nm seems to be the finest precision we use anyhow.
        # FOR NOW SPECIFY IN METERS.
        tolerance="0.00001",  # 10.0 um
        # With input from fab people, any of the weird artifacts
        # (like unwanted gaps) that are less than 1nm in size can be ignored.
        # They don't even show up in the fabricated masks.
        # So, the precision of e-9 (so 1 nm) should be good as a default.
        # FOR NOW SPECIFY IN METERS.
        precision="0.000000001",  # 1.0 nm
        # Since Qiskit Metal GUI, does not require a width for LineString, GDS,
        # will provide a default value.
        width_LineString="10um",
        # The file is expected to be in GDS format.  The cell will be placed
        # into gds Metal output without being edited. The name of the cell can
        # be placed as options for a component, i.e. placing within a qubit.
        # During export, the cell will NOT be edited, just imported.
        path_filename="../resources/Fake_Junctions.GDS",
        # For junction table, when cell from default_options.path_filename does
        # not fit into linestring, QGDSRender will create two pads and add to
        # junction to fill the location of lineString.  The junction_pad_overlap
        # is from the junction cell to the newly created pads.
        junction_pad_overlap="5um",
        # Vertex limit for FlexPath
        # max_points (integer) – If the number of points in the polygonal path
        # boundary is greater than max_points, it will be fractured in smaller
        # polygons with at most max_points each. If max_points is zero,
        # no fracture will occur. GDSII used 199 as the default because the historical
        # max value of vertices for a poly/path was 199 (fabrication equipment
        # restrictions).  The hard max limit that a GDSII file can
        # handle is 8191. Gdstk allows arbitary numbers as does most modern software.
        max_points="199",
        # Cheesing is denoted by each chip and layer.
        cheese=Dict(
            # Cheesing is NOT completed
            datatype="100",
            # Expect to mostly cheese a square, but allow for expansion.
            # 0 is rectangle, 1 is circle
            shape="0",
            # rectangle
            cheese_0_x="25um",
            cheese_0_y="25um",
            # circle
            cheese_1_radius="100um",
            # Identify which layers to view in gds output file, for each chip
            view_in_file=Dict(main={1: True}),
            # delta spacing between holes
            delta_x="100um",
            delta_y="100um",
            # Keep a buffer around the perimeter of chip, that will
            # not need cheesing.
            edge_nocheese="200um",
        ),
        # Think of this as a keep-out region for cheesing.
        no_cheese=Dict(
            # For every layer, if there is a ground plane, do cheesing and
            # place the output on the datatype number (sub-layer number)
            datatype="99",
            buffer="25um",
            # The styles of caps are specified by integer values:
            # 1 (round), 2 (flat), 3 (square).
            cap_style="2",
            # The styles of joins between offset segments are specified by
            # integer values:
            # 1 (round), 2 (mitre), and 3 (bevel).
            join_style="2",
            # Identify which layers to view in gds output file, for each chip
            view_in_file=Dict(main={1: True}),
        ),
        # (float): Scale box of components to render.
        # Should be greater than 1.0.  For benefit of the GUI, keep this the
        # last entry in the dict.  GUI shows a note regarding bound_box.
        bounding_box_scale_x="1.2",
        bounding_box_scale_y="1.2",
    )
    """Default options"""

    name = "gds"
    """Name"""

    _SEMANTIC_NAME_SEPARATOR = "__"
    _SEMANTIC_NAME_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

    # When additional columns are added to QGeometry,
    # this is the example to populate it.
    # e.g. element_extensions = dict(
    #         base=dict(color=str, klayer=int),
    #         path=dict(thickness=float, material=str, perfectE=bool),
    #         poly=dict(thickness=float, material=str), )
    # """element extensions dictionary from base class:
    #    element_extensions = dict() """

    # Add columns to junction table during MyGDSRenderer.load()
    # element_extensions  is now being populated as part of load().
    # Determined from element_table_data.

    # Dict structure MUST be same as  element_extensions!!!!!!
    # This dict will be used to update QDesign during init of renderer.
    # Keeping this as a cls dict so could be edited before renderer is
    # instantiated.  To update component.options junction table.

    element_table_data = dict(
        # Cell_name must exist in gds file with: path_filename
        junction=dict(cell_name="my_other_junction")
    )
    """Element table data"""

    def __init__(
        self,
        design: "QDesign",
        initiate=True,
        render_template: Optional[Dict] = None,
        render_options: Optional[Dict] = None,
    ):
        """Create a QRenderer for GDS interface: export and import.

        Args:
            design (QDesign): Use QGeometry within QDesign  to obtain elements
                            for GDS file.
            initiate (bool, optional): True to initiate the renderer.
                                        Defaults to True.
            render_template (Dict, optional): Typically used by GUI for
                                template options for GDS.  Defaults to None.
            render_options (Dict, optional): Used to override all options.
                                            Defaults to None.
        """

        super().__init__(
            design=design,
            initiate=initiate,
            render_template=render_template,
            render_options=render_options,
        )

        self.lib: Union[gdstk.Library, None] = None
        self.new_gds_library()

        self.dict_bounds: DictType[str, Dict] = Dict()

        # Updated each time export_to_gds() is called.
        self.chip_info: DictType[str, dict] = dict()
        self.semantic_cells: DictType[str, gdstk.Cell] = dict()
        self.semantic_cell_details: DictType[str, dict] = dict()
        self.semantic_metadata: DictType[str, list] = dict()
        self._plain_package_name_collision_warned = False
        self._semantic_name_collision_warnings = set()

        # check the scale
        self._check_bounding_box_scale()

        # if imported, hold the path to file name, otherwise None.
        self.imported_junction_gds: Union[str, None] = None  # track only once

        MyGDSRenderer.load()

    def _initiate_renderer(self):
        """Not used by the gds renderer at this time. Only returns True."""
        return True

    def _close_renderer(self):
        """Not used by the gds renderer at this time. Only returns True."""
        return True

    def render_design(self):
        """Export the design to GDS."""
        self.export_to_gds(file_name=self.design.name, highlight_qcomponents=[])

    def _check_bounding_box_scale(self):
        """Some error checking for bounding_box_scale_x and
        bounding_box_scale_y numbers."""
        bounding_box_scale_x = self.parse_value(self.options.bounding_box_scale_x)
        bounding_box_scale_y = self.parse_value(self.options.bounding_box_scale_y)

        if bounding_box_scale_x < 1:
            self.options["bounding_box_scale_x"] = (
                MyGDSRenderer.default_options.bounding_box_scale_x
            )
            self.logger.warning(
                "Expected float and number greater than or equal to"
                " 1.0 for bounding_box_scale_x. User"
                f"provided bounding_box_scale_x = {bounding_box_scale_x}"
                ", using default_options.bounding_box_scale_x."
            )

        if bounding_box_scale_y < 1:
            self.options["bounding_box_scale_y"] = (
                MyGDSRenderer.default_options.bounding_box_scale_y
            )
            self.logger.warning(
                "Expected float and number greater than or equal to 1.0 for "
                "bounding_box_scale_y.  User provided "
                f"bounding_box_scale_y = {bounding_box_scale_y}, "
                "using default_options.bounding_box_scale_y."
            )

    def _can_write_to_path(self, file: str) -> int:
        """Check if can write file.

        Args:
            file (str): Has the path and/or just the file name.

        Returns:
            int: 1 if access is allowed. Else returns 0, if access not given.
        """
        status, directory_name = can_write_to_path(file)  # pylint: disable=possibly-used-before-assignment
        if status:
            return 1

        self.logger.warning(
            "Not able to write to directory."
            f'File:"{file}" not written.'
            f' Checked directory:"{directory_name}".'
        )
        return 0

    def _update_units(self):
        """Update the options in the units.

        Warning: DOES NOT CHANGE THE CURRENT LIB
        """
        self.options["gds_unit"] = 1.0 / self.design.parse_value("1 meter")

    def _separate_subtract_shapes(
        self, chip_name: str, table_name: str, table: geopandas.GeoSeries
    ) -> None:
        """For each chip and table, separate them by subtract being either True
        or False. Names of chip and table should be same as the QGeometry
        tables.

        Args:
            chip_name (str): Name of "chip".  Example is "main".
            table_name (str): Name for "table".  Example is "poly", and "path".
            table (geopandas.GeoSeries): Table with similar qgeometries.
        """
        # pylint: disable=singleton-comparison
        subtract_true = table[table["subtract"] == True]

        subtract_false = table[table["subtract"] == False]

        setattr(self, f"{chip_name}_{table_name}_subtract_true", subtract_true)
        setattr(self, f"{chip_name}_{table_name}_subtract_false", subtract_false)

    @staticmethod
    def _get_bounds(
        gs_table: geopandas.GeoDataFrame,
    ) -> Tuple[float, float, float, float]:
        """Get the bounds for all of the elements in gs_table.

        Args:
            gs_table (geopandas.GeoDataFrame): A GeoPandas GeoDataFrame used to describe
                                        components in a design.

        Returns:
            Tuple[float, float, float, float]: The bounds of all of the
            elements in this table. [minx, miny, maxx, maxy]
        """
        if len(gs_table) == 0:
            return (0, 0, 0, 0)

        return gs_table.total_bounds

    @staticmethod
    def _inclusive_bound(all_bounds: list) -> tuple:
        """Given a list of tuples which describe corners of a box, i.e. (minx,
        miny, maxx, maxy). This method will find the box, which will include
        all boxes.  In another words, the smallest minx and miny; and the
        largest maxx and maxy.

        Args:
            all_bounds (list): List of bounds. Each tuple corresponds to a box.

        Returns:
            tuple: Describe a box which includes the area of each box
            in all_bounds.
        """

        # If given an empty list.
        if len(all_bounds) == 0:
            return (0.0, 0.0, 0.0, 0.0)

        inclusive_tuple = (
            min(all_bounds, key=itemgetter(0))[0],
            min(all_bounds, key=itemgetter(1))[1],
            max(all_bounds, key=itemgetter(2))[2],
            max(all_bounds, key=itemgetter(3))[3],
        )
        return inclusive_tuple

    @staticmethod
    def _midpoint_xy(
        x_1: float, y_1: float, x_2: float, y_2: float
    ) -> Tuple[float, float]:
        """Calculate the center of a line segment with endpoints (x1,y1) and
        (x2,y2).

        Args:
            x1 (float): x of endpoint (x1,y1)
            y1 (float): y of endpoint (x1,y1)
            x2 (float): x of endpoint (x2,y2)
            y2 (float): y of endpoint (x2,y2)

        Returns:
            Tuple[float, float]:
            1st float: x for midpoint
            2nd float: y for midpoint
        """
        midx = (x_1 + x_2) / 2
        midy = (y_1 + y_2) / 2

        return midx, midy

    def _scale_max_bounds(
        self, chip_name: str, all_bounds: list
    ) -> Tuple[tuple, tuple]:
        """Given the list of tuples to represent all of the bounds for path,
        poly, etc. This will return the scaled using self.bounding_box_scale_x
        and self.bounding_box_scale_y, and the max bounds of the tuples
        provided.

        Args:
            chip_name (str): Name of chip.
            all_bounds (list): Each tuple=(minx, miny, maxx, maxy) in list
                            represents bounding box for poly, path, etc.

        Returns:
            tuple[tuple, tuple]:
            first tuple: A scaled bounding box which includes all paths, polys, etc.;
            second tuple: A  bounding box which includes all paths, polys, etc.
        """
        # If given an empty list.
        if len(all_bounds) == 0:
            return (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)

        # Get an inclusive bounding box to contain all of the tuples provided.
        minx, miny, maxx, maxy = self._inclusive_bound(all_bounds)

        # Center of inclusive bounding box
        center_x = (minx + maxx) / 2
        center_y = (miny + maxy) / 2

        scaled_width = (maxx - minx) * self.parse_value(
            self.options.bounding_box_scale_x
        )
        scaled_height = (maxy - miny) * self.parse_value(
            self.options.bounding_box_scale_y
        )

        # Scaled inclusive bounding box by self.options.bounding_box_scale_x
        #  and self.options.bounding_box_scale_y.
        scaled_box = (
            center_x - (0.5 * scaled_width),
            center_y - (0.5 * scaled_height),
            center_x + (0.5 * scaled_width),
            center_y + (0.5 * scaled_height),
        )

        self.dict_bounds[chip_name]["scaled_box"] = scaled_box
        self.dict_bounds[chip_name]["inclusive_box"] = (minx, miny, maxx, maxy)

        return scaled_box, (minx, miny, maxx, maxy)

    def _check_qcomps(
        self, highlight_qcomponents: Optional[list] = None
    ) -> Tuple[list, int]:
        """Confirm the list doesn't have names of components repeated. Confirm
        that the name of component exists in QDesign.

        Args:
            highlight_qcomponents (list, optional): List of strings which
                                        denote the name of QComponents to render.
                                        Empty list means to render entire design.
                                        Defaults to [].

        Returns:
            Tuple[list, int]:
            list: Unique list of QComponents to render.
            int: 0 if all ended well. Otherwise,
            1 if QComponent name not in design.
        """
        if highlight_qcomponents is None:
            highlight_qcomponents = []

        # Remove identical QComponent names.
        unique_qcomponents = list(set(highlight_qcomponents))

        # Confirm all QComponent are in design.
        for qcomp in unique_qcomponents:
            if qcomp not in self.design.name_to_id:
                self.logger.warning(
                    f"The component={qcomp} in highlight_qcomponents not"
                    " in QDesign. The GDS data not generated."
                )
                return unique_qcomponents, 1

        # For Subtraction bounding box.
        # If list passed to export is the whole chip, then want to use the
        # bounding box from design planar.  If list is subset of chip, then
        # calculate a custom bounding box and scale it.

        # pylint: disable=protected-access
        if len(unique_qcomponents) == len(self.design._components):
            # Since user wants all of the chip to be rendered, use the
            # design.planar bounding box.
            unique_qcomponents[:] = []

        return unique_qcomponents, 0

    def _create_qgeometry_for_gds(
        self, highlight_qcomponents: Optional[list] = None
    ) -> int:
        """Using self.design, this method does the following:

        1. Gather the QGeometries to be used to write to file.
           Duplicate names in highlight_qcomponents will be removed without
           warning.

        2. Populate self.dict_bounds, for each chip, contains the maximum bound
           for all elements to render.

        3. Calculate scaled bounding box to emulate size of chip using
           self.bounding_box_scale(x and y) and place into
           self.dict_bounds[chip_name]['for_subtract'].

        4. Gather Geometries to export to GDS format.

        Args:
            highlight_qcomponents (list): List of strings which denote the name
                            of QComponents to render.
                            If empty, render all components in design.
                            If QComponent names are duplicated,
                            duplicates will be ignored.

        Returns:
            int: 0 if all ended well.
            Otherwise, 1 if QComponent name(s) not in design.
        """
        if highlight_qcomponents is None:
            highlight_qcomponents = []
        unique_qcomponents, status = self._check_qcomps(highlight_qcomponents)
        if status == 1:
            return 1
        self.dict_bounds.clear()

        for chip_name, _ in self.chip_info.items():
            # put the QGeometry into GDS format.
            # There can be more than one chip in QGeometry.
            # They all export to one gds file.
            self.chip_info[chip_name]["all_subtract"] = []
            self.chip_info[chip_name]["all_no_subtract"] = []

            self.dict_bounds[chip_name] = Dict()
            self.dict_bounds[chip_name]["gather"] = []
            self.dict_bounds[chip_name]["for_subtract"] = tuple()
            all_table_subtracts = []
            all_table_no_subtracts = []

            for table_name in self.design.qgeometry.get_element_types():
                # Get table for chip and table_name, and reduce
                # to keep just the list of unique_qcomponents.
                table = self._get_table(table_name, unique_qcomponents, chip_name)

                if table_name == "junction":
                    self.chip_info[chip_name]["junction"] = deepcopy(table)
                else:
                    # For every chip, and layer, separate the "subtract"
                    # and "no_subtract" elements and gather bounds.
                    # self.dict_bounds[chip_name] = list_bounds
                    self._gather_subtract_elements_and_bounds(
                        chip_name,
                        table_name,
                        table,
                        all_table_subtracts,
                        all_table_no_subtracts,
                    )

            # If list of QComponents provided, use the
            # bounding_box_scale(x and y), otherwise use self._chips.
            scaled_max_bound, max_bound = self._scale_max_bounds(
                chip_name, self.dict_bounds[chip_name]["gather"]
            )
            if highlight_qcomponents:
                self.dict_bounds[chip_name]["for_subtract"] = scaled_max_bound
            else:
                chip_box, status = self.design.get_x_y_for_chip(chip_name)
                if status == 0:
                    self.dict_bounds[chip_name]["for_subtract"] = chip_box
                else:
                    self.dict_bounds[chip_name]["for_subtract"] = max_bound
                    self.logger.warning(
                        f"design.get_x_y_for_chip() did NOT return a good "
                        f"code for chip={chip_name},for ground subtraction-box"
                        f" using the size calculated from QGeometry, "
                        f"({max_bound}) will be used. "
                    )
            if is_true(self.options.ground_plane):
                self._handle_ground_plane(
                    chip_name, all_table_subtracts, all_table_no_subtracts
                )

        return 0

    def _handle_ground_plane(
        self, chip_name: str, all_table_subtracts: list, all_table_no_subtracts: list
    ):
        """Place all the subtract geometries for one chip into
        self.chip_info[chip_name]['all_subtract_true'].

        For LINESTRING within table that has a value for fillet, check if any
        segment is shorter than fillet radius.  If so, then break the
        LINESTRING so that shorter segments do not get fillet'ed and longer
        segments get fillet'ed.  Add the multiple LINESTRINGS back to table.
        Also remove "bad" LINESTRING from table.

        Then use _qgeometry_to_gds() to convert the QGeometry elements to gdstk
        elements.  The gdstk elements are placed in
        self.chip_info[chip_name]['q_subtract_true'].

        Args:
            chip_name (str): Chip_name that is being processed.
            all_table_subtracts (list): Add to self.chip_info by layer number.
            all_table_no_subtracts (list): Add to self.chip_info by layer number.
        """

        fix_short_segments = self.parse_value(self.options.short_segments_to_not_fillet)
        all_layers = self.design.qgeometry.get_all_unique_layers(chip_name)

        for chip_layer in all_layers:
            copy_subtract = []
            copy_no_subtract = []
            copy_subtract = deepcopy(all_table_subtracts)
            copy_no_subtract = deepcopy(all_table_no_subtracts)

            for item in copy_subtract:
                item = item[item["layer"] == chip_layer]

            for item_no in copy_no_subtract:
                item_no = item_no[item_no["layer"] == chip_layer]

            self.chip_info[chip_name][chip_layer]["all_subtract_true"] = (
                geopandas.GeoDataFrame(pd.concat(copy_subtract, ignore_index=False))
            )

            self.chip_info[chip_name][chip_layer]["all_subtract_false"] = (
                geopandas.GeoDataFrame(pd.concat(copy_no_subtract, ignore_index=False))
            )

            self.chip_info[chip_name][chip_layer]["all_subtract_true"] = self.chip_info[
                chip_name
            ][chip_layer]["all_subtract_true"].reset_index()
            self.chip_info[chip_name][chip_layer]["all_subtract_false"] = (
                self.chip_info[chip_name][chip_layer][
                    "all_subtract_false"
                ].reset_index()
            )

            if is_true(fix_short_segments):
                self._fix_short_segments_within_table(
                    chip_name, chip_layer, "all_subtract_true"
                )
                self._fix_short_segments_within_table(
                    chip_name, chip_layer, "all_subtract_false"
                )

            self.chip_info[chip_name][chip_layer]["q_subtract_true"] = self.chip_info[
                chip_name
            ][chip_layer]["all_subtract_true"].apply(self._qgeometry_to_gds, axis=1)

            self.chip_info[chip_name][chip_layer]["q_subtract_false"] = self.chip_info[
                chip_name
            ][chip_layer]["all_subtract_false"].apply(self._qgeometry_to_gds, axis=1)

    # Handling Fillet issues.

    def _fix_short_segments_within_table(
        self, chip_name: str, chip_layer: int, all_sub_true_or_false: str
    ):
        """Update self.chip_info geopandas.GeoDataFrame.

        Will iterate through the rows to examine the LineString.
        Then determine if there is a segment that is shorter than the criteria
        based on default_options. If so, then remove the row, and append
        shorter LineString with no fillet, within the dataframe.

        Args:
            chip_name (str): The name of chip.
            chip_layer (int): The layer within the chip to be evaluated.
            all_sub_true_or_false (str): To be used within self.chip_info:
                                'all_subtract_true' or 'all_subtract_false'.
        """
        # pylint: disable=too-many-locals
        data_frame = self.chip_info[chip_name][chip_layer][all_sub_true_or_false]
        df_fillet = data_frame[-data_frame["fillet"].isnull()]

        if not df_fillet.empty:
            # Don't edit the table when iterating through the rows.
            # Save info in dict and then edit the table.
            edit_index = dict()
            for index, row in df_fillet.iterrows():
                # print(
                #     f'With parse_value: {self.parse_value(row.fillet)}, '
                #     f'row.fillet: {row.fillet}')
                status, all_shapelys = self._check_length(row.geometry, row.fillet)
                if status > 0:
                    edit_index[index] = all_shapelys

            df_copy = self.chip_info[chip_name][chip_layer][all_sub_true_or_false].copy(
                deep=True
            )
            for del_key, the_shapes in edit_index.items():
                # copy row "index" into a new data-frame "status" times.
                # Then replace the LONG shapely with all_shapelys.
                # For any entries in edit_index, edit table here.
                orig_row = df_copy.loc[del_key].copy(deep=True)
                df_copy = df_copy.drop(index=del_key)

                for dummy_new_row, short_shape in the_shapes.items():
                    orig_row["geometry"] = short_shape["line"]
                    orig_row["fillet"] = short_shape["fillet"]
                    # Keep ignore_index=False, otherwise,
                    # the other del_key will not be found.
                    df_copy = pd.concat([df_copy, pd.DataFrame([orig_row])], ignore_index=False)

            self.chip_info[chip_name][chip_layer][all_sub_true_or_false] = df_copy.copy(
                deep=True
            )

    def _check_length(
        self, a_shapely: shapely.geometry.LineString, a_fillet: float
    ) -> Tuple[int, Dict]:
        """Determine if a_shapely has short segments based on scaled fillet
        value.

        Use check_short_segments_by_scaling_fillet to determine the criteria
        for flagging a segment.  Return Tuple with flagged segments.

        The "status" returned in int:
            * -1: Method needs to update the return code.
            * 0: No issues, no short segments found
            * int: The number of shapelys returned. New shapelys, should
                    replace the ones provided in a_shapely

        The "shorter_lines" returned in dict:
        key: Using the index values from list(a_shapely.coords)
        value: dict() for each new, shorter, LineString

        The dict()
        key: fillet, value: can be float from before, or undefined to
                            denote no fillet.
        key: line, value: shorter LineString

        Args:
            a_shapely (shapely.geometry.LineString): A shapely object that
                                                    needs to be evaluated.
            a_fillet (float): From component developer.

        Returns:
            Tuple[int, Dict]:
            int: Number of short segments that should not have fillet.
            Dict: The key is an index into a_shapely. The value is a dict with
            fillet and shorter LineString.
        """
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-arguments
        # pylint: disable=too-many-statements
        # pylint: disable=too-many-branches

        # Holds all of the index of when a segment is too short.
        idx_bad_fillet = list()
        status = -1  # Initialize to meaningless value.
        coords = list(a_shapely.coords)
        len_coords = len(coords)

        all_idx_bad_fillet = dict()

        self._identify_vertex_not_to_fillet(coords, a_fillet, all_idx_bad_fillet)

        shorter_lines = dict()

        idx_bad_fillet = sorted(all_idx_bad_fillet["reduced_idx"])
        status = len(idx_bad_fillet)

        if status:
            midpoints = all_idx_bad_fillet["midpoints"]
            no_fillet_vertices = list()
            fillet_vertices = list()

            # Gather the no-fillet segments
            for idx, (start, stop) in enumerate(idx_bad_fillet):
                no_fillet_vertices.clear()
                if idx == 0 and start == 0:
                    # The first segment.
                    if stop == len_coords - 1:
                        # Every vertex should not be fillet'd
                        no_fillet_vertices = coords[start:len_coords]
                        shorter_lines[stop] = dict(
                            {
                                "line": LineString(no_fillet_vertices),
                                "fillet": float("NaN"),
                            }
                        )
                    else:
                        no_fillet_vertices = coords[start : stop + 1]
                        no_fillet_vertices.append(midpoints[stop])
                        shorter_lines[stop] = dict(
                            {
                                "line": LineString(no_fillet_vertices),
                                "fillet": float("NaN"),
                            }
                        )
                elif idx == status - 1 and stop == len_coords - 1:
                    # The last segment
                    no_fillet_vertices = coords[start : stop + 1]
                    no_fillet_vertices.insert(0, midpoints[start - 1])
                    shorter_lines[stop] = dict(
                        {"line": LineString(no_fillet_vertices), "fillet": float("NaN")}
                    )
                else:
                    # Segment in between first and last segment.
                    no_fillet_vertices = coords[start : stop + 1]
                    no_fillet_vertices.insert(0, midpoints[start - 1])
                    no_fillet_vertices.append(midpoints[stop])
                    shorter_lines[stop] = dict(
                        {"line": LineString(no_fillet_vertices), "fillet": float("NaN")}
                    )
            # Gather the fillet segments.
            at_vertex = 0
            for idx, (start, stop) in enumerate(idx_bad_fillet):
                fillet_vertices.clear()
                if idx == 0 and start == 0:
                    pass  # just update at_vertex
                if idx == 0 and start == 1:
                    init_tuple = coords[0]
                    fillet_vertices = [init_tuple, midpoints[start - 1]]
                    shorter_lines[start] = dict(
                        {"line": LineString(fillet_vertices), "fillet": a_fillet}
                    )
                if idx == 0 and start > 1:
                    fillet_vertices = coords[0:start]
                    fillet_vertices.append(midpoints[start - 1])
                    shorter_lines[start] = dict(
                        {"line": LineString(fillet_vertices), "fillet": a_fillet}
                    )
                    if idx == status - 1 and stop != len_coords - 1:
                        # Extra segment after the last no-fillet.
                        fillet_vertices.clear()
                        fillet_vertices = coords[stop + 1 : len_coords]
                        fillet_vertices.insert(0, midpoints[stop])
                        shorter_lines[len_coords] = dict(
                            {"line": LineString(fillet_vertices), "fillet": a_fillet}
                        )
                elif idx == status - 1 and start == 0 and stop != len_coords - 1:
                    # At last tuple, and and start at first index,
                    # and the stop is not last index of coords.
                    fillet_vertices = coords[stop + 1 : len_coords]
                    fillet_vertices.insert(0, midpoints[stop])
                    shorter_lines[start] = dict(
                        {"line": LineString(fillet_vertices), "fillet": a_fillet}
                    )
                elif idx == status - 1 and stop != len_coords - 1:
                    # At last tuple, and the stop is not last index of coords.
                    fillet_vertices = coords[at_vertex + 1 : start]
                    fillet_vertices.insert(0, midpoints[at_vertex])
                    fillet_vertices.append(midpoints[start - 1])
                    shorter_lines[start] = dict(
                        {"line": LineString(fillet_vertices), "fillet": a_fillet}
                    )
                    # Extra segment after the last no-fillet.
                    fillet_vertices.clear()
                    fillet_vertices = coords[stop + 1 : len_coords]
                    fillet_vertices.insert(0, midpoints[stop])
                    shorter_lines[len_coords] = dict(
                        {"line": LineString(fillet_vertices), "fillet": a_fillet}
                    )
                else:
                    if (start - at_vertex) > 1:
                        fillet_vertices = coords[at_vertex + 1 : start]
                        fillet_vertices.insert(0, midpoints[at_vertex])
                        fillet_vertices.append(midpoints[start - 1])
                        shorter_lines[start] = dict(
                            {"line": LineString(fillet_vertices), "fillet": a_fillet}
                        )
                at_vertex = stop  # Need to update for every loop.
        else:
            # No short segments.
            shorter_lines[len_coords - 1] = a_shapely
        return status, shorter_lines

    def _identify_vertex_not_to_fillet(
        self, coords: list, a_fillet: float, all_idx_bad_fillet: dict
    ):
        """Use coords to denote segments that are too short.  In particular,
        when fillet'd, they will cause the appearance of incorrect fillet when
        graphed.

        Args:
            coords (list): User provide a list of tuples.
                    The tuple is (x,y) location for a vertex.
                    The list represents a LineString.
            a_fillet (float): The value provided by component developer.
            all_idx_bad_fillet (dict): An empty dict which will be
                                        populated by this method.

        Dictionary:
            Key 'reduced_idx' will hold list of tuples.
                    The tuples correspond to index for list named "coords".
            Key 'midpoints' will hold list of tuples.
                    The index of a tuple corresponds to two index within coords.
            For example, a index in midpoints is x,
            that corresponds midpoint of segment x-1 to x.
        """

        # Depreciated since there is no longer a scale factor
        # given to QCheckLength.
        # fillet_scale_factor = self.parse_value(
        #     self.options.check_short_segments_by_scaling_fillet)

        # precision = float(self.parse_value(self.options.precision))

        # For now, DO NOT allow the user of GDS to provide the precision.
        # user_precision = int(np.abs(np.log10(precision)))

        all_idx_bad_fillet["reduced_idx"] = get_range_of_vertex_to_not_fillet(
            coords, a_fillet, self.design.template_options.PRECISION, add_endpoints=True
        )
        midpoints = [
            self._midpoint_xy(
                coords[idx - 1][0], coords[idx - 1][1], vertex2[0], vertex2[1]
            )
            for idx, vertex2 in enumerate(coords)
            if idx > 0
        ]
        all_idx_bad_fillet["midpoints"] = midpoints

    # Move data around to be useful for GDS

    def _gather_subtract_elements_and_bounds(
        self,
        chip_name: str,
        table_name: str,
        table: geopandas.GeoDataFrame,
        all_subtracts: list,
        all_no_subtracts: list,
    ):
        """For every chip, and layer, separate the "subtract" and "no_subtract"
        elements and gather bounds for all the elements in qgeometries. Use
        format: f'{chip_name}_{table_name}s'.

        Args:
            chip_name (str): Name of chip.  Example is 'main'.
            table_name (str): There are multiple tables in QGeometry table.
                                Example: 'path' and 'poly'.
            table (geopandas.GeoDataFrame): Actual table for the name.
            all_subtracts (list): Pass by reference so method can update
                                    this list.
            all_no_subtracts (list): Pass by reference so method can update
                                    this list.
        """

        # Determine bound box and return scalar larger than size.
        bounds = tuple(self._get_bounds(table))

        # Add the bounds of each table to list.
        self.dict_bounds[chip_name]["gather"].append(bounds)

        if is_true(self.options.ground_plane):
            self._separate_subtract_shapes(chip_name, table_name, table)

            all_subtracts.append(
                getattr(self, f"{chip_name}_{table_name}_subtract_true")
            )
            all_no_subtracts.append(
                getattr(self, f"{chip_name}_{table_name}_subtract_false")
            )

        # Done because ground plane option may be false.
        # This is not used anywhere currently.
        # Keep this deprecated code.
        # polys use gdstk.Polygon;    paths use gdstk.LineString

        # q_geometries = table.apply(self._qgeometry_to_gds, axis=1)
        # setattr(self, f'{chip_name}_{table_name}s', q_geometries)

    def _get_table(
        self, table_name: str, unique_qcomponents: list, chip_name: str
    ) -> geopandas.GeoDataFrame:
        """If unique_qcomponents list is empty, get table using table_name from
        QGeometry tables for all elements with table_name.  Otherwise, return a
        table with fewer elements, for just the qcomponents within the
        unique_qcomponents list.

        Args:
            table_name (str): Can be "path", "poly", etc. from the
                            QGeometry tables.
            unique_qcomponents (list): User requested list of qcomponent
                            names to export to GDS file.

        Returns:
            geopandas.GeoDataFrame: Table of elements within the QGeometry.
        """

        # self.design.qgeometry.tables is a dict. key=table_name, value=geopandas.GeoDataFrame
        if len(unique_qcomponents) == 0:
            table = self.design.qgeometry.tables[table_name]
        else:
            table = self.design.qgeometry.tables[table_name]
            # Convert string QComponent.name  to QComponent.id
            highlight_id = [
                self.design.name_to_id[a_qcomponent]
                for a_qcomponent in unique_qcomponents
            ]

            # Remove QComponents which are not requested.
            table = table[table["component"].isin(highlight_id)]

        table = table[table["chip"] == chip_name]

        return table

    def _get_component(self, component_id):
        """Resolve a QComponent from a qgeometry component id."""
        return self._get_component_object(component_id)

    def _get_component_object(self, component_id):
        """Resolve a component object from a qgeometry component id."""
        try:
            component_id = int(component_id)
        except (TypeError, ValueError):
            pass

        components_by_id = getattr(self.design, "_components", {})
        component = components_by_id.get(component_id, None)
        if component is not None:
            return component

        design_components = getattr(self.design, "components", None)
        if hasattr(design_components, "get"):
            return design_components.get(component_id, None)

        return None

    def _resolve_component(self, component):
        """Resolve a component given a name, id, or QComponent instance."""
        if component is None:
            return None

        if isinstance(component, str):
            if component not in self.design.name_to_id:
                self.logger.warning(
                    f'Component name "{component}" not found when setting semantic group.'
                )
                return None
            return self._get_component(self.design.name_to_id[component])

        if isinstance(component, (int, np.integer)):
            qcomponent = self._get_component(component)
            if qcomponent is None:
                self.logger.warning(
                    f'Component id "{component}" not found when setting semantic group.'
                )
            return qcomponent

        if hasattr(component, "options"):
            return component

        self.logger.warning(
            f"Unsupported component reference {component!r} when setting semantic group."
        )
        return None

    def _get_component_id(self, component) -> Optional[int]:
        """Return the numeric component id when available."""
        if component is None:
            return None

        component_id = getattr(component, "id", None)
        if component_id is None:
            component_id = getattr(component, "_id", None)
        if component_id is None:
            component_name = self._get_component_name(component)
            component_id = self.design.name_to_id.get(component_name)

        if component_id is None:
            return None

        try:
            return int(component_id)
        except (TypeError, ValueError):
            return component_id

    def _get_component_options(self, component):
        """Return a component options container."""
        return getattr(component, "options", None) if component is not None else None

    def _get_component_option(self, component, option_name: str, default=None):
        """Read a component option from either attribute or mapping style options."""
        options = self._get_component_options(component)
        if options is None:
            return default

        option_value = getattr(options, option_name, None)
        if option_value is None and hasattr(options, "get"):
            option_value = options.get(option_name)

        return default if option_value is None else option_value

    def _set_component_option(self, component, option_name: str, value) -> bool:
        """Write a component option using mapping or attribute style access."""
        options = self._get_component_options(component)
        if options is None:
            return False

        try:
            options[option_name] = value
            return True
        except TypeError:
            try:
                setattr(options, option_name, value)
                return True
            except AttributeError:
                return False

    def _get_component_qgeometry_names(self, component) -> list:
        """Collect unique non-subtractive qgeometry names for a component."""
        component_id = self._get_component_id(component)
        if component_id is None:
            return []

        geometry_names = set()
        for table_name in self.design.qgeometry.get_element_types():
            table = self.design.qgeometry.tables[table_name]
            if table.empty:
                continue

            table = table[table["component"] == component_id]
            if table.empty:
                continue

            if "subtract" in table.columns:
                table = table[table["subtract"] != True]

            if "name" not in table.columns:
                continue

            geometry_names.update(
                str(name) for name in table["name"].dropna().tolist()
            )

        return sorted(geometry_names)

    def set_semantic_group(self, semantic_group: str, components: list) -> int:
        """Assign one simulation object name to all geometry in components.

        Args:
            semantic_group (str): Final simulation object name.
            components (list): Component names, ids, or QComponent instances.

        Returns:
            int: Number of components updated.
        """
        if semantic_group is None or str(semantic_group).strip() == "":
            self.logger.warning("semantic_group must be a non-empty string.")
            return 0

        if components is None:
            components = []

        semantic_group = self._normalize_simulation_object_name(semantic_group)
        if not semantic_group:
            self.logger.warning(
                "semantic_group must follow "
                '"<SIM_TYPE>__<OBJECT_KEY>" or "<SIM_TYPE>__<OBJECT_KEY>__<LOCAL_COMPONENT>".'
            )
            return 0

        updated = 0

        for component in components:
            qcomponent = self._resolve_component(component)
            if qcomponent is None:
                continue

            geometry_names = self._get_component_qgeometry_names(qcomponent)
            if not geometry_names:
                self.logger.warning(
                    f'Component "{self._get_component_name(qcomponent)}" has no '
                    "non-subtractive qgeometry to assign."
                )
                continue

            semantic_map = self._get_component_option(qcomponent, "semantic_map", Dict())
            if semantic_map is None:
                semantic_map = Dict()

            for geometry_name in geometry_names:
                semantic_map[geometry_name] = semantic_group

            if not self._set_component_option(qcomponent, "semantic_map", semantic_map):
                self.logger.warning(
                    f'Component "{self._get_component_name(qcomponent)}" has no writable options.'
                )
                continue

            updated += 1

        return updated

    def set_semantic_groups(self, semantic_map: DictType[str, list]) -> DictType[str, int]:
        """Assign multiple semantic groups from a mapping.

        Example:
            renderer.set_semantic_groups({
                "RO__MAIN": ["RO__MAIN__route", "RO__MAIN__tee"],
                "BUS__LEFT_RIGHT": ["BUS__LEFT_RIGHT__res"],
            })

        Args:
            semantic_map (Dict[str, list]): semantic_group -> component references.

        Returns:
            Dict[str, int]: Count of updated components per semantic group.
        """
        if semantic_map is None:
            return {}

        summary = {}
        for semantic_group, components in semantic_map.items():
            summary[semantic_group] = self.set_semantic_group(
                semantic_group, components
            )

        return summary

    @staticmethod
    def _get_row_value(row, key: str, default=None):
        """Get a value from either a Series row or an itertuples row."""
        if isinstance(row, pd.Series):
            return row.get(key, default)
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    @staticmethod
    def _get_component_name(component, fallback_component_id=None) -> str:
        """Return a stable component instance name."""
        if component is None:
            if fallback_component_id is not None:
                return f"component_{fallback_component_id}"
            return "component_unknown"

        component_name = getattr(component, "name", None) or getattr(
            component, "_name", None
        )
        if component_name:
            return str(component_name)

        component_fallback_id = getattr(component, "id", None) or getattr(
            component, "_id", None
        )
        if component_fallback_id is not None:
            return f"component_{component_fallback_id}"

        return "component_unknown"

    @staticmethod
    def _get_component_class_name(component) -> str:
        """Return the QComponent class name."""
        if component is None:
            return "UnknownComponent"
        return component.__class__.__name__

    def _get_normalized_naming_map(self) -> DictType[str, str]:
        """Return the canonical-to-abbreviation naming map."""
        naming_map = self.options.get("naming_map", Dict())
        normalized_map = {}

        if naming_map is None or not hasattr(naming_map, "items"):
            return normalized_map

        for canonical_type, abbreviation in naming_map.items():
            canonical_type = str(canonical_type).strip()
            abbreviation = str(abbreviation).strip()
            if canonical_type and abbreviation:
                normalized_map[canonical_type] = abbreviation

        return normalized_map

    def normalize_simulation_type(self, simulation_type: str) -> Tuple[str, str]:
        """Normalize a canonical type or abbreviation to a canonical/abbr pair."""
        simulation_type = "" if simulation_type is None else str(simulation_type).strip()
        if not simulation_type:
            return "", ""

        naming_map = self._get_normalized_naming_map()
        if simulation_type in naming_map:
            return simulation_type, naming_map[simulation_type]

        for canonical_type, abbreviation in naming_map.items():
            if simulation_type == abbreviation:
                return canonical_type, abbreviation

        return simulation_type, simulation_type

    @classmethod
    def _is_valid_semantic_name_token(cls, token) -> bool:
        """Return True when a semantic naming token matches ``[A-Za-z0-9_-]+``."""
        if token is None:
            return False

        token = str(token).strip()
        return bool(token) and cls._SEMANTIC_NAME_TOKEN_PATTERN.fullmatch(token) is not None

    def _split_semantic_name(
        self, semantic_name: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Split ``<SIM_TYPE>__<OBJECT_KEY>[__<LOCAL_COMPONENT>]`` on ``__``.

        Single underscores remain valid inside ``OBJECT_KEY`` and the local
        component token. Double underscores are reserved as grammar separators.
        """
        if semantic_name is None:
            return None, None, None

        semantic_name = str(semantic_name).strip()
        if not semantic_name:
            return None, None, None

        name_parts = semantic_name.split(self._SEMANTIC_NAME_SEPARATOR)
        if len(name_parts) not in (2, 3):
            return None, None, None

        raw_type = name_parts[0].strip() or None
        object_key = name_parts[1].strip() or None
        local_component = None
        if len(name_parts) == 3:
            local_component = name_parts[2].strip() or None

        if not self._is_valid_semantic_name_token(raw_type):
            return None, None, None
        if not self._is_valid_semantic_name_token(object_key):
            return None, None, None
        if local_component is not None and not self._is_valid_semantic_name_token(
            local_component
        ):
            return None, None, None

        return raw_type, object_key, local_component

    def build_simulation_object_name(
        self, simulation_fields: DictType[str, Optional[str]]
    ) -> str:
        """Build ``<ABBREVIATION>__<OBJECT_KEY>`` using naming_map."""
        canonical_type = simulation_fields.get("canonical_type")
        if canonical_type is None:
            canonical_type = simulation_fields.get("type")
        if canonical_type is None:
            canonical_type = simulation_fields.get("abbreviation")

        object_key = simulation_fields.get("object_key")

        canonical_type, abbreviation = self.normalize_simulation_type(canonical_type)
        object_key = "" if object_key is None else str(object_key).strip()

        if not abbreviation or not self._is_valid_semantic_name_token(abbreviation):
            return ""
        if not self._is_valid_semantic_name_token(object_key):
            return ""

        return f"{abbreviation}{self._SEMANTIC_NAME_SEPARATOR}{object_key}"

    def _normalize_simulation_object_name(self, simulation_object_name: str) -> str:
        """Normalize a semantic name to the short-form simulation object name."""
        parsed_component_fields = self.parse_component_name(simulation_object_name)
        canonical_type = parsed_component_fields.get("canonical_type")
        object_key = parsed_component_fields.get("object_key")
        if not canonical_type or not object_key:
            return ""

        return self.build_simulation_object_name(
            {
                "canonical_type": canonical_type,
                "object_key": object_key,
            }
        )

    def parse_component_name(self, component_name: str) -> DictType[str, Optional[str]]:
        """Parse ``<SIM_TYPE>__<OBJECT_KEY>[__<LOCAL_COMPONENT>]``."""
        parsed_fields = {
            "type": None,
            "canonical_type": None,
            "abbreviation": None,
            "object_key": None,
            "local_component": None,
            "raw_type": None,
        }

        if component_name is None:
            return parsed_fields

        component_name = str(component_name).strip()
        if not component_name:
            return parsed_fields

        raw_type, object_key, local_component = self._split_semantic_name(component_name)
        if raw_type is None or object_key is None:
            return parsed_fields

        canonical_type, abbreviation = self.normalize_simulation_type(raw_type)

        parsed_fields["raw_type"] = raw_type
        parsed_fields["type"] = abbreviation or raw_type
        parsed_fields["canonical_type"] = canonical_type or raw_type
        parsed_fields["abbreviation"] = abbreviation or raw_type
        parsed_fields["object_key"] = object_key
        parsed_fields["local_component"] = local_component

        return parsed_fields

    def _get_default_simulation_object_name(
        self, component_name: str, parsed_component_fields: DictType[str, Optional[str]]
    ) -> str:
        """Return default ownership based on the component naming grammar."""
        parsed_type = parsed_component_fields.get("canonical_type")
        parsed_object_key = parsed_component_fields.get("object_key")
        if parsed_type and parsed_object_key:
            simulation_object_name = self.build_simulation_object_name(
                {
                    "canonical_type": parsed_type,
                    "object_key": parsed_object_key,
                }
            )
            if simulation_object_name:
                return simulation_object_name

        normalized_component_name = self._normalize_simulation_object_name(component_name)
        return normalized_component_name or component_name

    def _get_local_semantic_map(self, component) -> DictType[str, str]:
        """Return the component-local semantic_map override."""
        semantic_map = self._get_component_option(component, "semantic_map", Dict())
        if semantic_map is None:
            return Dict()
        if hasattr(semantic_map, "items"):
            return semantic_map

        self.logger.warning(
            f'Component "{self._get_component_name(component)}" has a non-mapping semantic_map; ignoring it.'
        )
        return Dict()

    def _match_semantic_rule(
        self, component_class: str, qgeometry_name: str
    ) -> Optional[str]:
        """Match a qgeometry name to a renderer semantic rule."""
        semantic_rules = self.options.get("semantic_rules", Dict())
        component_rules = semantic_rules.get(component_class, None)

        if not component_rules:
            return None

        qgeometry_name = str(qgeometry_name)
        for pattern, simulation_template in component_rules.items():
            try:
                if re.fullmatch(pattern, qgeometry_name):
                    simulation_template = str(simulation_template).strip()
                    if simulation_template and simulation_template.upper() != "UNASSIGNED":
                        return simulation_template
                    return None
            except re.error as ex:
                self.logger.warning(
                    f'Invalid semantic rule regex "{pattern}" for '
                    f'component class "{component_class}": {ex}'
                )

        return None

    def _apply_simulation_object_template(
        self,
        simulation_template: str,
        component_name: str,
        parsed_component_fields: DictType[str, Optional[str]],
    ) -> str:
        """Format a simulation object template using parsed component fields."""
        default_simulation_object_name = self._get_default_simulation_object_name(
            component_name, parsed_component_fields
        )
        if simulation_template is None:
            return default_simulation_object_name

        simulation_template = str(simulation_template).strip()
        if not simulation_template or simulation_template.upper() == "UNASSIGNED":
            return default_simulation_object_name

        canonical_type = parsed_component_fields.get("canonical_type") or ""
        abbreviation = parsed_component_fields.get("abbreviation") or ""
        format_context = {
            # Keep ``type`` canonical so semantic_rules stay readable and
            # project abbreviations remain a naming_map concern.
            "type": canonical_type or abbreviation,
            "object_key": parsed_component_fields.get("object_key") or "",
            "local_component": parsed_component_fields.get("local_component") or "",
            "canonical_type": canonical_type or abbreviation,
            "abbreviation": abbreviation or canonical_type,
        }

        missing_template_fields = [
            field_name
            for field_name in (
                "type",
                "object_key",
                "local_component",
                "canonical_type",
                "abbreviation",
            )
            if "{" + field_name + "}" in simulation_template and not format_context[field_name]
        ]
        if missing_template_fields:
            self.logger.warning(
                f'Unable to apply semantic template "{simulation_template}" '
                f'to component "{component_name}" because fields '
                f"{missing_template_fields} are missing from the component name."
            )
            return default_simulation_object_name

        try:
            formatted_name = simulation_template.format(**format_context).strip()
        except (IndexError, KeyError, ValueError) as ex:
            self.logger.warning(
                f'Unable to format semantic template "{simulation_template}" '
                f'for component "{component_name}": {ex}'
            )
            return default_simulation_object_name

        normalized_name = self._normalize_simulation_object_name(formatted_name)
        if normalized_name:
            return normalized_name

        self.logger.warning(
            f'Semantic template "{simulation_template}" produced invalid '
            f'simulation object name "{formatted_name}" for component '
            f'"{component_name}".'
        )
        return default_simulation_object_name

    def determine_simulation_object(
        self,
        component,
        qgeometry_name: str,
        parsed_component_fields: Optional[DictType[str, Optional[str]]] = None,
    ) -> str:
        """Determine final ownership using local map, global rules, then default grammar."""
        component_name = self._get_component_name(component)
        if parsed_component_fields is None:
            parsed_component_fields = self.parse_component_name(component_name)

        local_semantic_map = self._get_local_semantic_map(component)
        if qgeometry_name in local_semantic_map:
            return self._apply_simulation_object_template(
                local_semantic_map[qgeometry_name],
                component_name,
                parsed_component_fields,
            )

        component_class = self._get_component_class_name(component)
        matched_rule = self._match_semantic_rule(component_class, qgeometry_name)
        if matched_rule is not None:
            return self._apply_simulation_object_template(
                matched_rule, component_name, parsed_component_fields
            )

        return self._get_default_simulation_object_name(
            component_name, parsed_component_fields
        )

    def _resolve_semantic_object(self, row) -> Optional[str]:
        """Resolve the simulation object name for a qgeometry or junction row."""
        subtract = self._get_row_value(row, "subtract", False)
        if bool(subtract):
            return None

        component_id = self._get_row_value(row, "component", None)
        component = self._get_component_object(component_id)
        component_name = self._get_component_name(
            component, fallback_component_id=component_id
        )
        qgeometry_name = self._get_row_value(row, "name", "")
        parsed_component_fields = self.parse_component_name(component_name)

        return self.determine_simulation_object(
            component,
            qgeometry_name,
            parsed_component_fields=parsed_component_fields,
        )

    def _build_chip_semantic_cell_name(
        self, chip_name: str, simulation_object_name: str
    ) -> str:
        """Build the exported semantic-object cell name."""
        chip_name = "" if chip_name is None else str(chip_name).strip()
        simulation_object_name = (
            "" if simulation_object_name is None else str(simulation_object_name).strip()
        )
        if not simulation_object_name:
            return ""

        if chip_name and self._use_semantic_cell_chip_prefix():
            return f"{chip_name}{self._SEMANTIC_NAME_SEPARATOR}{simulation_object_name}"

        existing_details = self.semantic_cell_details.get(simulation_object_name, {})
        existing_chip = existing_details.get("chip")
        existing_role = existing_details.get("role")
        if (
            chip_name
            and existing_role == "semantic_object"
            and existing_chip not in (None, chip_name)
        ):
            warning_key = (simulation_object_name, chip_name, existing_chip)
            if warning_key not in self._semantic_name_collision_warnings:
                self.logger.warning(
                    f'Semantic cell name "{simulation_object_name}" would collide across '
                    f'chips "{existing_chip}" and "{chip_name}". Falling back to a '
                    "chip-qualified semantic cell name for this object."
                )
                self._semantic_name_collision_warnings.add(warning_key)
            return f"{chip_name}{self._SEMANTIC_NAME_SEPARATOR}{simulation_object_name}"

        return simulation_object_name

    def _build_component_subcell_name(
        self, chip_name: str, simulation_object_name: str, component_name: str
    ) -> str:
        """Build a unique component child cell name under a semantic object."""
        parent_name = self._build_chip_semantic_cell_name(chip_name, simulation_object_name)
        component_name = "" if component_name is None else str(component_name).strip()
        if not parent_name or not component_name:
            return ""

        return (
            f"{parent_name}{self._SEMANTIC_NAME_SEPARATOR}COMP"
            f"{self._SEMANTIC_NAME_SEPARATOR}{component_name}"
        )

    def _ensure_cell_reference(self, parent_cell: gdstk.Cell, child_cell: gdstk.Cell) -> None:
        """Add a child reference only once."""
        child_name = getattr(child_cell, "name", None)
        for reference in getattr(parent_cell, "references", []):
            ref_cell = self._get_reference_cell(reference)
            if ref_cell is not None and getattr(ref_cell, "name", None) == child_name:
                return
        parent_cell.add(gdstk.Reference(child_cell))

    def _get_or_create_semantic_parent_cell(
        self, lib: gdstk.Library, chip_name: str, simulation_object_name: str
    ) -> Optional[gdstk.Cell]:
        """Get or create the top-level semantic object cell."""
        semantic_cell_name = self._build_chip_semantic_cell_name(
            chip_name, simulation_object_name
        )
        if not semantic_cell_name:
            return None

        if semantic_cell_name not in self.semantic_cells:
            self.semantic_cells[semantic_cell_name] = lib.new_cell(semantic_cell_name)
            self.semantic_cell_details[semantic_cell_name] = {
                "role": "semantic_object",
                "chip": chip_name,
                "simulation_object_name": simulation_object_name,
            }

        return self.semantic_cells[semantic_cell_name]

    def _get_or_create_semantic_cell(
        self, lib: gdstk.Library, row
    ) -> Optional[gdstk.Cell]:
        """Get or create the semantic target cell for a qgeometry row."""
        simulation_object_name = self._resolve_semantic_object(row)
        if simulation_object_name is None:
            return None

        chip_name = self._get_row_value(row, "chip", None)
        semantic_parent_cell = self._get_or_create_semantic_parent_cell(
            lib, chip_name, simulation_object_name
        )
        if semantic_parent_cell is None:
            return None

        if not self._use_semantic_component_subcells():
            return semantic_parent_cell

        component_id = self._get_row_value(row, "component", None)
        component = self._get_component_object(component_id)
        component_name = self._get_component_name(
            component, fallback_component_id=component_id
        )
        component_cell_name = self._build_component_subcell_name(
            chip_name, simulation_object_name, component_name
        )
        if not component_cell_name:
            return semantic_parent_cell

        if component_cell_name not in self.semantic_cells:
            self.semantic_cells[component_cell_name] = lib.new_cell(component_cell_name)
            self.semantic_cell_details[component_cell_name] = {
                "role": "component_subcell",
                "chip": chip_name,
                "simulation_object_name": simulation_object_name,
                "component_name": component_name,
                "parent_semantic_cell_name": semantic_parent_cell.name,
            }

        component_cell = self.semantic_cells[component_cell_name]
        self._ensure_cell_reference(semantic_parent_cell, component_cell)
        return component_cell

    def _register_semantic_metadata(self, semantic_cell_name: str, row) -> None:
        """Preserve source metadata for future HFSS/Q3D reconstruction."""
        if semantic_cell_name not in self.semantic_metadata:
            self.semantic_metadata[semantic_cell_name] = []

        component_id = self._get_row_value(row, "component", None)
        component = self._get_component_object(component_id)
        parsed_component_fields = self.parse_component_name(
            self._get_component_name(component, fallback_component_id=component_id)
        )
        semantic_details = self.semantic_cell_details.get(semantic_cell_name, {})
        metadata_entry = {
            "semantic_cell_name": semantic_cell_name,
            "simulation_object_name": semantic_details.get("simulation_object_name"),
            "semantic_cell_role": semantic_details.get("role", "semantic_object"),
            "parent_semantic_cell_name": semantic_details.get(
                "parent_semantic_cell_name"
            ),
            "component_id": component_id,
            "component_name": self._get_component_name(
                component, fallback_component_id=component_id
            ),
            "component_class": self._get_component_class_name(component),
            "source_raw_type": parsed_component_fields.get("raw_type"),
            "source_type": parsed_component_fields.get("type"),
            "canonical_type": parsed_component_fields.get("canonical_type"),
            "abbreviation": parsed_component_fields.get("abbreviation"),
            "object_key": parsed_component_fields.get("object_key"),
            "source_local_component": parsed_component_fields.get("local_component"),
            "qgeometry_name": self._get_row_value(row, "name", None),
            "layer": self._get_row_value(row, "layer", None),
            "datatype": self._get_row_value(row, "datatype", None),
            "chip": self._get_row_value(row, "chip", None),
        }
        self.semantic_metadata[semantic_cell_name].append(metadata_entry)

    def get_semantic_metadata(self) -> DictType[str, list]:
        """Return preserved semantic metadata keyed by semantic cell name."""
        return self.semantic_metadata

    @staticmethod
    def _json_safe_metadata_value(value):
        """Convert numpy/pandas scalar metadata into JSON-safe Python values."""
        if value is None:
            return None
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.bool_):
            return bool(value)

        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        return value

    def _export_semantic_metadata(self, gds_file_name: str) -> Optional[str]:
        """Write preserved semantic ownership metadata alongside the exported GDS."""
        output_directory = os.path.dirname(os.path.abspath(gds_file_name))
        metadata_path = os.path.join(output_directory, "semantic_export_map.json")
        exported_metadata = {}

        metadata_keys = sorted(
            set(self.semantic_cell_details.keys()) | set(self.semantic_metadata.keys())
        )
        for semantic_cell_name in metadata_keys:
            metadata_entries = self.semantic_metadata.get(semantic_cell_name, [])
            semantic_details = self.semantic_cell_details.get(semantic_cell_name, {})
            exported_metadata[semantic_cell_name] = {
                "role": self._json_safe_metadata_value(
                    semantic_details.get("role", "semantic_object")
                ),
                "chip": self._json_safe_metadata_value(semantic_details.get("chip")),
                "simulation_object_name": self._json_safe_metadata_value(
                    semantic_details.get("simulation_object_name")
                ),
                "component_name": self._json_safe_metadata_value(
                    semantic_details.get("component_name")
                ),
                "parent_semantic_cell_name": self._json_safe_metadata_value(
                    semantic_details.get("parent_semantic_cell_name")
                ),
                "source_entries": [
                    {
                        key: self._json_safe_metadata_value(value)
                        for key, value in metadata_entry.items()
                    }
                    for metadata_entry in metadata_entries
                ],
            }

        for path_label, target_path in (
            ("semantic export map", metadata_path),
            (
                "legacy semantic metadata",
                os.path.join(output_directory, "semantic_metadata.json"),
            ),
        ):
            try:
                with open(target_path, "w", encoding="utf-8") as metadata_file:
                    json.dump(exported_metadata, metadata_file, indent=2, sort_keys=True)
                    metadata_file.write("\n")
            except OSError as ex:
                self.logger.warning(
                    f'Unable to export {path_label} to "{target_path}": {ex}'
                )
                if target_path == metadata_path:
                    return None

        return metadata_path

    def _export_naming_map_metadata(self, gds_file_name: str) -> Optional[str]:
        """Write the normalized naming_map alongside the exported GDS."""
        output_directory = os.path.dirname(os.path.abspath(gds_file_name))
        naming_map_path = os.path.join(output_directory, "semantic_naming_map.json")
        naming_map = self._get_normalized_naming_map()

        try:
            with open(naming_map_path, "w", encoding="utf-8") as naming_file:
                json.dump(naming_map, naming_file, indent=2, sort_keys=True)
                naming_file.write("\n")
        except OSError as ex:
            self.logger.warning(
                f'Unable to export semantic naming map to "{naming_map_path}": {ex}'
            )
            return None

        return naming_map_path

    def _populate_semantic_qgeometry(self, lib: gdstk.Library, chip_name: str) -> None:
        """Route non-subtractive qgeometry into reconstructed object cells."""
        for chip_layer in self.design.qgeometry.get_all_unique_layers(chip_name):
            data_frame = self.chip_info[chip_name][chip_layer].get("all_subtract_false")
            gds_elements = self.chip_info[chip_name][chip_layer].get("q_subtract_false")

            if data_frame is None or gds_elements is None:
                continue

            if hasattr(gds_elements, "tolist"):
                element_iterable = gds_elements.tolist()
            elif hasattr(gds_elements, "values"):
                element_iterable = list(gds_elements.values)
            else:
                element_iterable = list(gds_elements)

            for (_, row), gds_element in zip(data_frame.iterrows(), element_iterable):
                if gds_element is None:
                    continue
                semantic_cell = self._get_or_create_semantic_cell(lib, row)
                if semantic_cell is None:
                    continue
                semantic_cell.add(gds_element)
                self._register_semantic_metadata(semantic_cell.name, row)

    def _add_semantic_cells_to_top(self, top_cell: gdstk.Cell) -> None:
        """Reference every populated semantic cell from TOP in legacy mode."""
        semantic_object_cells = sorted(
            (
                semantic_cell
                for semantic_cell_name, semantic_cell in self.semantic_cells.items()
                if self.semantic_cell_details.get(semantic_cell_name, {}).get("role")
                != "component_subcell"
            ),
            key=lambda cell: cell.name,
        )
        for semantic_cell in semantic_object_cells:
            if semantic_cell.bounding_box() is not None:
                top_cell.add(gdstk.Reference(semantic_cell))

    @staticmethod
    def _get_cell_by_name(lib: gdstk.Library, cell_name: str) -> Optional[gdstk.Cell]:
        """Return the first library cell that matches ``cell_name``."""
        if lib is None or not cell_name:
            return None
        return next((cell for cell in lib.cells if cell.name == cell_name), None)

    @staticmethod
    def _get_reference_cell(reference) -> Optional[gdstk.Cell]:
        """Resolve the referenced cell from a gdstk reference object.

        Some gdstk builds expose the target cell as ``ref_cell`` and others as
        ``cell``. Support both so hierarchy traversal and cleanup stay robust.
        """
        if reference is None:
            return None

        ref_cell = getattr(reference, "ref_cell", None)
        if ref_cell is not None:
            return ref_cell

        ref_cell = getattr(reference, "cell", None)
        if isinstance(ref_cell, gdstk.Cell):
            return ref_cell

        return None

    def _use_semantic_hierarchy(self) -> bool:
        """Return True when the final exported TOP should be semantic-only."""
        return is_true(self.options.get("semantic_hierarchy", False))

    def _use_semantic_cell_chip_prefix(self) -> bool:
        """Return True when semantic object cells should include the chip prefix."""
        return is_true(self.options.get("semantic_cell_chip_prefix", True))

    def _use_chip_container_prefix(self) -> bool:
        """Return True when chip container cells should use ``CHIP__<chip>``."""
        return is_true(self.options.get("chip_container_prefix", True))

    def _use_package_cell_chip_prefix(self) -> bool:
        """Return True when package helper cells should include the chip prefix."""
        return is_true(self.options.get("package_cell_chip_prefix", True))

    def _use_semantic_component_subcells(self) -> bool:
        """Return True when simulation objects should fan out into component subcells."""
        return is_true(self.options.get("semantic_component_subcells", False))

    def _get_chip_container_cell_name(self, chip_name: str) -> str:
        """Build the final container cell name for a chip."""
        chip_name = "" if chip_name is None else str(chip_name).strip()
        if not chip_name:
            return ""
        if self._use_chip_container_prefix():
            return f"CHIP__{chip_name}"
        return chip_name

    def _get_package_cell_name(self, package_kind: str, chip_name: str) -> str:
        """Build the exported package helper cell name."""
        package_kind = "" if package_kind is None else str(package_kind).strip().upper()
        chip_name = "" if chip_name is None else str(chip_name).strip()
        if not package_kind:
            return ""

        if self._use_package_cell_chip_prefix():
            return f"{chip_name}__{package_kind}" if chip_name else package_kind

        if len(self.chip_info) <= 1:
            return package_kind

        if not self._plain_package_name_collision_warned:
            self.logger.warning(
                "package_cell_chip_prefix=False is only safe for single-chip "
                "exports. Falling back to chip-qualified package cell names."
            )
            self._plain_package_name_collision_warned = True

        return f"{chip_name}__{package_kind}" if chip_name else package_kind

    def _rename_cell(self, lib: gdstk.Library, old_name: str, new_name: str):
        """Rename a cell when it exists, replacing an empty placeholder if needed."""
        cell = self._get_cell_by_name(lib, old_name)
        if cell is None:
            return None
        if old_name == new_name:
            return cell

        existing_cell = self._get_cell_by_name(lib, new_name)
        if existing_cell is not None and existing_cell is not cell:
            lib.remove(existing_cell)

        lib.rename_cell(cell, new_name)
        return cell

    def _add_semantic_cells_to_chip_cell(
        self, chip_name: str, chip_cell: gdstk.Cell
    ) -> None:
        """Reference every semantic simulation object that belongs to a chip."""
        semantic_cells = sorted(
            (
                (
                    semantic_details.get("simulation_object_name") or semantic_cell_name,
                    semantic_cell_name,
                )
                for semantic_cell_name, semantic_details in self.semantic_cell_details.items()
                if semantic_details.get("chip") == chip_name
                and semantic_details.get("role") != "component_subcell"
            ),
            key=itemgetter(0, 1),
        )
        for _, semantic_cell_name in semantic_cells:
            semantic_cell = self.semantic_cells.get(semantic_cell_name)
            if semantic_cell is not None and semantic_cell.bounding_box() is not None:
                chip_cell.add(gdstk.Reference(semantic_cell))

    def _create_substrate_cell(
        self, lib: gdstk.Library, chip_name: str
    ) -> Optional[gdstk.Cell]:
        """Create ``<chip>__SUBSTRATE`` from packaging_dict when configured."""
        pkg_dict = self.options.get("packaging_dict", {})
        chip_packaging = pkg_dict.get(chip_name, {})
        substrate_layer = chip_packaging.get("substrate", None)
        chip_bounds = self.dict_bounds.get(chip_name, {}).get("for_subtract", None)
        if substrate_layer is None or chip_bounds is None:
            return None

        substrate_cell = lib.new_cell(self._get_package_cell_name("SUBSTRATE", chip_name))
        minx, miny, maxx, maxy = chip_bounds
        substrate_cell.add(
            gdstk.rectangle(
                (minx, miny),
                (maxx, maxy),
                layer=int(substrate_layer),
                datatype=0,
            )
        )
        return substrate_cell

    def _create_vacuum_cell(self, lib: gdstk.Library) -> Optional[gdstk.Cell]:
        """Create ``ENV__VACUUM`` from packaging_dict when configured."""
        pkg_dict = self.options.get("packaging_dict", {})
        vacuum_layer = pkg_dict.get("global", {}).get("vacuum", None)
        if vacuum_layer is None or not self.dict_bounds:
            return None

        all_bounds = [
            bounds_dict.get("for_subtract")
            for bounds_dict in self.dict_bounds.values()
            if bounds_dict.get("for_subtract") is not None
        ]
        if not all_bounds:
            return None

        minx = min(bounds[0] for bounds in all_bounds)
        miny = min(bounds[1] for bounds in all_bounds)
        maxx = max(bounds[2] for bounds in all_bounds)
        maxy = max(bounds[3] for bounds in all_bounds)

        vacuum_cell = lib.new_cell("ENV__VACUUM")
        vacuum_cell.add(
            gdstk.rectangle(
                (minx, miny), (maxx, maxy), layer=int(vacuum_layer), datatype=0
            )
        )
        return vacuum_cell

    def _build_packaged_ground_cell(
        self, lib: gdstk.Library, chip_name: str, source_chip_cell=None
    ) -> Optional[gdstk.Cell]:
        """Build one physical packaged ground cell for a chip.

        When ``packaging_dict[chip]['ground']`` is configured, multiple source
        chip layers can map onto the same physical ground layer. Exporting one
        rectangle-minus-subtract boolean per source layer would stack several
        full-chip ground planes on top of each other and refill CPW cutouts.

        This helper preserves the historical positive-mask geometry intent by
        computing the packaged ground plane exactly once per chip in
        ``<chip>__GROUND``:

        ``chip rectangle on target layer - union(all relevant subtract=True geometry)``
        """
        pkg_dict = self.options.get("packaging_dict", {})
        target_layer = pkg_dict.get(chip_name, {}).get("ground", None)
        chip_bounds = self.dict_bounds.get(chip_name, {}).get("for_subtract", None)
        if target_layer is None or chip_bounds is None:
            return None

        precision = float(self.parse_value(self.options.precision))
        minx, miny, maxx, maxy = chip_bounds
        chip_rectangle = gdstk.rectangle(
            (minx, miny), (maxx, maxy), layer=int(target_layer), datatype=0
        )

        safe_subtracts = []
        for chip_layer in self.design.qgeometry.get_all_unique_layers(chip_name):
            if self._is_negative_mask(chip_name, chip_layer):
                continue

            q_subtract_true = self.chip_info[chip_name][chip_layer].get(
                "q_subtract_true", []
            )
            for geom in q_subtract_true:
                if geom is None:
                    continue
                if isinstance(geom, (gdstk.FlexPath, gdstk.RobustPath)):
                    safe_subtracts.extend(geom.to_polygons())
                else:
                    safe_subtracts.append(geom)

        if safe_subtracts:
            diff_geometry = gdstk.boolean(
                [chip_rectangle],
                safe_subtracts,
                "not",
                layer=int(target_layer),
                datatype=0,
                precision=precision,
            )
        else:
            diff_geometry = [chip_rectangle]

        if not diff_geometry:
            return None

        ground_cell = lib.new_cell(self._get_package_cell_name("GROUND", chip_name))
        ground_cell.add(*diff_geometry)

        if source_chip_cell is not None:
            layer_cell_pattern = re.compile(rf"^TOP_{re.escape(chip_name)}_\d+$")
            for reference in list(getattr(source_chip_cell, "references", [])):
                ref_cell = self._get_reference_cell(reference)
                if ref_cell is None:
                    continue
                if layer_cell_pattern.fullmatch(ref_cell.name):
                    continue
                ground_cell.add(gdstk.Reference(ref_cell))

        return ground_cell

    def _collect_reachable_cells(
        self, cell: Optional[gdstk.Cell], reachable: Optional[set] = None
    ) -> set:
        """Collect every cell reachable from ``cell`` through references."""
        if reachable is None:
            reachable = set()
        if cell is None or cell.name in reachable:
            return reachable

        reachable.add(cell.name)
        for reference in getattr(cell, "references", []):
            ref_cell = self._get_reference_cell(reference)
            if ref_cell is not None:
                self._collect_reachable_cells(ref_cell, reachable)
        return reachable

    def _prune_unreachable_cells(self, lib: gdstk.Library, root_cell: gdstk.Cell) -> None:
        """Remove any cell that is not reachable from the final exported TOP."""
        reachable = self._collect_reachable_cells(root_cell)
        if len(reachable) == 1 and getattr(root_cell, "references", []):
            self.logger.warning(
                "Skipping unreachable-cell pruning because TOP child references "
                "could not be resolved."
            )
            return
        for cell in list(lib.cells):
            if cell.name not in reachable:
                lib.remove(cell)

    def _build_semantic_chip_package_hierarchy(
        self, lib: gdstk.Library
    ) -> Optional[gdstk.Cell]:
        """Build the final semantic package hierarchy rooted at ``TOP``."""
        old_top = self._get_cell_by_name(lib, "TOP")
        if old_top is not None:
            lib.remove(old_top)

        final_top = self._get_cell_by_name(lib, "TOP")
        if final_top is not None:
            lib.remove(final_top)
        final_top = lib.new_cell("TOP")

        vacuum_cell = self._create_vacuum_cell(lib)
        if vacuum_cell is not None and vacuum_cell.bounding_box() is not None:
            final_top.add(gdstk.Reference(vacuum_cell))

        for chip_name in sorted(self.chip_info):
            chip_cell = lib.new_cell(self._get_chip_container_cell_name(chip_name))

            substrate_cell = self._create_substrate_cell(lib, chip_name)
            if substrate_cell is not None and substrate_cell.bounding_box() is not None:
                chip_cell.add(gdstk.Reference(substrate_cell))

            source_chip_cell = self._get_cell_by_name(lib, f"TOP_{chip_name}")
            chip_ground_layer = (
                self.options.get("packaging_dict", {}).get(chip_name, {}).get("ground")
            )
            if chip_ground_layer is not None:
                ground_cell = self._build_packaged_ground_cell(
                    lib, chip_name, source_chip_cell=source_chip_cell
                )
            else:
                ground_cell = self._rename_cell(
                    lib,
                    f"TOP_{chip_name}",
                    self._get_package_cell_name("GROUND", chip_name),
                )
            if ground_cell is not None and ground_cell.bounding_box() is not None:
                chip_cell.add(gdstk.Reference(ground_cell))

            self._add_semantic_cells_to_chip_cell(chip_name, chip_cell)

            if chip_cell.references or chip_cell.polygons or chip_cell.paths:
                final_top.add(gdstk.Reference(chip_cell))
            else:
                lib.remove(chip_cell)

        self._prune_unreachable_cells(lib, final_top)
        return final_top

    def inspect_component_geometry(
        self, pretty_print: bool = False
    ) -> DictType[str, DictType[str, list]]:
        """Inspect qgeometry names grouped by component class and table type."""
        inspection = defaultdict(lambda: defaultdict(set))

        for table_name in self.design.qgeometry.get_element_types():
            table = self.design.qgeometry.tables[table_name]
            if table.empty:
                continue

            if "subtract" in table.columns:
                table = table[table["subtract"] != True]

            for row in table.itertuples():
                component = self._get_component_object(row.component)
                component_class = self._get_component_class_name(component)
                qgeometry_name = getattr(row, "name", None)
                if qgeometry_name is None:
                    continue
                inspection[component_class][table_name].add(str(qgeometry_name))

        result = {
            component_class: {
                table_name: sorted(names)
                for table_name, names in sorted(table_map.items())
            }
            for component_class, table_map in sorted(inspection.items())
        }

        if pretty_print:
            pprint(result)

        return result

    def generate_default_semantic_template(
        self, pretty_print: bool = False
    ) -> DictType[str, DictType[str, str]]:
        """Generate a canonical semantic_rules template using ``{object_key}``."""
        inspection = self.inspect_component_geometry(pretty_print=False)
        template = {}

        for component_class, table_map in inspection.items():
            geometry_names = sorted(
                {name for names in table_map.values() for name in names}
            )
            template[component_class] = {
                geometry_name: "{canonical_type}__{object_key}"
                for geometry_name in geometry_names
            }

        if pretty_print:
            pprint(template)

        return template

    def generate_semantic_template(
        self, pretty_print: bool = False
    ) -> DictType[str, DictType[str, str]]:
        """Backward-compatible alias for generate_default_semantic_template."""
        return self.generate_default_semantic_template(pretty_print=pretty_print)

    # To export the data.

    def new_gds_library(self) -> gdstk.Library:
        """Creates a new GDS Library. Deletes the old. Create a new GDS library
        file. It can contains multiple cells.

        Returns:
            gdstk.Library: GDS library which can contain multiple cells.
        """

        self._update_units()

        if self.lib:
            # Clear old cells from the library
            for c in list(self.lib.cells):
                self.lib.remove(c)

        # Create a new GDS library file. It can contains multiple cells.
        self.lib = gdstk.Library(
            unit=float(self.parse_value(self.options.gds_unit)),
            precision=float(self.parse_value(self.options.precision)),
        )

        return self.lib

    def _check_cheese(self, chip: str, layer: int) -> int:
        """Examine the option for cheese_view_in_file.

        Args:
            chip (str): User defined chip name.
            layer (int): Layer used in chip.

        Returns:
            int: Observation of option based on chip and layer information.

            * 0 This is the initialization state.
            * 1 The layer is in the chip and cheese is True.
            * 2 The layer is in the chip and cheese is False.
            * 3 The chip is not in dict, so can't give answer.
            * 4 The layer is not in the chip, so can't give answer.
        """
        code = 0

        cheese_option = self.parse_value(self.options.cheese.view_in_file)

        if chip in cheese_option:
            if layer in cheese_option[chip]:
                if is_true(cheese_option[chip][layer]):
                    code = 1
                else:
                    code = 2
            else:
                code = 4
        else:
            code = 3

        return code

    def _check_no_cheese(self, chip: str, layer: int) -> int:
        """Examine the option for no_cheese_view_in_file.

        Args:
            chip (str): User defined chip name.
            layer (int): Layer used in chip.

        Returns:
            int: Observation of option based on chip and layer information.

            * 0 This is the initialization state.
            * 1 The layer is in the chip and viewing no-cheese is True.
            * 2 The layer is in the chip and viewing no-cheese is False.
            * 3 The chip is not in dict, so can't give answer.
            * 4 The layer is not in the chip, so can't give answer.
        """

        code = 0

        no_cheese_option = self.parse_value(self.options.no_cheese.view_in_file)

        if chip in no_cheese_option:
            if layer in no_cheese_option[chip]:
                if is_true(no_cheese_option[chip][layer]):
                    code = 1
                else:
                    code = 2
            else:
                code = 4
        else:
            code = 3

        return code

    def _check_either_cheese(self, chip: str, layer: int) -> int:
        """Use methods to check two options and give review of values for
        no_cheese_view_in_file and cheese_view_in_file.

        Args:
            chip (str): User defined chip name.
            layer (int): Layer used in chip.

        Returns:
            int: Observation of options based on chip and layer information.

            * 0 This is the initialization state.
            * 1 Show the layer in both cheese and no cheese
            * 2 Show the layer in just the cheese
            * 3 Show the no-cheese, but not the cheese
            * 4 Do NOT show the layer in neither cheese
            * 5 The chip is not in the default option.
            * 6 The layer is not in the chip dict.
        """
        # pylint: disable=too-many-return-statements
        code = 0
        no_cheese_code = self._check_no_cheese(chip, layer)
        cheese_code = self._check_cheese(chip, layer)

        if no_cheese_code == 0 or cheese_code == 0:
            self.logger.warning(
                "Not able to get no_cheese_view_in_file or "
                "cheese_view_in_file from self.options."
            )
            code = 0
            return code
        if no_cheese_code == 1 and cheese_code == 1:
            code = 1
            return code
        if no_cheese_code == 2 and cheese_code == 1:
            code = 2
            return code
        if no_cheese_code == 1 and cheese_code == 2:
            code = 3
            return code
        if no_cheese_code == 2 and cheese_code == 2:
            code = 4
            return code
        if no_cheese_code == 3 or cheese_code == 3:
            code = 5
            self.logger.warning(
                f"Chip={chip} is not either in no_cheese_view_in_file "
                f"or cheese_view_in_file from self.options."
            )
            return code
        if no_cheese_code == 4 or cheese_code == 4:
            code = 6
            self.logger.warning(
                f"layer={layer} is not in chip={chip} either in "
                f"no_cheese_view_in_file or cheese_view_in_file from self.options."
            )
            return code

        return code

    def _populate_cheese(self):
        """Iterate through each chip, then layer to determine the cheesing
        geometry."""
        
        # lib = self.lib
        cheese_sub_layer = int(self.parse_value(self.options.cheese.datatype))
        nocheese_sub_layer = int(self.parse_value(self.options.no_cheese.datatype))

        for chip_name in self.chip_info:
            layers_in_chip = self.design.qgeometry.get_all_unique_layers(chip_name)

            for chip_layer in layers_in_chip:
                code = self._check_cheese(chip_name, chip_layer)
                if code == 1:
                    chip_box, status = self.design.get_x_y_for_chip(chip_name)
                    if status == 0:
                        minx, miny, maxx, maxy = chip_box

                        self._cheese_based_on_shape(
                            minx,
                            miny,
                            maxx,
                            maxy,
                            chip_name,
                            chip_layer,
                            cheese_sub_layer,
                            nocheese_sub_layer,
                        )

    def _cheese_based_on_shape(
        self,
        minx: float,
        miny: float,
        maxx: float,
        maxy: float,
        chip_name: str,
        chip_layer: int,
        cheese_sub_layer: int,
        nocheese_sub_layer: int,
    ):
        """Instantiate class to do cheesing.

        Args:
            minx (float): Chip minimum x location.
            miny (float): Chip minimum y location.
            maxx (float): Chip maximum x location.
            maxy (float): chip maximum y location.
            chip_name (str): User defined chip name.
            layer (int): Layer number for calculating the cheese.
            cheese_sub_layer (int):  User defined datatype, considered a
                    sub-layer number for where to place the cheese output.
            nocheese_sub_layer (int): User defined datatype, considered a
                    sub-layer number for where to place the NO_cheese output.
        """
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-arguments

        max_points = int(self.parse_value(self.options.max_points))
        cheese_shape = int(self.parse_value(self.options.cheese.shape))
        all_nocheese = self.chip_info[chip_name][chip_layer]["no_cheese"]
        all_nocheese_gds = self.chip_info[chip_name][chip_layer]["no_cheese_gds"]
        delta_x = float(self.parse_value(self.options.cheese.delta_x))
        delta_y = float(self.parse_value(self.options.cheese.delta_y))
        edge_nocheese = float(self.parse_value(self.options.cheese.edge_nocheese))
        precision = float(self.parse_value(self.options.precision))
        is_neg_mask = self._is_negative_mask(chip_name, chip_layer)
        fab = is_true(self.options.fabricate)

        # =====================================================================
        # --- CUSTOM DICTIONARY LOGIC FOR CHEESE LAYER ---
        # =====================================================================
        pkg_dict = self.options.get('packaging_dict', {})
        target_cheese_layer = chip_layer # Default to normal layer
        
        # Override with dictionary if it exists
        if chip_name in pkg_dict and 'cheese' in pkg_dict[chip_name]:
            target_cheese_layer = pkg_dict[chip_name]['cheese']
        # =====================================================================

        if cheese_shape == 0:
            cheese_x = float(self.parse_value(self.options.cheese.cheese_0_x))
            cheese_y = float(self.parse_value(self.options.cheese.cheese_0_y))
            a_cheese = Cheesing(
                all_nocheese,
                all_nocheese_gds,
                self.lib,
                minx,
                miny,
                maxx,
                maxy,
                chip_name,
                edge_nocheese,
                chip_layer,           # <-- REVERTED TO chip_layer! Keeps make_cheese.py happy!
                is_neg_mask,
                cheese_sub_layer,
                nocheese_sub_layer,
                fab,
                self.logger,
                max_points,
                precision,
                cheese_shape=cheese_shape,
                shape_0_x=cheese_x,
                shape_0_y=cheese_y,
                delta_x=delta_x,
                delta_y=delta_y,
            )
        elif cheese_shape == 1:
            cheese_radius = float(self.parse_value(self.options.cheese.cheese_1_radius))
            a_cheese = Cheesing(
                all_nocheese,
                all_nocheese_gds,
                self.lib,
                minx,
                miny,
                maxx,
                maxy,
                chip_name,
                edge_nocheese,
                chip_layer,           # <-- REVERTED TO chip_layer! Keeps make_cheese.py happy!
                is_neg_mask,
                cheese_sub_layer,
                nocheese_sub_layer,
                fab,
                self.logger,
                max_points,
                precision,
                cheese_shape=cheese_shape,
                shape_1_radius=cheese_radius,
                delta_x=delta_x,
                delta_y=delta_y,
            )
        else:
            self.logger.warning(
                f"The cheese_shape={cheese_shape} is unknown in MyGDSRenderer."
            )
            a_cheese = None

        if a_cheese is not None:
            # Let the original engine do all the math without crashing
            _dummy_a_lib = a_cheese.apply_cheesing()

            # =====================================================================
            # --- POST-PROCESS: MOVE CHEESE TO TARGET LAYER ---
            # =====================================================================
            # Once it's successfully generated, sweep the library and remap the layer!
            if target_cheese_layer != chip_layer:
                for cell in self.lib.cells:
                    for poly in cell.polygons:
                        if poly.datatype == cheese_sub_layer and poly.layer == chip_layer:
                            poly.layer = target_cheese_layer
            # =====================================================================
    def _populate_no_cheese(self):
        """Iterate through every chip and layer.  If options choose to have
        either cheese or no-cheese, a MultiPolygon is placed
        self.chip_info[chip_name][chip_layer]['no_cheese'].
        """
        # pylint: disable=too-many-nested-blocks

        no_cheese_buffer = float(self.parse_value(self.options.no_cheese.buffer))
        sub_layer = int(self.parse_value(self.options.no_cheese.datatype))
        lib = self.lib
        fab = is_true(self.options.fabricate)
        
        # =====================================================================
        # --- FETCH THE DICTIONARY ---
        # =====================================================================
        pkg_dict = self.options.get('packaging_dict', {})

        for chip_name, _ in self.chip_info.items():
            layers_in_chip = self.design.qgeometry.get_all_unique_layers(chip_name)

            for chip_layer in layers_in_chip:
                code = self._check_either_cheese(chip_name, chip_layer)
                
                # =====================================================================
                # --- APPLY CUSTOM DICTIONARY LOGIC FOR NO_CHEESE LAYER ---
                # =====================================================================
                target_nocheese_layer = chip_layer
                if chip_name in pkg_dict and 'no_cheese' in pkg_dict[chip_name]:
                    target_nocheese_layer = pkg_dict[chip_name]['no_cheese']
                # =====================================================================

                if code in (1, 2, 3):
                    if (
                        len(self.chip_info[chip_name][chip_layer]["all_subtract_true"])
                        != 0
                    ):
                        sub_df = self.chip_info[chip_name][chip_layer][
                            "all_subtract_true"
                        ]
                        no_cheese_multipolygon = self._cheese_buffer_maker(
                            sub_df, chip_name, no_cheese_buffer
                        )
                        if no_cheese_multipolygon is not None:
                            self.chip_info[chip_name][chip_layer]["no_cheese"] = (
                                no_cheese_multipolygon
                            )
                            
                            # --- PASS THE TARGET LAYER INTO THE GDS TRANSLATOR ---
                            all_nocheese_gds = self._multipolygon_to_gds(
                                no_cheese_multipolygon,
                                target_nocheese_layer,  # <-- CHANGED FROM chip_layer
                                sub_layer,
                                no_cheese_buffer,
                            )
                            self.chip_info[chip_name][chip_layer]["no_cheese_gds"] = (
                                all_nocheese_gds
                            )

                            if (
                                self._check_no_cheese(chip_name, chip_layer) == 1
                                and not fab
                            ):
                                # --- UPDATE THE CELL NAME TO REFLECT THE NEW LAYER ---
                                no_cheese_subtract_cell_name = (
                                    f"TOP_{chip_name}_{target_nocheese_layer}_NoCheese_{sub_layer}" 
                                )
                                no_cheese_cell = lib.new_cell(
                                    no_cheese_subtract_cell_name
                                )
                                for poly_el in all_nocheese_gds:
                                    if isinstance(poly_el, list):
                                        for sub_poly in poly_el:
                                            no_cheese_cell.add(sub_poly)
                                    else:
                                        no_cheese_cell.add(poly_el)

                                chip_only_top_name = f"TOP_{chip_name}"
                                chip_only_top = next(
                                    (
                                        c
                                        for c in lib.cells
                                        if c.name == chip_only_top_name
                                    ),
                                    None,
                                )
                                if (
                                    chip_only_top
                                    and no_cheese_cell.bounding_box() is not None
                                ):
                                    chip_only_top.add(gdstk.Reference(no_cheese_cell))
                                else:
                                    lib.remove(no_cheese_cell)
    def _cheese_buffer_maker(
        self, sub_df: geopandas.GeoDataFrame, chip_name: str, no_cheese_buffer: float
    ) -> Union[None, shapely.geometry.multipolygon.MultiPolygon]:
        """For each layer in each chip, and if it has a ground plane
        (subtract==True), determine the no-cheese buffer and return a shapely
        object. Before the buffer is created for no-cheese, the LineStrings and
        Polygons are all combined.

        Args:
            sub_df (geopandas.GeoDataFrame): The subset of QGeometry tables
                for each chip, and layer, and only if the layer has a ground plane.
            chip_name (str): Name of chip.
            no_cheese_buffer (float): Will be used for fillet and
                size of buffer.

        Returns:
            Union[None, shapely.geometry.multipolygon.MultiPolygon]: The
            shapely which combines the polygons and linestrings and creates
            buffer as specified through default_options.
        """
        # pylint: disable=too-many-locals
        style_cap = int(self.parse_value(self.options.no_cheese.cap_style))
        style_join = int(self.parse_value(self.options.no_cheese.join_style))

        poly_sub_df = sub_df[
            sub_df.geometry.apply(
                lambda x: isinstance(x, shapely.geometry.polygon.Polygon)
            )
        ]
        poly_sub_geo = poly_sub_df["geometry"].tolist()

        path_sub_df = sub_df[
            sub_df.geometry.apply(
                lambda x: isinstance(x, shapely.geometry.linestring.LineString)
            )
        ]
        path_sub_geo = path_sub_df["geometry"].tolist()
        path_sub_width = path_sub_df["width"].tolist()
        # for n in range(len(path_sub_geo)):
        for index, _ in enumerate(path_sub_geo):
            path_sub_geo[index] = path_sub_geo[index].buffer(
                path_sub_width[index] / 2, cap_style=style_cap, join_style=style_join
            )

        #  Need to add buffer_size, cap style, and join style to default options
        combo_list = path_sub_geo + poly_sub_geo
        combo_shapely = draw.union(combo_list)

        if not combo_shapely.is_empty:
            # Can return either Multipolygon or just one polygon.
            combo_shapely = combo_shapely.buffer(
                no_cheese_buffer, cap_style=style_cap, join_style=style_join
            )
            if isinstance(combo_shapely, shapely.geometry.polygon.Polygon):
                combo_shapely = shapely.geometry.MultiPolygon([combo_shapely])

            # Check if the buffer went past the chip size.
            chip_box, status = self.design.get_x_y_for_chip(chip_name)
            if status == 0:
                minx, miny, maxx, maxy = chip_box
                c_minx, c_miny, c_maxx, c_maxy = combo_shapely.bounds
                if c_minx < minx or c_miny < miny or c_maxx > maxx or c_maxy > maxy:
                    self.logger.warning(
                        f"The bounding box for no-cheese is outside of chip size.\n"
                        f"Bounding box for chip is {chip_box}.\n"
                        f"Bounding box with no_cheese buffer is {combo_shapely.bounds}."
                    )
            else:
                self.logger.warning(
                    f"design.get_x_y_for_chip() did NOT return a good code for chip={chip_name},"
                    f"for _cheese_buffer_maker.  The chip boundary will not be tested."
                )

            # The type of combo_shapely will be
            # <class 'shapely.geometry.multipolygon.MultiPolygon'>
            return combo_shapely
        return None  # Need explicitly to avoid lint warnings.

    def _get_rectangle_points(self, chip_name: str) -> Tuple[list, list]:
        """There can be more than one chip in QGeometry. All chips export to
        one gds file. Each chip uses its own subtract rectangle.

        Args:
            chip_name (str): Name of chip to render.

        Returns:
            Tuple[list, list]: The subtract-rectangle for the chip_name.
        """
        layers_in_chip = self.design.qgeometry.get_all_unique_layers(chip_name)

        minx, miny, maxx, maxy = self.dict_bounds[chip_name]["for_subtract"]
        rectangle_points = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]

        return layers_in_chip, rectangle_points

    def _populate_poly_path_for_export(self):
        """Using the geometries for each table name in QGeometry, populate
        self.lib to eventually write to a GDS file.

        For every layer within a chip, use the same "subtraction box" for the
        elements that have subtract as true.  Every layer within a chip will
        have a construction cell named ``TOP_<chip>_<layer>``. When
        ``semantic_hierarchy`` is enabled, those internal layer cells are later
        wrapped under ``<chip>__GROUND`` and only semantic/package cells remain
        directly visible from the final exported ``TOP``.

        Args:
            file_name (str): The path and file name to write the gds file.
                             Name needs to include desired extension,
                             i.e. "a_path_and_name.gds".
        """

        precision = float(self.parse_value(self.options.precision))

        lib = self.new_gds_library()

        if is_true(self.options.ground_plane):
            all_chips_top_name = "TOP"
            all_chips_top = lib.new_cell(all_chips_top_name)
            for chip_name, _ in self.chip_info.items():
                chip_only_top_name = f"TOP_{chip_name}"
                chip_only_top = lib.new_cell(chip_only_top_name)

                layers_in_chip, rectangle_points = self._get_rectangle_points(chip_name)

                for chip_layer in layers_in_chip:
                    self._handle_photo_resist(
                        lib,
                        chip_only_top,
                        chip_name,
                        chip_layer,
                        rectangle_points,
                        precision,
                    )

                self._populate_semantic_qgeometry(lib, chip_name)

                # If junction table, import the cell and cell to chip_only_top
                if "junction" in self.chip_info[chip_name]:
                    self._import_junctions_to_one_cell(
                        chip_name, lib, chip_only_top, layers_in_chip
                    )

                # put all chips into TOP
                if chip_only_top.bounding_box() is not None:
                    all_chips_top.add(gdstk.Reference(chip_only_top))
                else:
                    lib.remove(chip_only_top)

            if not self._use_semantic_hierarchy():
                self._add_semantic_cells_to_top(all_chips_top)

    def _handle_photo_resist(
        self,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        chip_name: str,
        chip_layer: int,
        rectangle_points: list,
        precision: float,
    ):
        """Handle the positive vs negative mask.

        Args:
            lib (gdstk.Library): The GDS library to export.
            chip_only_top (gdstk.Cell): The GDS  cell for top.
            chip_name (str): Name of chip to render.
            chip_layer (int): Layer of the chip to render.
            rectangle_points (list): The rectangle to denote the ground
                                    for each layer.
            precision (float): Used for GDS python export.
        """

        self.chip_info[chip_name]["subtract_poly"] = gdstk.Polygon(
            rectangle_points, layer=chip_layer, datatype=10
        )

        ground_cell_name = f"TOP_{chip_name}_{chip_layer}"
        ground_cell = lib.new_cell(ground_cell_name)

        if self._is_negative_mask(chip_name, chip_layer):
            self._negative_mask(
                lib,
                chip_only_top,
                ground_cell,
                chip_name,
                chip_layer,
                precision,
            )
        else:
            self._positive_mask(
                lib,
                chip_only_top,
                ground_cell,
                chip_name,
                chip_layer,
                precision,
            )

    def _is_negative_mask(self, chip: str, layer: int) -> bool:
        """Check options to see if negative mask is requested for the
        chip and layer.

        Args:
            chip (str): Chip name to search for in options.
            layer (int): Layer to search for within chip.  Determine if this
                         layer should have negative mask.

        Returns:
            bool: If there should be a negative mask for this chip and layer.
        """
        if chip in self.options.negative_mask.keys():
            if layer in self.options.negative_mask[chip]:
                return True

        return False

    def _negative_mask(
        self,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        ground_cell: gdstk.Cell,
        chip_name: str,
        chip_layer: int,
        precision: float,
    ):
        """Apply logic for negative_mask.

        Args:
            lib (gdstk.Library): GDS library.
            chip_only_top (gdstk.Cell): The chip's top cell.
            ground_cell (gdstk.Cell): The ground cell for this layer.
            chip_name (str): Name of chip to render.
            chip_layer (int): Layer of the chip to render.
            precision (float):  GDS geometry precision.
        """
        if len(self.chip_info[chip_name][chip_layer]["q_subtract_true"]) != 0:
            # Difference for True-False.
            diff_geometry = gdstk.boolean(
                self.chip_info[chip_name][chip_layer]["q_subtract_true"],
                self.chip_info[chip_name][chip_layer]["q_subtract_false"],
                "not",
                layer=chip_layer,
                precision=precision,
            )

            if diff_geometry is None:
                self.design.logger.warning(
                    "There is no table named diff_geometry to write."
                )
            else:
                ground_cell.add(*diff_geometry)

        MyGDSRenderer._add_groundcell_to_chip_only_top(lib, chip_only_top, ground_cell)

    def _positive_mask(
        self,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        ground_cell: gdstk.Cell,
        chip_name: str,
        chip_layer: int,
        precision: float,
    ):
        """Apply logic for positive mask for a chip to render.

        Args:
            lib (gdstk.Library): GDS library.
            chip_only_top (gdstk.Cell): The chip's top cell.
            ground_cell (gdstk.Cell): The ground cell for this layer.
            chip_name (str): Chip name.
            chip_layer (int): Layer index.
            precision (float): GDS geometry precision.
        """
        # Fetch the custom dictionary from options
        pkg_dict = self.options.get('packaging_dict', {})
        
        # Default target layer is the standard chip layer, UNLESS it is 
        # specifically overridden by your dictionary
        target_layer = chip_layer 
        if chip_name in pkg_dict and 'ground' in pkg_dict[chip_name]:
            target_layer = pkg_dict[chip_name]['ground']
        
        if len(self.chip_info[chip_name][chip_layer]["q_subtract_true"]) != 0:
            # Convert any complex FlexPaths to flat polygons to prevent gdstk C++ crashes
            safe_subtracts = []
            for geom in self.chip_info[chip_name][chip_layer]["q_subtract_true"]:
                if isinstance(geom, (gdstk.FlexPath, gdstk.RobustPath)):
                    safe_subtracts.extend(geom.to_polygons())
                else:
                    safe_subtracts.append(geom)
            diff_geometry = gdstk.boolean(
                [self.chip_info[chip_name]["subtract_poly"]],
                safe_subtracts,      # <-- ONLY safe_subtracts should be here
                "not",
                layer=target_layer,  
                datatype=0,          
                precision=precision,
            )

            if diff_geometry is None:
                self.design.logger.warning(
                    "There is no table named diff_geometry to write."
                )
            else:
                ground_plane_cell_name = f"ground_{chip_name}_{chip_layer}"
                ground_plane_cell = lib.new_cell(ground_plane_cell_name)
                ground_plane_cell.add(*diff_geometry)
                ground_cell.add(gdstk.Reference(ground_plane_cell))

        MyGDSRenderer._add_groundcell_to_chip_only_top(lib, chip_only_top, ground_cell)

    def _handle_q_subtract_false(
        self, chip_name: str, chip_layer: int, ground_cell: gdstk.Cell
    ):
        """Retained for compatibility with the historical ground-cell flow.

        Args:
            chip_name (str): Name of chip to render.
            chip_layer (int): Name of layer to render.
            ground_cell (gdstk.Cell): The cell in lib to add to.
                                            Cell created for each layer.
        """
        if self.chip_info[chip_name][chip_layer]["q_subtract_false"] is None:
            self.logger.warning(
                f"There is no table named "
                f"self.chip_info[{chip_name}][q_subtract_false]"
                f" to write."
            )
        else:
            if len(self.chip_info[chip_name][chip_layer]["q_subtract_false"]) != 0:
                ground_cell.add(
                    *self.chip_info[chip_name][chip_layer]["q_subtract_false"]
                )

    @classmethod
    def _add_groundcell_to_chip_only_top(
        cls, lib: gdstk.Library, chip_only_top: gdstk.Cell, ground_cell: gdstk.Cell
    ) -> None:
        """Add the ground cell to the top of cell for chip.

        Args:
            lib (gdstk.GdsLibrary): Holds all of the chips to export to gds.
            chip_only_top (gdstk.Cell): Cell which for a single chip.
            ground_cell (gdstk.Cell): The ground cell to add to
                                    chip_only_top. Cell created for each layer.
        """
        # put all cells into TOP_chipname, if not empty.
        # When checking for bounding box, gdstk will return None if empty.

        if ground_cell.bounding_box() is not None:
            chip_only_top.add(gdstk.Reference(ground_cell))
        else:
            lib.remove(ground_cell)

    def _get_linestring_characteristics(
        self, row: pd.Series
    ) -> Tuple[Tuple, float, float]:
        """Given a row in the Junction table, give the characteristics of
        LineString in row.geometry.

        Args:
            row (pd.Pandas): A row from Junction table of QGeometry.

        Returns:
            Tuple:
            * 1st entry is Tuple[float,float]: The midpoint of Linestring from
            row.geometry in format (x,y).
            * 2nd entry is float: The angle in degrees of Linestring from
            row.geometry.
            * 3rd entry is float: Is the magnitude of Linestring from
            row.geometry.
        """
        precision = float(self.parse_value(self.options.precision))
        for_rounding = int(np.abs(np.log10(precision)))

        [(minx, miny), (maxx, maxy)] = row.geometry.coords[:]

        center = MyGDSRenderer._midpoint_xy(minx, miny, maxx, maxy)
        rotation = math.degrees(math.atan2((maxy - miny), (maxx - minx)))
        magnitude = np.round(
            distance.euclidean(row.geometry.coords[0], row.geometry.coords[1]),
            for_rounding,
        )

        return center, rotation, magnitude

    def _give_rotation_center_twopads(
        self, row: pd.Series, a_cell_bounding_box: np.ndarray
    ) -> Tuple[
        float,
        Tuple[float, float],
        Union[gdstk.Polygon, None],
        Union[gdstk.Polygon, None],
    ]:
        """Calculate the angle for rotation, center of LineString in
        row.geometry, and if needed create two pads to connect the junction to
        qubit.

        Args:
            row (pd.Pandas): A row from Junction table of QGeometry.
            a_cell_bounding_box (numpy.ndarray): Give the bounding box of cell
                used in row.gds_cell_name.

        Returns:
            Tuple:
            * 1st entry is float: The angle in degrees of Linestring from
            row.geometry.
            * 2nd entry is Tuple[float,float]: The midpoint of Linestring
            from row.geometry in format (x,y).
            * 3rd entry is gdstk.Rectangle: None if Magnitude of
            LineString is smaller than width of cell from row.gds_cell_name.
            Otherwise the rectangle for pad on LEFT of row.gds_cell_name.
            * 4th entry is gdstk.Rectangle: None if Magnitude of
            LineString is smaller than width of cell from row.gds_cell_name.
            Otherwise the rectangle for pad on RIGHT of row.gds_cell_name.
        """
        # pylint: disable=too-many-locals
        junction_pad_overlap = float(
            self.parse_value(self.options.junction_pad_overlap)
        )

        pad_height = row.width
        center, rotation, magnitude = self._get_linestring_characteristics(row)
        [(jj_minx, jj_miny), (jj_maxx, jj_maxy)] = a_cell_bounding_box[0:2]

        pad_left = None
        pad_right = None
        jj_x_width = abs(jj_maxx - jj_minx)
        jj_y_height = abs(jj_maxy - jj_miny)

        # jj_center_x = (jj_x_width / 2) + jj_minx
        jj_center_y = (jj_y_height / 2) + jj_miny

        pad_height = row.width

        if pad_height < jj_y_height:
            # pylint: disable=protected-access
            text_id = self.design._components[row.component]._name
            self.logger.warning(
                f"In junction table, component={text_id} with name={row.name} "
                f"has width={pad_height} smaller than cell dimension={jj_y_height}."
            )

        if jj_x_width < magnitude:
            pad_x_size_minus_overlap = (magnitude - jj_x_width) / 2
            pad_miny = jj_center_y - (pad_height / 2)
            pad_left = gdstk.Polygon(
                [
                    (jj_minx - pad_x_size_minus_overlap, pad_miny),
                    (jj_minx + junction_pad_overlap, pad_miny),
                    (jj_minx + junction_pad_overlap, pad_miny + pad_height),
                    (jj_minx - pad_x_size_minus_overlap, pad_miny + pad_height),
                ],
                layer=int(row.layer),
                datatype=10,
            )
            pad_right = gdstk.Polygon(
                [
                    (jj_maxx - junction_pad_overlap, pad_miny),
                    (jj_maxx + pad_x_size_minus_overlap, pad_miny),
                    (jj_maxx + pad_x_size_minus_overlap, pad_miny + pad_height),
                    (jj_maxx - junction_pad_overlap, pad_miny + pad_height),
                ],
                layer=int(row.layer),
                datatype=10,
            )

        return rotation, center, pad_left, pad_right

    ############

    def import_junction_gds_file(
        self, lib: gdstk.Library, directory_name: Optional[str] = None
    ) -> bool:
        """Import the file which contains all junctions for design.

        If the file has already been imported, just return True.

        When the design has junctions on multiple chips,
        we only need to import the file once to get all of the junction cells.

        Args:
            lib: Main GDS library used by this renderer.
            directory_name: Directory path where the junction GDS file is expected.

        Returns:
            True if the file was imported (or was already imported), False otherwise.
        """

        if self.imported_junction_gds is None:  # auto get dir name
            if self.options.path_filename is None or self.options.path_filename == "":
                self.logger.warning(
                    "No path_filename specified for junction GDS import."
                )
                return False
            else:
                _, directory_name = can_write_to_path(self.options.path_filename)

        # TODO: Validate this works as intended with new gdstk.read_gds
        # already imported once in this renderer
        if self.imported_junction_gds is not None:
            return True

        if not os.path.isfile(self.options.path_filename):
            message_str = (
                f'Not able to find file:"{self.options.path_filename}".  '
                f"Not used to replace junction."
                f' Checked directory:"{directory_name}".'
            )
            self.logger.warning(message_str)
            return False

        # read external library (with its own unit/precision)
        imported_lib = gdstk.read_gds(self.options.path_filename)
        imported_cells = getattr(imported_lib, "cells", None)

        if not imported_cells:
            message_str = (
                f'Imported file "{self.options.path_filename}" contains no cells.  '
                "Not used to replace junction."
            )
            self.logger.warning(message_str)
            return False

        # replicate old gdspy `units="convert"` behavior:
        # # rescale imported cells so their physical size matches this renderer's lib.
        # # coord_target = coord_imported * (imported_lib.unit / lib.unit)
        # scale = imported_lib.unit / lib.unit

        # # only do work if there is a real difference
        # if not math.isclose(scale, 1.0, rel_tol=1e-12, abs_tol=0.0):
        #     self.logger.info(
        #         "Rescaling imported junction library from unit=%g to unit=%g "
        #         "(scale factor=%g).",
        #         imported_lib.unit,
        #         lib.unit,
        #         scale,
        #     )
        #     for cell in imported_cells:
        #         # scale in-place; affects polygons, paths, labels, references
        #         cell.scale(scale, scale)

        # merge imported cells into main library, like old lib.read_gds did
        for cell in imported_cells:
            lib.add(cell)

        self.imported_junction_gds = self.options.path_filename
        return True

    def _import_junctions_to_one_cell(
        self,
        chip_name: str,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        layers_in_chip: list,
    ):
        """Given lib, import the gds file from default options.  Based on the
        cell name in QGeometry table, import the cell from the gds file and
        place junction instances into their semantic cells. For negative-mask
        layers, extension pads are still applied against the chip/layer cell.
        The linestring should be two vertexes, and denotes two things.
        1. The midpoint of
        segment is the the center of cell.

        2. The angle made by second tuple - fist tuple  for delta y/ delta x
        is used to rotate the cell.

        Args:
            chip_name (str): The name of chip.
            lib (gdstk.Library): The library used to export the entire QDesign.
            chip_only_top (gdstk.Cell): The cell used for
                                                just chip_name.
            layers_in_chip (list):  List of all layers in chip.
        """
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-nested-blocks

        # Make sure the file exists, before trying to read it.
        _, directory_name = can_write_to_path(self.options.path_filename)
        layers_in_junction_table = set(self.chip_info[chip_name]["junction"]["layer"])

        if self.import_junction_gds_file(lib=lib, directory_name=directory_name):
            for row in self.chip_info[chip_name]["junction"].itertuples():
                if row.gds_cell_name in [c.name for c in lib.cells]:
                    semantic_cell = self._get_or_create_semantic_cell(lib, row)
                    if semantic_cell is not None:
                        self._add_positive_extension_to_jj(lib, row, semantic_cell)
                        self._register_semantic_metadata(semantic_cell.name, row)
                else:
                    self.logger.warning(
                        f"Cell={row.gds_cell_name} from junction"
                        f"table not found in {self.options.path_filename}."
                    )

            for iter_layer in layers_in_chip:
                if self._is_negative_mask(chip_name, iter_layer):
                    # Want to export negative mask
                    # Gather the pads into hold_all_pads_cell for same layer.
                    if iter_layer in layers_in_junction_table:
                        chip_only_top_layer_name = f"TOP_{chip_name}_{iter_layer}"
                        top_layer_cell = next(
                            (
                                c
                                for c in lib.cells
                                if c.name == chip_only_top_layer_name
                            ),
                            None,
                        )
                        if top_layer_cell:
                            hold_all_pads_cell = lib.new_cell(
                                f"r_l_hold_all_pads_{iter_layer}"
                            )
                            top_layer_cell.add(gdstk.Reference(hold_all_pads_cell))

                            self._add_negative_extension_to_jj(
                                chip_name,
                                iter_layer,
                                lib,
                                chip_only_top,
                                top_layer_cell,
                                hold_all_pads_cell,
                            )

    def _add_negative_extension_to_jj(
        self,
        chip_name: str,
        jj_layer: int,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        chip_only_top_layer: gdstk.Cell,
        hold_all_pads_cell: gdstk.Cell,
    ) -> None:
        """Gather extension pads for negative mask junction handling.
        Manipulate existing geometries for the layer that the junctions need
         to be added.  Since boolean subtraction is computationally intensive,
         the method will gather the pads for a layer, and do the boolean just
         once.

        Args:
            chip_name (str): Chip name.
            jj_layer (int): Layer index for junction.
            lib (gdstk.Library): GDS library.
            chip_only_top (gdstk.Cell): Chip top cell.
            chip_only_top_layer (gdstk.Cell): Chip/layer cell.
            hold_all_pads_cell (gdstk.Cell): Cell collecting extension pads.
        """
        boolean_by_layer = self.chip_info[chip_name]["junction"]["layer"] == jj_layer
        for row in self.chip_info[chip_name]["junction"][boolean_by_layer].itertuples():
            if row.gds_cell_name in [c.name for c in lib.cells]:
                self._gather_negative_extension_for_jj(lib, row, hold_all_pads_cell)
            else:
                self.logger.warning(
                    f"Junction cell={row.gds_cell_name} not "
                    f"n {self.options.path_filename} for negative "
                    "mask usage."
                )

        diff_r_l_pads_name = f"r_l_pads_diff_{jj_layer}"
        diff_pad_cell_layer = lib.new_cell(diff_r_l_pads_name)
        chip_only_top.add(gdstk.Reference(diff_pad_cell_layer))

        precision = float(self.parse_value(self.options.precision))

        if chip_only_top_layer.bounding_box() is not None:
            boolean_result = gdstk.boolean(
                chip_only_top_layer.get_polygons(),
                hold_all_pads_cell.get_polygons(),
                "not",
                precision=precision,
            )
            if boolean_result:
                for poly in boolean_result:
                    diff_pad_cell_layer.add(poly)

        self._clean_hierarchy(
            lib,
            chip_only_top,
            chip_only_top_layer,
            diff_pad_cell_layer,
            hold_all_pads_cell,
        )

    @classmethod
    def _clean_hierarchy(
        cls,
        lib: gdstk.Library,
        chip_only_top: gdstk.Cell,
        chip_only_top_layer: gdstk.Cell,
        diff_pad_cell_layer: gdstk.Cell,
        hold_all_pads_cell: gdstk.Cell,
    ) -> None:
        """Delete cell that doesn't have pad nor jjs.  Then use same
        name for correct cell.  Also, get rid of cell that had the pads
        since subtraction happened and we don't need it any more.

        Args:
            lib (gdstk.Library): [The library used to export the entire QDesign.
            chip_only_top (gdstk.Cell): [description]
            chip_only_top_layer (gdstk.Cell): Cell under chip,
                                        with specific layer.
            diff_pad_cell_layer (gdstk.Cell): Holds result of top_layer - pads + jjs.
            hold_all_pads_cell (gdstk.Cell): Collect all the jj's with movement.
        """
        hold_name = chip_only_top_layer.name
        lib.remove(chip_only_top_layer)
        lib.rename_cell(diff_pad_cell_layer, hold_name)

        if diff_pad_cell_layer.bounding_box() is not None:
            chip_only_top.add(gdstk.Reference(diff_pad_cell_layer))
        else:
            lib.remove(diff_pad_cell_layer)

        for ref in list(hold_all_pads_cell.references):
            ref_cell = self._get_reference_cell(ref)
            if ref_cell is not None:
                lib.remove(ref_cell)
        lib.remove(hold_all_pads_cell)

    def _gather_negative_extension_for_jj(
        self,
        lib: gdstk.Library,
        row: pd.Series,
        hold_all_pads_cell: gdstk.Cell,
    ) -> None:
        """Gather only the junction extension pads for negative mask usage.

        Args:
            lib (gdstk.Library): GDS library.
            row (pd.Series): Row from junction table.
            hold_all_pads_cell (gdstk.Cell): Collecting extension pads.
        """

        a_cell = next((c for c in lib.cells if c.name == row.gds_cell_name), None)
        if a_cell is None:
            return
        bounding_box = a_cell.bounding_box()
        if bounding_box is None:
            return

        rotation, center, pad_left, pad_right = self._give_rotation_center_twopads(
            row, bounding_box
        )
        jj_pad_r_l_name = (
            f"{row.gds_cell_name}_QComponent_is_{row.component}"
            f"_Name_is_{row.name}_name_is_{row.name}"
        )
        temp_cell = lib.new_cell(jj_pad_r_l_name)
        if pad_left is not None:
            temp_cell.add(pad_left)
        if pad_right is not None:
            temp_cell.add(pad_right)

        hold_all_pads_cell.add(
            gdstk.Reference(temp_cell, origin=center, rotation=rotation)
        )

    def _add_positive_extension_to_jj(
        self,
        lib: gdstk.Library,
        row: pd.Series,
        target_cell: gdstk.Cell,
    ):
        """Add a junction reference and its extension pads to a target cell.

        Args:
            lib (gdstk.Library): The library used to export the entire QDesign.
            row (pd.core.frame.Pandas): Each row is from the qgeometry
                                            junction table.
            target_cell (gdstk.Cell): Cell receiving the junction placement.
        """
        a_cell = next((c for c in lib.cells if c.name == row.gds_cell_name), None)
        if a_cell is None:
            return
        bounding_box = a_cell.bounding_box()
        if bounding_box is None:
            return

        rotation, center, pad_left, pad_right = self._give_rotation_center_twopads(
            row, bounding_box
        )
        jj_pad_r_l_name = (
            f"pads_{row.gds_cell_name}_QComponent_is_{row.component}_name_is_{row.name}"
        )
        temp_cell = lib.new_cell(jj_pad_r_l_name)

        if pad_left is not None:
            temp_cell.add(pad_left)
        if pad_right is not None:
            temp_cell.add(pad_right)

        target_cell.add(gdstk.Reference(a_cell, origin=center, rotation=rotation))
        if temp_cell.bounding_box() is not None:
            target_cell.add(
                gdstk.Reference(temp_cell, origin=center, rotation=rotation)
            )
        else:
            lib.remove(temp_cell)

    def _add_legacy_packaging_geometry(self, lib: gdstk.Library) -> None:
        """Preserve the historical direct-to-TOP packaging geometry flow."""
        pkg_dict = self.options.get("packaging_dict", {})
        if not pkg_dict:
            return

        top_cells = lib.top_level()
        main_cell = top_cells[0] if top_cells else lib.cells[0]

        global_minx, global_miny = float("inf"), float("inf")
        global_maxx, global_maxy = float("-inf"), float("-inf")

        for chip_name, bounds_dict in self.dict_bounds.items():
            if chip_name in pkg_dict and "substrate" in pkg_dict[chip_name]:
                minx, miny, maxx, maxy = bounds_dict["for_subtract"]

                global_minx = min(global_minx, minx)
                global_miny = min(global_miny, miny)
                global_maxx = max(global_maxx, maxx)
                global_maxy = max(global_maxy, maxy)

                sub_layer = pkg_dict[chip_name]["substrate"]
                main_cell.add(
                    gdstk.rectangle(
                        (minx, miny), (maxx, maxy), layer=sub_layer, datatype=0
                    )
                )

        if "global" in pkg_dict and "vacuum" in pkg_dict["global"]:
            if global_minx != float("inf"):
                vacuum_layer = pkg_dict["global"]["vacuum"]
                main_cell.add(
                    gdstk.rectangle(
                        (global_minx, global_miny),
                        (global_maxx, global_maxy),
                        layer=vacuum_layer,
                        datatype=0,
                    )
                )

    def export_to_gds(self, file_name: str, highlight_qcomponents: list = None) -> int:
        """Use the design which was used to initialize this class. The
        QGeometry element types of both "path" and "poly", will be used, to
        convert QGeometry to GDS formatted file.

        Args:
            file_name (str): File name which can also include directory path.
                             If the file exists, it will be overwritten.
            highlight_qcomponents (list): List of strings which denote
                                        the name of QComponents to render.
                                        If empty, render all components in design.

        Returns:
            int: 0=file_name can not be written, otherwise 1=file_name has been written
        """
        if highlight_qcomponents is None:
            highlight_qcomponents = []

        if not self._can_write_to_path(file_name):
            return 0

        # There can be more than one chip in QGeometry.
        # They all export to one gds file.
        # Each chip will hold the rectangle for subtract for each layer so:
        # chip_info[chip_name][subtract_box][(min_x,min_y,max_x,max_y)]
        # chip_info[chip_name][layer_number][all_subtract_elements]
        # chip_info[chip_name][layer_number][all_no_subtract_elements]
        self.chip_info.clear()
        self.chip_info.update(self._get_chip_names())
        self.semantic_cells.clear()
        self.semantic_cell_details.clear()
        self.semantic_metadata.clear()
        self._plain_package_name_collision_warned = False
        self._semantic_name_collision_warnings.clear()

        # if imported, hold the path to file name, otherwise None.
        self.imported_junction_gds = None

        max_points = int(self.parse_value(self.options.max_points))

        if self._create_qgeometry_for_gds(highlight_qcomponents) == 0:
            # Create self.lib and populate path and poly.
            self._populate_poly_path_for_export()

            # Add no-cheese MultiPolygon to
            # self.chip_info[chip_name][chip_layer]['no_cheese'],
            # if self.options requests the layer.
            self._populate_no_cheese()

            # Use self.options  to decide what to put for export
            # into self.chip_info[chip_name][chip_layer]['cheese'].
            # Not finished.
            self._populate_cheese()
            if self._use_semantic_hierarchy():
                self._build_semantic_chip_package_hierarchy(self.lib)
            else:
                self._add_legacy_packaging_geometry(self.lib)

            # Export the file to disk from self.lib
            self.lib.write_gds(file_name, max_points)
            self._export_semantic_metadata(file_name)
            self._export_naming_map_metadata(file_name)

            return 1

        return 0

    def _multipolygon_to_gds(
        self,
        multi_poly: shapely.geometry.multipolygon.MultiPolygon,
        layer: int,
        data_type: int,
        no_cheese_buffer: float,  # pylint: disable=unused-argument
    ) -> list:
        """Convert a shapely MultiPolygon to corresponding gdstk.

        Args:
            multi_poly (shapely.geometry.multipolygon.MultiPolygon): The
                                shapely geometry of no-cheese boundary.
            layer (int): The layer of the input multipolygon.
            data_type (int): Used as a "sub-layer" to place the no-cheese
                                gdstk output.
            no_cheese_buffer (float): Used for both fillet and buffer size.

        Returns:
            list: Each entry is converted to GDSII.
        """
        # pylint: disable=too-many-locals

        precision = float(self.parse_value(self.options.precision))

        all_polys = list(multi_poly.geoms)
        all_gds = list()

        for poly in all_polys:
            exterior_coords = list(poly.exterior.coords)
            exterior_poly = gdstk.Polygon(
                exterior_coords, layer=layer, datatype=data_type
            )

            if poly.interiors:
                holes = []
                for hole in poly.interiors:
                    hole_coords = list(hole.coords)
                    holes.append(
                        gdstk.Polygon(hole_coords, layer=layer, datatype=data_type)
                    )

                diff_result = gdstk.boolean(
                    [exterior_poly],
                    holes,
                    "not",
                    layer=layer,
                    datatype=data_type,
                    precision=precision,
                )
                # Poly fracturing leading to a funny shape. Leave this out of gds output for now.
                # a_poly.fillet(no_cheese_buffer,
                #               points_per_2pi=128,
                #               precision=precision)
                all_gds.append(diff_result)
            else:
                # Poly fracturing leading to a funny shape. Leave this out of gds output for now.
                # exterior_poly.fillet(no_cheese_buffer,
                #                      points_per_2pi=128,
                #                      precision=precision)
                all_gds.append(exterior_poly)

        return all_gds

    def _qgeometry_to_gds(
        self, qgeometry_element: pd.Series
    ) -> Union[gdstk.Polygon, gdstk.FlexPath, None]:
        """Convert the design.qgeometry table to format used by GDS renderer.
        Convert the class to a series of GDSII elements.

        Args:
            qgeometry_element (pd.Series): Expect a shapely object.

        Returns:
            Union['gdstk.Polygon' or 'gdstk.FlexPath' or None]: Convert the
            class to a series of GDSII format on the input pd.Series.


        *NOTE:*
        GDS:
            points (array-like[N][2]) – Coordinates of the vertices of
                                        the polygon.
            layer (integer) – The GDSII layer number for this
                                        qgeometry_element.
            datatype (integer) – The GDSII datatype for this qgeometry_element
                                (between 0 and 255).
                                datatype=10 or 11 means only that they are
                                from a Polygon vs. LineString.
                                This can be changed.

        See:
            https://heitzmann.github.io/gdstk/geometry/gdstk.Polygon.html
        """

        corners = self.options.corners
        precision = self.parse_value(self.options.precision)
        tolerance = self.parse_value(self.options.tolerance)

        geom = qgeometry_element.geometry
        layer_num = int(qgeometry_element.layer)

        if isinstance(geom, shapely.geometry.Polygon):
            exterior_coords = list(geom.exterior.coords)
            exterior_poly = gdstk.Polygon(
                exterior_coords,
                layer=layer_num,
                datatype=0,
            )

            # Handle holes
            if geom.interiors:
                holes = []
                for hole in geom.interiors:
                    hole_coords = list(hole.coords)
                    holes.append(
                        gdstk.Polygon(hole_coords, layer=layer_num, datatype=0)
                    )
                result = gdstk.boolean(
                    [exterior_poly],
                    holes,
                    "not",
                    layer=layer_num,
                    datatype=0,
                    precision=float(precision),
                )
                if len(result) != 1:
                    self.logger.warning(
                        "Some elements are not inside the geometry; these are invalid holes."
                    )
                return result[0]
            return exterior_poly

        if isinstance(geom, shapely.geometry.LineString):
            if not math.isnan(qgeometry_element.width):
                use_width = qgeometry_element.width
            else:
                use_width = self.parse_value(self.options.width_LineString)
                qcomponent_id = self.parse_value(qgeometry_element.component)
                name = self.parse_value(qgeometry_element["name"])
                layer_num = self.parse_value(qgeometry_element.layer)
                width = self.parse_value(qgeometry_element.width)
                self.logger.warning(
                    f"Since width:{width} for a Path is not a number, "
                    f"it will be exported using width_LineString:"
                    f" {use_width}.  The component_id is:{qcomponent_id},"
                    f" name is:{name}, layer is: {layer_num}"
                )

            if "fillet" in qgeometry_element:
                if (
                    math.isnan(qgeometry_element.fillet)
                    or qgeometry_element.fillet <= 0
                    or qgeometry_element.fillet < 0.5 * qgeometry_element.width
                ):
                    to_return = gdstk.FlexPath(
                        list(geom.coords),
                        use_width,
                        layer=layer_num,
                        datatype=0,
                        tolerance=tolerance,
                    )

                else:
                    to_return = gdstk.FlexPath(
                        list(geom.coords),
                        use_width,
                        layer=layer_num,
                        datatype=0,
                        joins=corners,
                        bend_radius=qgeometry_element.fillet,
                        tolerance=tolerance,
                    )

                return to_return

            # Could be junction table with a linestring.
            # Look for gds_path_filename in column.
            self.logger.warning(
                f"Linestring did not have fillet in column. "
                f"The qgeometry_element was not drawn.\n"
                f"The qgeometry_element within table is:\n"
                f"{qgeometry_element}"
            )
            return None  # Need explicitly to avoid lint warnings.

        self.logger.warning(
            f"Unexpected shapely object geometry."
            f"The variable qgeometry_element is {type(geom)}, "
            f"method can currently handle Polygon and FlexPath."
        )
        return None

    def _get_chip_names(self) -> Dict:
        """Returns a dict of unique chip names for ALL tables within QGeometry.
        In another words, for every "path" table, "poly" table ... etc, this
        method will search for unique chip names and return a dict of unique
        chip names from QGeometry table.

        Returns:
            Dict: dict with key of chip names and value of empty
            dict to hold things for renderers.
        """
        chip_names = Dict()
        for table_name in self.design.qgeometry.get_element_types():
            table = self.design.qgeometry.tables[table_name]
            names = table["chip"].unique().tolist()
            chip_names += names
        unique_list = list(set(chip_names))

        unique_dict = Dict()
        for chip in unique_list:
            unique_dict[chip] = Dict()
        return unique_dict

    def show_imported_junction_gds(self):
        r"""If junction gds file has been imported, show the cells in it.
        To use, you may need to first set:
        >>> gds.options.path_filename = "../resources/Fake_Junctions.GDS"
        This function will read the file again, and print out the cells in it.
        It will also render the cells as an SVG inline if run in a Jupyter notebook.
        """
        if self.imported_junction_gds is not None:
            imported_lib = gdstk.read_gds(self.imported_junction_gds)
            print("imported_lib name:", imported_lib.name)
            print("imported_lib unit:", imported_lib.unit)
            print("imported_lib precision:", imported_lib.precision)
            for cell in imported_lib.cells:
                self.debug_print_cell(cell, show=True)
        else:
            self.logger.info(
                "No junction gds file has been imported. \n"
                "You can set it with `gds.options.path_filename = ...`"
            )

    @staticmethod
    def debug_print_cell(cell, show=False):
        """Compact pretty-print summary of a gdstk Cell."""

        if show:
            cell.write_svg("test_output.svg")
            from IPython.display import SVG, display

            display(SVG("test_output.svg"))

        print(f"\n=== {cell.name} ===")

        # Bounding box
        try:
            bbox = cell.bounding_box()
        except Exception:
            bbox = None
        print(f"bbox: {bbox}")

        # Paths
        print("paths:", end=" ")
        if cell.paths:
            print(f"{len(cell.paths)}")
            for p in cell.paths:
                print(f"  - {p} (pts={len(p.points)})")
        else:
            print("0")

        # Polygons
        print("polygons:", end=" ")
        if cell.polygons:
            print(f"{len(cell.polygons)}")
            for poly in cell.polygons:
                print(f"  - poly(n={len(poly.points)})")
        else:
            print("0")

        # References
        print("refs:", end=" ")
        if cell.references:
            print(f"{len(cell.references)}")
            for r in cell.references:
                print(f"  - {r}")
        else:
            print("0")

        # Properties
        print("props:", end=" ")
        if cell.properties:
            print(f"{len(cell.properties)}")
            for obj, props in cell.properties.items():
                print(f"  - {obj}: {props}")
        else:
            print("0")

        print("=== end ===\n")

    def debug_print_final_hierarchy(self, max_depth: int = 3) -> None:
        """Print the final exported hierarchy rooted at ``TOP``.

        This helper is intended for semantic_hierarchy validation. It highlights
        direct TOP references so it is easy to verify that final output points
        only to ``ENV__VACUUM`` and ``CHIP__<chip>`` cells.
        """

        if self.lib is None:
            print("No active GDS library.")
            return

        top_cell = self._get_cell_by_name(self.lib, "TOP")
        if top_cell is None:
            print('Cell "TOP" was not found in the current library.')
            return

        def _walk(cell, depth: int, seen: set):
            indent = "    " * depth
            print(f"{indent}{cell.name}")
            if depth >= max_depth or cell.name in seen:
                return

            seen.add(cell.name)
            for reference in sorted(
                getattr(cell, "references", []),
                key=lambda ref: getattr(self._get_reference_cell(ref), "name", ""),
            ):
                ref_cell = self._get_reference_cell(reference)
                if ref_cell is not None:
                    _walk(ref_cell, depth + 1, seen)

        print("\nFINAL HIERARCHY")
        _walk(top_cell, 0, set())

        direct_top_refs = sorted(
            getattr(self._get_reference_cell(reference), "name", "")
            for reference in getattr(top_cell, "references", [])
            if self._get_reference_cell(reference) is not None
        )
        expected_top_refs = {
            self._get_chip_container_cell_name(chip_name)
            for chip_name in self.chip_info.keys()
        }
        expected_top_refs.add("ENV__VACUUM")
        print("\nTOP direct references:")
        for ref_name in direct_top_refs:
            marker = ""
            if ref_name not in expected_top_refs:
                marker = "  [unexpected]"
            print(f"  - {ref_name}{marker}")

    @staticmethod
    def debug_summarize_gds_library(lib: gdstk.Library, show=False) -> None:
        """Print a concise summary report for a gdstk.Library.

        The summary includes:

        - Library metadata (name, unit, precision, number of cells).
        - Cell names and whether they have geometry.
        - Per (layer, datatype) statistics:
            - number of polygons
            - number of paths

        Args:
            lib: Loaded gdstk.Library instance.

        Example:
            .. code-block:: python

                import gdstk

                lib = gdstk.read_gds("awesome_design.gds")
                summarize_gds_library(lib)
        """
        if show:
            write_library_overview_svg(lib, "test_output.svg")
            from IPython.display import SVG, display

            display(SVG("test_output.svg"))

        # Basic library info
        print("\n=== GDS LIBRARY SUMMARY ===")
        print(f"name:      {getattr(lib, 'name', None)}")
        print(f"unit:      {lib.unit}")
        print(f"precision: {lib.precision}")
        print(f"cells:     {len(lib.cells)}")

        # Cell list
        print("\nCELLS:")
        for cell in lib.cells:
            has_geom = bool(cell.polygons or cell.paths or cell.references)
            bbox = cell.bounding_box()
            bbox_str = "None" if bbox is None else f"{bbox}"
            print(f"  - {cell.name:30s} geom={has_geom} bbox={bbox_str}")

        # Collect per (layer, datatype) stats
        layer_stats: DictType[Tuple[int, int], DictType[str, int]] = defaultdict(
            lambda: {"polygons": 0, "paths": 0}
        )

        for cell in lib.cells:
            # Polygons
            for poly in cell.polygons:
                key = (poly.layer, poly.datatype)
                layer_stats[key]["polygons"] += 1

            # Paths (FlexPath / RobustPath)
            for path in cell.paths:
                # FlexPath / RobustPath can have multiple parallel elements
                # with potentially multiple layers; treat each layer separately.
                layers = getattr(path, "layers", [getattr(path, "layer", 0)])
                datatypes = getattr(path, "datatypes", [getattr(path, "datatype", 0)])

                # Normalize to lists of same length
                if not isinstance(layers, (list, tuple)):
                    layers = [layers]
                if not isinstance(datatypes, (list, tuple)):
                    datatypes = [datatypes]

                # Pair up safely
                for lyr, dt in zip(layers, datatypes):
                    key = (int(lyr), int(dt))
                    layer_stats[key]["paths"] += 1

        # If lib.layers_and_datatypes() is available, we can cross-check:
        try:
            lad = lib.layers_and_datatypes()
        except AttributeError:
            lad = None

        print("\nLAYER / DATATYPE USAGE:")
        if not layer_stats:
            print("  (no geometry found)")
        else:
            print("  layer  dtype   polys   paths")
            print("  -----  -----   -----   -----")
            for (layer, dtype), counts in sorted(layer_stats.items()):
                print(
                    f"  {layer:5d}  {dtype:5d}   "
                    f"{counts['polygons']:5d}   {counts['paths']:5d}"
                )

        if lad is not None:
            # Show the raw set from lib.layers_and_datatypes() for comparison
            print("\nlib.layers_and_datatypes():")
            for layer, dtype in sorted(lad):
                print(f"  (layer={layer}, datatype={dtype})")

        print("\n=== END SUMMARY ===\n")


def write_library_overview_svg(
    lib: gdstk.Library,
    filename: str = "library_overview.svg",
    background: str | None = "white",
    scale: float = 10.0,
) -> None:
    """Write a single SVG that references all cells in a library.

    Args:
        lib: GDS library to export.
        filename: Output SVG filename.
        background: SVG background color, or None for transparent.
        scale: Coordinate scaling factor applied when writing SVG.
    """
    top = gdstk.Cell("LIB_OVERVIEW")
    for cell in lib.top_level():  # for cell in lib.cells:
        top.add(gdstk.Reference(cell))
    top.write_svg(filename, background=background, scaling=scale)
