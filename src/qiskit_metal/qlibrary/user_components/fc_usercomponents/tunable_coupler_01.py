from qiskit_metal.qlibrary.couplers.tunable_coupler_01 import TunableCoupler01 as _TunableCoupler01

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class TunableCoupler01(FlipChipCarveOutMixin, _TunableCoupler01):
    default_options = build_fc_default_options(_TunableCoupler01.default_options)
