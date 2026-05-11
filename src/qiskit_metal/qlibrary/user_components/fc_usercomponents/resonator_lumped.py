from qiskit_metal.qlibrary.resonators.resonator_lumped import ResonatorLumped as _ResonatorLumped

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class ResonatorLumped(FlipChipCarveOutMixin, _ResonatorLumped):
    default_options = build_fc_default_options(_ResonatorLumped.default_options)
