from qiskit_metal.qlibrary.qubits.SQUID_loop import SQUID_LOOP as _SQUID_LOOP

from .fc_flipchip import FlipChipCarveOutMixin, build_fc_default_options


class SQUID_LOOP(FlipChipCarveOutMixin, _SQUID_LOOP):
    default_options = build_fc_default_options(_SQUID_LOOP.default_options)
