from qiskit_metal.qlibrary.couplers.cap_n_interdigital_tee import CapNInterdigitalTee as _CapNInterdigitalTee

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class CapNInterdigitalTee(FlipChipCarveOutMixin, _CapNInterdigitalTee):
    default_options = build_fc_default_options(_CapNInterdigitalTee.default_options)
