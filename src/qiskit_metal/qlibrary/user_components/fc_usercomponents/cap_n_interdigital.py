from qiskit_metal.qlibrary.lumped.cap_n_interdigital import CapNInterdigital as _CapNInterdigital

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class CapNInterdigital(FlipChipCarveOutMixin, _CapNInterdigital):
    default_options = build_fc_default_options(_CapNInterdigital.default_options)
