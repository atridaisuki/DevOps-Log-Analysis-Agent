"""Metrics generation engine — produces realistic time-series JSON files."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from scripts.generators.noise import (
    jitter,
    seconds_to_hhmm,
    smooth_transition,
    time_to_seconds,
)


@dataclass
class MetricDefinition:
    name: str
    unit: str
    baseline: float
    noise_pct: float = 5.0
    fault_curve: str = "flat"  # flat, ramp, spike, step, sawtooth, decay
    fault_peak: float | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ServiceMetricsConfig:
    name: str
    role: str
    metrics: list[MetricDefinition]


class MetricCurve:
    """Generate time-series values with different degradation patterns."""

    @staticmethod
    def flat(baseline: float, noise_pct: float, n_points: int, rng: random.Random) -> list[float]:
        return [jitter(baseline, noise_pct, rng) for _ in range(n_points)]

    @staticmethod
    def ramp(
        baseline: float, peak: float, noise_pct: float,
        n_normal: int, n_fault: int, n_recovery: int, rng: random.Random
    ) -> list[float]:
        values = []
        # Normal period
        for _ in range(n_normal):
            values.append(jitter(baseline, noise_pct, rng))
        # Fault period: sigmoid ramp from baseline to peak
        for i in range(n_fault):
            progress = i / max(n_fault - 1, 1)
            t = smooth_transition(progress, sharpness=8.0)
            v = baseline + (peak - baseline) * t
            values.append(jitter(v, noise_pct * 0.5, rng))
        # Recovery period
        for i in range(n_recovery):
            progress = i / max(n_recovery - 1, 1)
            t = smooth_transition(progress, sharpness=6.0)
            v = peak - (peak - baseline) * t
            values.append(jitter(v, noise_pct, rng))
        return values

    @staticmethod
    def spike(
        baseline: float, peak: float, noise_pct: float,
        n_normal: int, n_fault: int, n_recovery: int, rng: random.Random
    ) -> list[float]:
        values = []
        for _ in range(n_normal):
            values.append(jitter(baseline, noise_pct, rng))
        # Sudden jump to peak
        for _ in range(n_fault):
            values.append(jitter(peak, noise_pct * 0.3, rng))
        for i in range(n_recovery):
            progress = i / max(n_recovery - 1, 1)
            t = smooth_transition(progress, sharpness=6.0)
            v = peak - (peak - baseline) * t
            values.append(jitter(v, noise_pct, rng))
        return values

    @staticmethod
    def step(
        baseline: float, peak: float, noise_pct: float,
        n_normal: int, n_fault: int, n_recovery: int, rng: random.Random
    ) -> list[float]:
        values = []
        for _ in range(n_normal):
            values.append(jitter(baseline, noise_pct, rng))
        # Instant step to peak, stays there
        for _ in range(n_fault + n_recovery):
            values.append(jitter(peak, noise_pct * 0.5, rng))
        return values

    @staticmethod
    def sawtooth(
        baseline: float, peak: float, noise_pct: float,
        n_normal: int, n_fault: int, n_recovery: int, rng: random.Random,
        crash_at: float = 0.6,
    ) -> list[float]:
        """Ramp up then crash (OOM pattern). May repeat."""
        values = []
        for _ in range(n_normal):
            values.append(jitter(baseline, noise_pct, rng))
        # First ramp to crash
        crash_point = int(n_fault * crash_at)
        for i in range(crash_point):
            progress = i / max(crash_point - 1, 1)
            v = baseline + (peak - baseline) * progress
            values.append(jitter(v, noise_pct * 0.3, rng))
        # Crash: drop to near-zero then restart ramp
        values.append(0.0)
        remaining = n_fault - crash_point - 1 + n_recovery
        for i in range(remaining):
            progress = i / max(remaining - 1, 1)
            v = baseline * 0.5 + (peak * 0.7 - baseline * 0.5) * progress
            values.append(jitter(v, noise_pct * 0.5, rng))
        return values

    @staticmethod
    def decay(
        baseline: float, peak: float, noise_pct: float,
        n_normal: int, n_fault: int, n_recovery: int, rng: random.Random
    ) -> list[float]:
        """Start at peak and decay toward zero (e.g., cached tokens depleting)."""
        values = []
        for _ in range(n_normal):
            values.append(jitter(baseline, noise_pct, rng))
        # Decay from baseline to near-zero
        for i in range(n_fault + n_recovery):
            progress = i / max(n_fault + n_recovery - 1, 1)
            v = baseline * (1 - progress * 0.95)
            values.append(max(0, jitter(v, noise_pct * 0.3, rng)))
        return values


CURVE_MAP = {
    "flat": MetricCurve.flat,
    "ramp": MetricCurve.ramp,
    "spike": MetricCurve.spike,
    "step": MetricCurve.step,
    "sawtooth": MetricCurve.sawtooth,
    "decay": MetricCurve.decay,
}


class ServiceMetricsGenerator:
    """Generate metrics JSON for one service."""

    def __init__(
        self,
        config: ServiceMetricsConfig,
        time_range: tuple[str, str],
        fault_window: tuple[str, str],
        seed: int = 42,
    ):
        self.config = config
        self.rng = random.Random(seed)

        self.start_secs = time_to_seconds(time_range[0])
        self.end_secs = time_to_seconds(time_range[1])
        self.fault_start = time_to_seconds(fault_window[0])
        self.fault_end = time_to_seconds(fault_window[1])

        total_minutes = int((self.end_secs - self.start_secs) / 60)
        fault_start_min = int((self.fault_start - self.start_secs) / 60)
        fault_end_min = int((self.fault_end - self.start_secs) / 60)

        self.n_total = total_minutes
        self.n_normal = fault_start_min
        self.n_fault = fault_end_min - fault_start_min
        self.n_recovery = total_minutes - fault_end_min

    def generate(self) -> dict:
        result = {}
        for metric_def in self.config.metrics:
            data_points = self._generate_metric(metric_def)
            entry = {"unit": metric_def.unit, "data": data_points}
            entry.update(metric_def.metadata)
            result[metric_def.name] = entry
        return result

    def _generate_metric(self, m: MetricDefinition) -> list[dict]:
        if self.config.role == "distractor" or m.fault_curve == "flat":
            values = MetricCurve.flat(m.baseline, m.noise_pct, self.n_total, self.rng)
        else:
            curve_fn = CURVE_MAP[m.fault_curve]
            peak = m.fault_peak if m.fault_peak is not None else m.baseline * 2
            if m.fault_curve == "flat":
                values = MetricCurve.flat(m.baseline, m.noise_pct, self.n_total, self.rng)
            else:
                values = curve_fn(
                    m.baseline, peak, m.noise_pct,
                    self.n_normal, self.n_fault, self.n_recovery, self.rng,
                )

        # Pad or trim to exact length
        while len(values) < self.n_total:
            values.append(jitter(m.baseline, m.noise_pct, self.rng))
        values = values[:self.n_total]

        # Build data points with timestamps
        data = []
        for i, v in enumerate(values):
            t_secs = self.start_secs + i * 60
            time_str = seconds_to_hhmm(t_secs)
            data.append({"time": time_str, "value": round(v, 1)})
        return data
