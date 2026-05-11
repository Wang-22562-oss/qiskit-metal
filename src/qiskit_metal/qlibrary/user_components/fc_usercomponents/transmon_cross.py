from qiskit_metal.qlibrary.qubits.transmon_cross import TransmonCross as _TransmonCross

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonCross(FlipChipCarveOutMixin, _TransmonCross):
    default_options = build_fc_default_options(_TransmonCross.default_options)
