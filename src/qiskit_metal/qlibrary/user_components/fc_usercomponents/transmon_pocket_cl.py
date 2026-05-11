from qiskit_metal.qlibrary.qubits.transmon_pocket_cl import TransmonPocketCL as _TransmonPocketCL

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TransmonPocketCL(FlipChipCarveOutMixin, _TransmonPocketCL):
    default_options = build_fc_default_options(_TransmonPocketCL.default_options)
