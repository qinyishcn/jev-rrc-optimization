"""Frozen decision prompt, traditional policies and explicit engineering screen."""
import json
import math

from rrcopt.simulation import PROFILES

BY_NAME = {p.name: p for p in PROFILES}
OPTIONS = [p.name for p in PROFILES]
QUESTION = ('Choose the connected-mode DRX profile with the lowest receiver ON fraction '
            'that keeps packet delay within the stated deadline for at least 99% of packets. '
            'Consider base delay, sleep wait, burst queueing and available service capacity. '
            'off means always awake. Other choices are cycle/on-duration in milliseconds. '
            'Use off when the deadline cannot safely tolerate sleep. Which profile?')


def context(s, current_mac=None):
    """Descriptors known before arrivals; never pass RNG seed or evaluation labels."""
    state = {
        'service': s.service, 'packet_deadline_ms': round(s.deadline_ms, 4),
        'burst_interval_ms': round(s.period_ms, 4), 'burst_jitter_plus_minus_ms': round(s.jitter_ms, 4),
        'packets_per_burst': s.burst_packets, 'service_time_per_packet_ms': round(s.packet_service_ms, 4),
        'fixed_network_delay_ms': round(s.base_delay_ms, 4),
    }
    if current_mac:
        state['existing_MAC_config_from_public_RRC_trace'] = current_mac
    return ('LTE FDD simplified periodic receive windows. Packets arriving during sleep wait for the next ON window. '
            'FIFO; each whole packet must finish within an ON window. The fixed network delay is added to '
            'queueing and service delay. Burst phase is unknown. Minimize ON fraction subject to the deadline. '
            + json.dumps(state, separators=(',', ':')))


def eligible(s):
    """Descriptor-only screening heuristic, NOT a proved latency guarantee.

    Sleep + burst service + one packet fragmentation margin + base <= deadline;
    pessimistic minimum inter-burst interval must fit with 2x capacity headroom.
    Full simulation still measures violations after this screen.
    """
    names = ['off']
    for p in PROFILES[1:]:
        delay_estimate = p.cycle_ms-p.on_ms + (s.burst_packets+1)*s.packet_service_ms + s.base_delay_ms
        interval = max(1e-9, s.period_ms-2*s.jitter_ms)
        capacity = math.floor(p.on_ms/s.packet_service_ms) / p.cycle_ms
        if delay_estimate <= s.deadline_ms and 2*s.burst_packets/interval <= capacity:
            names.append(p.name)
    return names


def guard_choice(s):
    def key(name):
        p = BY_NAME[name]
        return (p.on_ms/p.cycle_ms if p.cycle_ms else 1, p.cycle_ms-p.on_ms)
    return min(eligible(s), key=key)


def service_rule(s):
    return {'industrial_control':'10/8', 'xr':'10/4', 'gaming':'20/8'}[s.service]


def cost(metrics, deadline_ms):
    """Lexicographic feasibility, violation, duty, p99. Hindsight/calibration only."""
    violation = max(0, metrics['miss_rate']-.01)
    return (int(violation > 1e-12), violation, metrics['rx_duty'], metrics['p99_ms'])


def configuration_fragment(name):
    """A typed MAC-MainConfig DRX fragment; not an encoded full RRC message."""
    p = BY_NAME[name]
    if not p.cycle_ms:
        return {'drx-Config': {'release': None}}
    return {'drx-Config': {'setup': {
        'onDurationTimer': f'psf{int(p.on_ms)}', 'drx-InactivityTimer': 'psf1',
        'drx-RetransmissionTimer': 'psf1',
        'longDRX-CycleStartOffset': {f'sf{int(p.cycle_ms)}': 0},
    }}}
