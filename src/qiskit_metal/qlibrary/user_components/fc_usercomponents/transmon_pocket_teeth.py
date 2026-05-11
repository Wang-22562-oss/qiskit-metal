from qiskit_metal.qlibrary.qubits.transmon_pocket_teeth import TransmonPocketTeeth as _TransmonPocketTeeth

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocketTeeth(FlipChipCarveOutMixin, _TransmonPocketTeeth):
    default_options = build_fc_default_options(_TransmonPocketTeeth.default_options)
