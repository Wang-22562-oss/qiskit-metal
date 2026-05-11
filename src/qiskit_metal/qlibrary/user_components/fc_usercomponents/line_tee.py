from qiskit_metal.qlibrary.couplers.line_tee import LineTee as _LineTee

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class LineTee(FlipChipCarveOutMixin, _LineTee):
    default_options = build_fc_default_options(_LineTee.default_options)
