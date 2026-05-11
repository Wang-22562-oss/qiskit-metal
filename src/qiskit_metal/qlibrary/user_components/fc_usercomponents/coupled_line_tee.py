from qiskit_metal.qlibrary.couplers.coupled_line_tee import CoupledLineTee as _CoupledLineTee

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class CoupledLineTee(FlipChipCarveOutMixin, _CoupledLineTee):
    default_options = build_fc_default_options(_CoupledLineTee.default_options)
