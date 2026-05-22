"""Shared randomization utilities for data generation."""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta


def poisson_intervals(mean_seconds: float, duration_seconds: float, rng: random.Random) -> list[float]:
    """Generate inter-arrival times following a Poisson process.

    Returns a list of cumulative offsets (in seconds) from time 0.
    """
    offsets = []
    t = 0.0
    while t < duration_seconds:
        interval = rng.expovariate(1.0 / mean_seconds)
        t += interval
        if t < duration_seconds:
            offsets.append(t)
    return offsets


def jitter(value: float, noise_pct: float, rng: random.Random) -> float:
    """Add ±noise_pct% random noise to a value."""
    delta = value * noise_pct / 100.0
    return value + rng.uniform(-delta, delta)


def random_ip(rng: random.Random) -> str:
    """Generate a realistic internal IP address."""
    subnet = rng.choice(["192.168.1", "192.168.2", "10.0.1", "10.0.2"])
    host = rng.randint(10, 250)
    return f"{subnet}.{host}"


def random_user_id(rng: random.Random) -> str:
    return str(rng.randint(1000, 99999))


def random_request_id(rng: random.Random) -> str:
    return f"req_{rng.randint(100000, 999999):06x}"


def random_session_id(rng: random.Random) -> str:
    parts = [f"{rng.randint(0, 0xffff):04x}" for _ in range(4)]
    return f"sess_{''.join(parts)}"


def random_order_id(rng: random.Random, base: int = 10000) -> int:
    return base + rng.randint(0, 50000)


def sigmoid(x: float) -> float:
    """Standard sigmoid function."""
    return 1.0 / (1.0 + math.exp(-x))


def smooth_transition(progress: float, sharpness: float = 10.0) -> float:
    """Sigmoid-based smooth transition from 0 to 1.

    progress: 0.0 (start) to 1.0 (end)
    Returns: smoothed value between 0 and 1
    """
    return sigmoid(sharpness * (progress - 0.5))


def time_to_seconds(t: str) -> float:
    """Convert 'HH:MM:SS' or 'HH:MM' to seconds since midnight."""
    parts = t.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = int(parts[2]) if len(parts) > 2 else 0
    return h * 3600 + m * 60 + s


def seconds_to_time(secs: float) -> str:
    """Convert seconds since midnight to 'HH:MM:SS'."""
    h = int(secs) // 3600
    m = (int(secs) % 3600) // 60
    s = int(secs) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def seconds_to_hhmm(secs: float) -> str:
    """Convert seconds since midnight to 'HH:MM' (for metrics)."""
    h = int(secs) // 3600
    m = (int(secs) % 3600) // 60
    return f"{h:02d}:{m:02d}"


def format_timestamp(date: str, seconds_since_midnight: float) -> str:
    """Format a full log timestamp: 'YYYY-MM-DD HH:MM:SS'."""
    time_str = seconds_to_time(seconds_since_midnight)
    return f"{date} {time_str}"


HTTP_METHODS = ["GET", "POST", "PUT", "DELETE"]
HTTP_PATHS_USER = [
    "/api/users/{id}", "/api/users/login", "/api/users/profile",
    "/api/users/register", "/api/users/{id}/settings",
]
HTTP_PATHS_ORDER = [
    "/api/orders/{id}", "/api/orders/create", "/api/orders/list",
    "/api/orders/{id}/status", "/api/orders/{id}/cancel",
]
HTTP_PATHS_AUTH = [
    "/auth/verify", "/auth/token/refresh", "/auth/logout",
    "/auth/session/validate", "/auth/oauth/callback",
]
HTTP_STATUS_OK = [200, 200, 200, 200, 201, 204]
