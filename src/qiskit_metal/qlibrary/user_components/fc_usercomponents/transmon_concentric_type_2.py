from qiskit_metal.qlibrary.qubits.transmon_concentric_type_2 import TransmonConcentricType2 as _TransmonConcentricType2

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonConcentricType2(FlipChipCarveOutMixin, _TransmonConcentricType2):
    default_options = build_fc_default_options(_TransmonConcentricType2.default_options)
