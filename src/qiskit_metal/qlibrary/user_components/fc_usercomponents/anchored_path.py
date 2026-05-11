from qiskit_metal.qlibrary.tlines.anchored_path import RouteAnchors as _RouteAnchors

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteAnchors(FlipChipRouteMixin, _RouteAnchors):
    default_options = build_fc_route_default_options(_RouteAnchors.default_options)
