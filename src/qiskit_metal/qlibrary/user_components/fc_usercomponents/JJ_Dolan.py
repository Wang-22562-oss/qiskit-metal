from qiskit_metal.qlibrary.qubits.JJ_Dolan import jj_dolan as _jj_dolan

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class jj_dolan(FlipChipCarveOutMixin, _jj_dolan):
    default_options = build_fc_default_options(_jj_dolan.default_options)
