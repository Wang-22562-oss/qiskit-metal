from qiskit_metal.qlibrary.qubits.JJ_Manhattan import jj_manhattan as _jj_manhattan

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class jj_manhattan(FlipChipCarveOutMixin, _jj_manhattan):
    default_options = build_fc_default_options(_jj_manhattan.default_options)
