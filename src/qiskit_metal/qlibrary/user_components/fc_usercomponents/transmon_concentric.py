from qiskit_metal.qlibrary.qubits.transmon_concentric import TransmonConcentric as _TransmonConcentric

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonConcentric(FlipChipCarveOutMixin, _TransmonConcentric):
    default_options = build_fc_default_options(_TransmonConcentric.default_options)
