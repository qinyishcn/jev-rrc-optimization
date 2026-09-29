"""Synthetic FIFO queue with periodic receive windows; not a radio simulator.

See docs/simulation.md for assumptions, traffic distributions and limitations.
All time values are milliseconds. Policy inputs must exclude the trace seed.
"""
from dataclasses import dataclass
import math
from numbers import Integral

import numpy as np


LONG_CYCLES = {10, 20, 32, 40, 64, 80, 128, 160, 256, 320, 512, 640,
               1024, 1280, 2048, 2560}
ON_DURATIONS = {1, 2, 3, 4, 5, 6, 8, 10, 20, 30, 40, 50, 60, 80, 100, 200}


def _finite(name, value, *, allow_zero=False):
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}")


def _integer(name, value, *, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    _finite(name, value, allow_zero=allow_zero)


@dataclass(frozen=True)
class Profile:
    name: str
    cycle_ms: float
    on_ms: float

    def __post_init__(self):
        if not self.name:
            raise ValueError("profile name must be nonempty")
        if self.cycle_ms == self.on_ms == 0:
            return  # synthetic DRX-disabled reference
        if (self.cycle_ms not in LONG_CYCLES or self.on_ms not in ON_DURATIONS
                or self.on_ms > self.cycle_ms):
            raise ValueError("profile needs supported LTE long-cycle/onDuration values")


PROFILES = tuple(Profile(name, cycle, on) for name, cycle, on in (
    ("off", 0, 0), ("10/8", 10, 8), ("10/4", 10, 4), ("10/2", 10, 2),
    ("20/8", 20, 8), ("20/4", 20, 4), ("32/8", 32, 8),
    ("40/4", 40, 4), ("80/4", 80, 4),
))


@dataclass(frozen=True)
class Scenario:
    uid: str
    service: str
    deadline_ms: float
    period_ms: float
    jitter_ms: float
    burst_packets: int
    packet_service_ms: float
    base_delay_ms: float
    duration_ms: float
    seed: int

    def __post_init__(self):
        for name in ("deadline_ms", "period_ms", "packet_service_ms", "duration_ms"):
            _finite(name, getattr(self, name))
        for name in ("jitter_ms", "base_delay_ms"):
            _finite(name, getattr(self, name), allow_zero=True)
        _integer("burst_packets", self.burst_packets)
        _integer("seed", self.seed, allow_zero=True)
        if self.jitter_ms > self.period_ms / 2:
            raise ValueError("jitter_ms must not exceed half the period")


def generate_scenarios(n_per_service: int, seed: int) -> list[Scenario]:
    """Independent descriptor draws; these distributions are experimental choices."""
    _integer("n_per_service", n_per_service)
    _integer("seed", seed, allow_zero=True)
    rng = np.random.default_rng(seed)
    # service, deadline, period choices, inclusive burst range, service/base ranges
    specs = (
        ("industrial_control", 5, (1, 2, 4, 5, 10), (1, 3), (.04, .18), (.5, 3.5)),
        ("xr", 10, (1000 / 120, 1000 / 90, 1000 / 60), (3, 12), (.04, .22), (.5, 5)),
        ("gaming", 20, (10, 1000 / 60, 20, 25, 1000 / 30), (1, 6), (.05, .3), (1, 8)),
    )
    scenarios = []
    for service, deadline, periods, burst, packet_time, base in specs:
        for i in range(n_per_service):
            period = float(rng.choice(periods))
            scenarios.append(Scenario(
                uid=f"{seed}-{service}-{i:04d}", service=service,
                deadline_ms=deadline, period_ms=period,
                jitter_ms=float(rng.uniform(0, .2) * period),
                burst_packets=int(rng.integers(burst[0], burst[1] + 1)),
                packet_service_ms=float(rng.uniform(*packet_time)),
                base_delay_ms=float(rng.uniform(*base)), duration_ms=1000.0,
                seed=int(rng.integers(0, 2**63 - 1)),
            ))
    return scenarios


def generate_arrivals(scenario: Scenario) -> np.ndarray:
    """Periodic simultaneous bursts with independent uniform event jitter/phase."""
    rng = np.random.default_rng(scenario.seed)
    phase = rng.uniform(0, scenario.period_ms)
    # Include neighboring nominal events so jitter across a boundary is retained.
    indices = np.arange(-1, math.ceil(scenario.duration_ms / scenario.period_ms) + 1)
    events = phase + indices * scenario.period_ms
    events += rng.uniform(-scenario.jitter_ms, scenario.jitter_ms, len(events))
    events = np.sort(events[(events >= 0) & (events < scenario.duration_ms)])
    return np.repeat(events, scenario.burst_packets)


def simulate(arrivals, profile: Profile, packet_service_ms: float,
             base_delay_ms: float, deadline_ms: float, duration_ms: float) -> dict:
    """Serve every arrival FIFO, without fragmentation, and drain after horizon.

    Awake intervals are [k * cycle, k * cycle + on). A packet may finish at
    the interval end. Constant base delay is added after the modeled queue;
    it does not occupy the server. Deadline equality is successful delivery.
    """
    for name, value in (("packet_service_ms", packet_service_ms),
                        ("deadline_ms", deadline_ms), ("duration_ms", duration_ms)):
        _finite(name, value)
    _finite("base_delay_ms", base_delay_ms, allow_zero=True)
    a = np.asarray(arrivals, dtype=float)
    if (a.ndim != 1 or a.size == 0 or not np.all(np.isfinite(a))
            or np.any(a < 0) or np.any(a >= duration_ms) or np.any(np.diff(a) < 0)):
        raise ValueError("arrivals must be nonempty, finite, sorted and in [0, duration_ms)")
    if profile.cycle_ms and packet_service_ms > profile.on_ms:
        raise ValueError("a whole packet must fit in an awake window")
    if profile.cycle_ms:
        ratio = profile.on_ms / packet_service_ms
        _finite("packets per window", ratio)
        slots = math.floor(math.nextafter(ratio, math.inf))
        capacity, duty = slots / profile.cycle_ms, profile.on_ms / profile.cycle_ms
    else:
        capacity, duty = 1 / packet_service_ms, 1.0
    _finite("capacity", capacity)
    utilization = (a.size / duration_ms) / capacity
    _finite("utilization", utilization, allow_zero=True)

    completion = np.empty(a.size, dtype=float)
    finish = 0.0
    for i, arrival in enumerate(a):
        ready = max(float(arrival), finish)
        if ready + packet_service_ms <= ready:
            raise ValueError("packet service time is below clock precision")
        if profile.cycle_ms:
            start = math.floor(ready / profile.cycle_ms) * profile.cycle_ms
            end = start + profile.on_ms
            candidate = ready + packet_service_ms
            tolerance = 8 * max(math.ulp(end), math.ulp(candidate))
            if candidate > end + tolerance:
                ready = start + profile.cycle_ms
                end = ready + profile.on_ms
            finish = min(ready + packet_service_ms, end)
        else:
            finish = ready + packet_service_ms
        if not math.isfinite(finish):
            raise ValueError("completion time overflow")
        completion[i] = finish

    delays = completion - a + base_delay_ms
    if not np.all(np.isfinite(delays)):
        raise ValueError("delay overflow")
    return {
        "mean_ms": float(np.sum(delays / a.size)),
        "p95_ms": float(np.quantile(delays, .95, method="linear")),
        "p99_ms": float(np.quantile(delays, .99, method="linear")),
        "max_ms": float(np.max(delays)), "miss_rate": float(np.mean(delays > deadline_ms)),
        "rx_duty": duty, "packets": int(a.size), "last_completion_ms": finish,
        "drain_ms": max(0.0, finish - duration_ms),
        "capacity_packets_per_ms": capacity, "utilization": utilization,
        "overloaded": bool(utilization > 1),
    }
