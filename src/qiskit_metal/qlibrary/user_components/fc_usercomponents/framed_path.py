from qiskit_metal.qlibrary.tlines.framed_path import RouteFramed as _RouteFramed

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteFramed(FlipChipRouteMixin, _RouteFramed):
    default_options = build_fc_route_default_options(_RouteFramed.default_options)
