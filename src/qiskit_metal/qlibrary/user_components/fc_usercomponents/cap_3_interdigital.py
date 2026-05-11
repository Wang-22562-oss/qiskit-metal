from qiskit_metal.qlibrary.lumped.cap_3_interdigital import Cap3Interdigital as _Cap3Interdigital

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class Cap3Interdigital(FlipChipCarveOutMixin, _Cap3Interdigital):
    default_options = build_fc_default_options(_Cap3Interdigital.default_options)
