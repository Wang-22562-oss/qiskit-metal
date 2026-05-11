from qiskit_metal.qlibrary.qubits.transmon_pocket_6 import TransmonPocket6 as _TransmonPocket6

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocket6(FlipChipCarveOutMixin, _TransmonPocket6):
    default_options = build_fc_default_options(_TransmonPocket6.default_options)
