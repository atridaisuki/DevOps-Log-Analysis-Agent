"""Log generation engine — produces realistic service log files."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from scripts.generators.noise import (
    HTTP_METHODS,
    HTTP_PATHS_AUTH,
    HTTP_PATHS_ORDER,
    HTTP_PATHS_USER,
    HTTP_STATUS_OK,
    format_timestamp,
    jitter,
    poisson_intervals,
    random_ip,
    random_order_id,
    random_request_id,
    random_session_id,
    random_user_id,
    time_to_seconds,
)


@dataclass
class LogEntry:
    timestamp_secs: float
    level: str
    service: str
    message: str

    def format(self, date: str) -> str:
        ts = format_timestamp(date, self.timestamp_secs)
        level_padded = f"{self.level:<5s}"
        return f"{ts} {level_padded} [{self.service}] {self.message}"


# ── Log Profiles: pools of realistic messages per service type ──────


def _java_web_info(service: str, rng: random.Random, paths: list[str]) -> list[str]:
    method = rng.choice(HTTP_METHODS[:3])
    path = rng.choice(paths).replace("{id}", random_user_id(rng))
    ip = random_ip(rng)
    latency = rng.randint(8, 180)
    status = rng.choice(HTTP_STATUS_OK)
    req_id = random_request_id(rng)

    lines = [f"Request received: {method} {path} from {ip} [{req_id}]"]
    if rng.random() < 0.3:
        lines.append(f"DB query executed in {rng.randint(2, 45)}ms")
    lines.append(f"Response: {method} {path} -> {status} ({latency}ms)")
    return lines


def _java_web_noise_warn(service: str, rng: random.Random) -> str:
    warns = [
        f"GC pause: G1 Young Generation, {rng.randint(15, 80)}ms, freed {rng.randint(5, 30)}MB",
        f"Thread pool utilization: {rng.randint(60, 85)}% ({rng.randint(30, 42)}/50 threads)",
        f"Slow DB query: {rng.randint(200, 800)}ms — SELECT * FROM sessions WHERE ...",
        f"Connection pool checkout time: {rng.randint(50, 200)}ms (threshold: 500ms)",
        f"HTTP client retry: attempt 2/3 for upstream call",
    ]
    return rng.choice(warns)


def _nginx_info(service: str, rng: random.Random) -> list[str]:
    method = rng.choice(HTTP_METHODS[:3])
    paths = HTTP_PATHS_USER + HTTP_PATHS_ORDER + HTTP_PATHS_AUTH
    path = rng.choice(paths).replace("{id}", random_user_id(rng))
    ip = random_ip(rng)
    upstream = rng.choice(["user-service:8081", "order-service:8082", "auth-service:8083"])
    latency = rng.randint(15, 250)

    lines = [
        f"Request received: {method} {path} from {ip}",
        f"Forwarding to {upstream}",
        f"Response: {method} {path} -> 200 ({latency}ms)",
    ]
    return lines


def _nginx_noise_warn(service: str, rng: random.Random) -> str:
    warns = [
        f"Slow response: GET /api/users/{random_user_id(rng)} -> 200 ({rng.randint(800, 2500)}ms)",
        f"Upstream health check: order-service latency {rng.randint(100, 400)}ms",
        f"Worker connections: {rng.randint(700, 900)}/1024",
    ]
    return rng.choice(warns)


def _postgres_info(service: str, rng: random.Random) -> list[str]:
    msgs = [
        [f"checkpoint starting: time"],
        [f"checkpoint complete: wrote {rng.randint(200, 2000)} buffers ({rng.uniform(1, 10):.1f}%); write={rng.uniform(1, 5):.1f}s, sync={rng.uniform(0.1, 0.5):.1f}s"],
        [f"automatic vacuum of table \"public.sessions\": removed {rng.randint(100, 5000)} dead tuples"],
        [f"statement: SELECT * FROM users WHERE id = {random_user_id(rng)} — duration: {rng.randint(1, 30)}ms"],
        [f"connection received: host={random_ip(rng)} port={rng.randint(40000, 60000)}"],
    ]
    return rng.choice(msgs)


def _postgres_noise_warn(service: str, rng: random.Random) -> str:
    warns = [
        f"autovacuum launcher: already running {rng.randint(2, 3)} workers",
        f"checkpoint write took {rng.uniform(5, 14):.1f}s, expected < 15s",
        f"temporary file: size {rng.randint(50, 500)}MB",
    ]
    return rng.choice(warns)


def _redis_info(service: str, rng: random.Random) -> list[str]:
    msgs = [
        [f"Connection accepted from {random_ip(rng)}:{rng.randint(40000, 60000)}"],
        [f"DB 0: {rng.randint(1000, 50000)} keys, expires={rng.randint(100, 5000)}"],
        [f"RDB: {rng.randint(1, 5)} changes in {rng.randint(60, 300)} seconds. Saving..."],
        [f"Background saving terminated with success"],
    ]
    return rng.choice(msgs)


def _redis_noise_warn(service: str, rng: random.Random) -> str:
    warns = [
        f"Memory usage: {rng.randint(60, 80)}% of maxmemory ({rng.randint(100, 200)}MB/{rng.randint(200, 256)}MB)",
        f"Slow command detected: KEYS pattern* took {rng.randint(50, 200)}ms",
    ]
    return rng.choice(warns)


LOG_PROFILES = {
    "java_web_user": {"info_fn": lambda s, r: _java_web_info(s, r, HTTP_PATHS_USER), "warn_fn": _java_web_noise_warn},
    "java_web_order": {"info_fn": lambda s, r: _java_web_info(s, r, HTTP_PATHS_ORDER), "warn_fn": _java_web_noise_warn},
    "java_web_auth": {"info_fn": lambda s, r: _java_web_info(s, r, HTTP_PATHS_AUTH), "warn_fn": _java_web_noise_warn},
    "nginx_gateway": {"info_fn": lambda s, r: _nginx_info(s, r), "warn_fn": _nginx_noise_warn},
    "postgres": {"info_fn": lambda s, r: _postgres_info(s, r), "warn_fn": _postgres_noise_warn},
    "redis": {"info_fn": lambda s, r: _redis_info(s, r), "warn_fn": _redis_noise_warn},
}


# ── Service Log Generator ──────────────────────────────────────────


@dataclass
class FaultPattern:
    relative_seconds: float
    level: str
    message: str


@dataclass
class ServiceLogConfig:
    name: str
    role: str  # "primary_fault", "affected", "distractor"
    log_profile: str
    baseline_interval: tuple[float, float]  # (min, max) seconds between log groups
    noise_warn_rate: float  # probability of a WARN in baseline
    fault_patterns: list[FaultPattern] = field(default_factory=list)
    propagation_delay: float = 0.0  # seconds after fault_start before symptoms appear


class ServiceLogGenerator:
    """Generate a complete log file for one service."""

    def __init__(
        self,
        config: ServiceLogConfig,
        time_range: tuple[str, str],
        fault_window: tuple[str, str],
        date: str,
        seed: int = 42,
    ):
        self.config = config
        self.date = date
        self.rng = random.Random(seed)

        self.start_secs = time_to_seconds(time_range[0])
        self.end_secs = time_to_seconds(time_range[1])
        self.fault_start = time_to_seconds(fault_window[0]) + config.propagation_delay
        self.fault_end = time_to_seconds(fault_window[1])

        self.profile = LOG_PROFILES[config.log_profile]

    def generate(self) -> list[str]:
        entries: list[LogEntry] = []

        # Generate baseline log entries across the full time range
        mean_interval = sum(self.config.baseline_interval) / 2
        duration = self.end_secs - self.start_secs
        offsets = poisson_intervals(mean_interval, duration, self.rng)

        for offset in offsets:
            t = self.start_secs + offset
            in_fault = self.fault_start <= t <= self.fault_end
            is_fault_service = self.config.role in ("primary_fault", "affected")

            # During fault window, reduce normal log frequency for fault services
            if in_fault and is_fault_service and self.rng.random() < 0.4:
                continue

            # Generate normal INFO log group
            info_lines = self.profile["info_fn"](self.config.name, self.rng)
            for i, line in enumerate(info_lines):
                entries.append(LogEntry(t + i * 0.1, "INFO", self.config.name, line))

            # Sprinkle noise WARN
            if self.rng.random() < self.config.noise_warn_rate:
                warn_msg = self.profile["warn_fn"](self.config.name, self.rng)
                entries.append(LogEntry(t + 0.5, "WARN", self.config.name, warn_msg))

        # Inject fault patterns
        if self.config.role in ("primary_fault", "affected"):
            for fp in self.config.fault_patterns:
                t = self.fault_start + fp.relative_seconds
                if t <= self.fault_end:
                    entries.append(LogEntry(t, fp.level, self.config.name, fp.message))

        # Sort by timestamp
        entries.sort(key=lambda e: e.timestamp_secs)
        return [e.format(self.date) for e in entries]
