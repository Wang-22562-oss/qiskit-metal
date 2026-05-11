from qiskit_metal.qlibrary.tlines.mixed_path import RouteMixed as _RouteMixed

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteMixed(FlipChipRouteMixin, _RouteMixed):
    default_options = build_fc_route_default_options(_RouteMixed.default_options)
