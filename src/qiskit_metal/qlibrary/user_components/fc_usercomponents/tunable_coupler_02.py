from qiskit_metal.qlibrary.couplers.tunable_coupler_02 import TunableCoupler02 as _TunableCoupler02

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TunableCoupler02(FlipChipCarveOutMixin, _TunableCoupler02):
    default_options = build_fc_default_options(_TunableCoupler02.default_options)
