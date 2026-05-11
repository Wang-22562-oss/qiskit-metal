from qiskit_metal.qlibrary.tlines.meandered import RouteMeander as _RouteMeander

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteMeander(FlipChipRouteMixin, _RouteMeander):
    default_options = build_fc_route_default_options(_RouteMeander.default_options)
