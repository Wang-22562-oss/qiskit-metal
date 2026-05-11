from qiskit_metal.qlibrary.qubits.star_qubit import StarQubit as _StarQubit

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class StarQubit(FlipChipCarveOutMixin, _StarQubit):
    default_options = build_fc_default_options(_StarQubit.default_options)
