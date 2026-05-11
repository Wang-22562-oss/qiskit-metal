from qiskit_metal.qlibrary.resonators.readoutres_fc import ReadoutResFC as _ReadoutResFC

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class ReadoutResFC(FlipChipCarveOutMixin, _ReadoutResFC):
    default_options = build_fc_default_options(_ReadoutResFC.default_options)
