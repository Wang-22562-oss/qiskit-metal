from qiskit_metal.qlibrary.qubits.transmon_pocket import TransmonPocket as _TransmonPocket

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocket(FlipChipCarveOutMixin, _TransmonPocket):
    default_options = build_fc_default_options(_TransmonPocket.default_options)
