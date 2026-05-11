from qiskit_metal.qlibrary.qubits.transmon_cross_fl import TransmonCrossFL as _TransmonCrossFL

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonCrossFL(FlipChipCarveOutMixin, _TransmonCrossFL):
    default_options = build_fc_default_options(_TransmonCrossFL.default_options)
