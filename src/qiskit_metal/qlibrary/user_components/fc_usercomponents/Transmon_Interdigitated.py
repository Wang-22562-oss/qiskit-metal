from qiskit_metal.qlibrary.qubits.Transmon_Interdigitated import TransmonInterdigitated as _TransmonInterdigitated

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonInterdigitated(FlipChipCarveOutMixin, _TransmonInterdigitated):
    default_options = build_fc_default_options(_TransmonInterdigitated.default_options)
