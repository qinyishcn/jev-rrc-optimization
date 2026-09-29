# Synthetic DRX evaluator

This is a deterministic, single-server packet queue with periodic receive
windows. It is an experiment for choosing a constrained configuration, **not**
a 3GPP protocol implementation, radio/channel simulator, or measured network.
The public RRC records do not calibrate its traffic or latency parameters.

## Configuration scope

The fixed, ordered candidates are `off`, `10/8`, `10/4`, `10/2`, `20/8`,
`20/4`, `32/8`, `40/4`, `80/4`. A pair is cycle/on duration in milliseconds.
The disabled reference is represented as cycle=0/on=0 and receive duty=1.

The nonzero cycle and on-duration values are drawn from the LTE
`longDRX-CycleStartOffset` and `onDurationTimer` enumerations in
[3GPP TS 36.331 V11.2.0, DRX-Config, pp. 196 and 198](https://www.etsi.org/deliver/etsi_TS/136300_136399/136331/11.02.00_60/ts_136331v110200p.pdf).
The latter counts PDCCH subframes. This experiment assumes every subframe is a
1 ms PDCCH subframe; it does not implement TDD or other availability patterns.
4 and 8 ms are not used as long DRX cycles. Timer-value validity alone does not
make the resulting queue model a standards-compliant DRX implementation.

## Queue semantics

For cycle `C` and on-duration `O`, the receiver is available in
`[k*C, k*C+O)` for integer `k >= 0`. The DRX phase is fixed at zero.
All packets have the scenario's constant service time `s`. Packets are FIFO,
cannot be fragmented, and start only when they can finish in the current
receive window. Finishing exactly at the end is allowed. Otherwise the packet
waits for the next window. Floating comparisons use an eight-ULP tolerance at
window endpoints and clamp completion to that endpoint.

Arrivals must be sorted, finite and in `[0, duration_ms)`. Simultaneous arrivals
are valid. Empty traces are rejected because delay quantiles would be undefined.
Arrivals stop at the horizon; the queue then drains to completion. Every arrival
contributes to every packet metric, including under overload. A packet longer
than the on-duration is rejected as impossible in this nonfragmenting model.
Numerically unrepresentable capacities or service increments are also rejected.

Modeled delay = queue waiting + packet service + constant `base_delay_ms`.
The base term represents an exogenous delay budget contribution; it does not
hold the queue's server and is not a simulated network path. A deadline miss
means delay strictly greater than the deadline; equality is successful.

## Traffic distributions

`generate_scenarios(n_per_service, seed)` returns equally many scenarios for
each service below. These are hand-chosen synthetic workloads, not standardized
service models, measured application traces, or application-wide SLA claims.
Within each row, descriptors are drawn independently. Period is chosen uniformly
from its list; burst size is a uniform integer including both endpoints;
service and base delay are continuous uniform draws. Deadline is fixed.

| Service | Deadline (ms) | Period choices (ms) | Packets/burst | Service/packet (ms) | Base delay (ms) |
|---|---:|---|---:|---:|---:|
| industrial_control | 5 | 1, 2, 4, 5, 10 | 1–3 | 0.04–0.18 | 0.5–3.5 |
| xr | 10 | 1000/120, 1000/90, 1000/60 | 3–12 | 0.04–0.22 | 0.5–5 |
| gaming | 20 | 10, 1000/60, 20, 25, 1000/30 | 1–6 | 0.05–0.30 | 1–8 |

All arrival horizons are 1000 ms. The jitter half-width is uniformly chosen
between zero and 20% of the period. A separate deterministic trace seed is
drawn per scenario. `generate_arrivals(scenario)` draws a traffic phase uniformly
over one period, then adds independent uniform jitter in the declared range to
each periodic event. Each retained event yields a simultaneous burst. Nominal
events immediately outside the horizon are included before jitter and clipping
so boundary-crossing events are handled symmetrically. Custom scenarios allow
jitter up to half a period.

The random traffic phase reduces artificial alignment with a zero-phase DRX
schedule but does not eliminate periodic resonances. Each scenario has only one
trace phase realization. Comparisons must use exactly the same arrival array
for all candidate profiles. Different scenario seeds provide the independent
replicates for uncertainty estimates; packets in a burst are not independent
experimental replicates. Calibration and evaluation scenario seeds must differ.

Policies may see traffic and delay descriptors. They must not receive the trace
seed, realized arrivals, evaluation outcomes, or hindsight-best profile labels.

## Output and capacity checks

`simulate(arrivals, profile, packet_service_ms, base_delay_ms, deadline_ms,
duration_ms)` returns JSON-compatible scalar values:

| Key | Meaning |
|---|---|
| `mean_ms`, `p95_ms`, `p99_ms`, `max_ms` | All-arrival delay summaries; NumPy linear-interpolated quantiles |
| `miss_rate` | Fraction of all packets exceeding the deadline |
| `rx_duty` | Configured asymptotic `O/C`, or 1 when disabled |
| `packets` | Number of arrivals, all served |
| `last_completion_ms` | Final queue service completion, before exogenous base delay |
| `drain_ms` | Time final queue completion extends beyond the arrival horizon, floored at zero |
| `capacity_packets_per_ms` | Whole-packet saturated service capacity: `floor(O/s)/C`; disabled: `1/s` |
| `utilization` | Observed arrival rate over the fixed horizon divided by capacity |
| `overloaded` | Whether utilization is strictly greater than one |

The capacity check includes per-window unused time caused by whole packets.
Utilization below one does not guarantee any deadline, and finite bursts can
create queues even at low average utilization. Capacity is asymptotic, so a
finite-horizon utilization above one is a load warning rather than proof that
every finite trace violates a deadline. Overloaded results remain in evaluation.

`rx_duty` is a configured receive-availability proxy. It is not measured active
time, radiated power, device energy, or battery-life improvement. It does not
integrate partial first/last cycles or change with queue drain duration.

## Scientific limitations and validation

There are no DRX inactivity timers, short cycles, HARQ/retransmissions, scheduling
requests, grants, physical channels, interference, errors, mobility, bandwidth
sharing, variable packet sizes, transport protocols, or RRC reconfiguration
latency. Real DRX Active Time can extend beyond on-duration through other timers;
the fixed windows here deliberately omit that behavior. This omission and the
nonfragmenting service rule can materially change both delay and power tradeoffs.
The queue begins empty; there is no stationary-state burn-in. Results depend on
the synthetic horizon, distributions, phase, and offered load. They establish
neither NR URLLC reliability nor deployable configuration safety.

Run `.venv\Scripts\python.exe -m unittest discover -s tests -p test_simulation.py -v`.
Tests cover hand-computable sleep/wake delays and quantiles, exact endpoints,
FIFO spillover, deadline equality, post-horizon drain, packet conservation under
10,000-packet overload, independent integer-slot enumeration, DRX-disabled delay
lower bounds on common traces, descriptor/trace reproducibility and invalid inputs.
