from qiskit_metal.qlibrary.tlines.straight_path import RouteStraight as _RouteStraight

from .fc_flipchip import FlipChipRouteMixin, build_fc_route_default_options


class RouteStraight(FlipChipRouteMixin, _RouteStraight):
    default_options = build_fc_route_default_options(_RouteStraight.default_options)
