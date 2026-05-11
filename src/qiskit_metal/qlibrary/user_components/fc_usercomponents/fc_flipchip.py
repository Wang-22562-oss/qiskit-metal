from shapely.ops import unary_union

from qiskit_metal import Dict
import shapely.geometry as geom


def build_fc_default_options(base_defaults):
    defaults = Dict(base_defaults)
    defaults.update(
        Dict(
            chip=defaults.get('chip', 'main'),
            carve_out_chip='Q_chip',
            carve_out_extend_size='10um',
            carve_out_layer=defaults.get('layer', '1'),
        ))
    return defaults


def build_fc_route_default_options(base_defaults):
    defaults = Dict(base_defaults)
    defaults.update(
        Dict(
            chip=defaults.get('chip', 'C_chip'),
            carve_out_chip='Q_chip',
            carve_out_extend_size='10um',
        ))
    return defaults


class FlipChipCarveOutMixin:
    """Add an opposite-chip carve-out based on existing component footprint."""

    def make(self):
        super().make()
        self.add_flipchip_carve_out()

    def add_flipchip_carve_out(self):
        p = self.p
        carve_out_chip = getattr(p, 'carve_out_chip', None)
        if not carve_out_chip or str(carve_out_chip).strip().lower() == 'none':
            return

        source_chip = getattr(p, 'chip', 'main')
        carve_source = self._collect_carve_source_geometry(source_chip)
        if carve_source is None or carve_source.is_empty:
            return

        extend_size = getattr(p, 'carve_out_extend_size', 0)
        if extend_size:
            carve_source = carve_source.buffer(
                extend_size, cap_style=2, join_style=1)

        carve_out_layer = int(getattr(p, 'carve_out_layer',
                                      getattr(p, 'layer', 1)))
        self.add_qgeometry('poly',
                           {'carve_out': carve_source},
                           subtract=True,
                           chip=carve_out_chip,
                           layer=carve_out_layer)

    def _collect_carve_source_geometry(self, source_chip):
        subtract_geoms = []
        metal_geoms = []

        for kind in ('poly', 'path'):
            table = self.qgeometry_table(kind)
            if table is None or table.empty:
                continue

            for _, row in table.iterrows():
                if row.get('helper', False):
                    continue
                if row.get('chip', 'main') != source_chip:
                    continue

                geom = row['geometry']
                if kind == 'path':
                    width = row.get('width', 0)
                    if not width:
                        continue
                    geom = geom.buffer(width / 2, cap_style=2, join_style=1)

                if row.get('subtract', False):
                    subtract_geoms.append(geom)
                else:
                    metal_geoms.append(geom)

        if subtract_geoms:
            return unary_union(subtract_geoms)
        if metal_geoms:
            return unary_union(metal_geoms)
        return None


class FlipChipRouteMixin:
    """Add an opposite-chip carve-out path for QRoute-based components."""

    def make(self):
        super().make()
        self.add_flipchip_route_carve_out()

    def add_flipchip_route_carve_out(self):
        p = self.p
        carve_out_chip = getattr(p, 'carve_out_chip', None)
        if not carve_out_chip or str(carve_out_chip).strip().lower() == 'none':
            return

        pts = self.get_points()
        if pts is None or len(pts) < 2:
            return

        route_line = geom.LineString(pts)
        total_cpw_width = p.trace_width + 2 * p.trace_gap
        carveout_width = total_cpw_width + 2 * p.carve_out_extend_size

        self.add_qgeometry('path',
                           {'top_carveout': route_line},
                           width=carveout_width,
                           fillet=getattr(p, 'fillet', 0),
                           chip=carve_out_chip,
                           layer=p.layer,
                           subtract=True)
