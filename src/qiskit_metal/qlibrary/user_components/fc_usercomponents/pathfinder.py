from qiskit_metal.qlibrary.tlines.pathfinder import RoutePathfinder as _RoutePathfinder

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RoutePathfinder(FlipChipRouteMixin, _RoutePathfinder):
    default_options = build_fc_route_default_options(_RoutePathfinder.default_options)
