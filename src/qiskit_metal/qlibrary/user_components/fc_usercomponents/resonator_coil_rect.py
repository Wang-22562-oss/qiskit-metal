from qiskit_metal.qlibrary.lumped.resonator_coil_rect import ResonatorCoilRect as _ResonatorCoilRect

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class ResonatorCoilRect(FlipChipCarveOutMixin, _ResonatorCoilRect):
    default_options = build_fc_default_options(_ResonatorCoilRect.default_options)
