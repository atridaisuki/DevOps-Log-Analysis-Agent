"""Per-scenario fault definitions for data generation."""

from __future__ import annotations

from scripts.generators.log_engine import FaultPattern, ServiceLogConfig
from scripts.generators.metrics_engine import MetricDefinition, ServiceMetricsConfig

# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 01: Database Connection Pool Exhaustion
# Root cause: user-service pool max=10, traffic spike exhausts connections
# ═══════════════════════════════════════════════════════════════════════

SCENARIO_01 = {
    "name": "scenario_01_db_pool",
    "date": "2024-03-15",
    "time_range": ("09:00:00", "11:00:00"),
    "fault_window": ("10:00:00", "10:15:00"),
    "log_configs": [
        ServiceLogConfig(
            name="user-service",
            role="primary_fault",
            log_profile="java_web_user",
            baseline_interval=(3, 6),
            noise_warn_rate=0.03,
            fault_patterns=[
                FaultPattern(0, "WARN", "DB connection pool utilization: 80% (8/10 active)"),
                FaultPattern(30, "WARN", "DB connection pool utilization: 90% (9/10 active)"),
                FaultPattern(60, "WARN", "Slow DB query: 1200ms — SELECT * FROM users WHERE id = 456"),
                FaultPattern(90, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(91, "ERROR", "java.sql.SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 3000ms."),
                FaultPattern(120, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(150, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(180, "WARN", "Request queue depth: 23 pending requests waiting for DB connection"),
                FaultPattern(210, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(240, "ERROR", "Response: GET /api/users/789 -> 503 (3002ms) — Service Unavailable"),
                FaultPattern(270, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(300, "ERROR", "Response: POST /api/users/login -> 503 (3001ms) — Service Unavailable"),
                FaultPattern(360, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(420, "WARN", "Active threads: 48/50 — approaching thread pool limit"),
                FaultPattern(480, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(540, "ERROR", "Health check FAILED: cannot acquire DB connection within 1000ms"),
                FaultPattern(600, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(660, "ERROR", "Response: GET /api/users/profile -> 503 (3003ms) — Service Unavailable"),
                FaultPattern(720, "ERROR", "Failed to acquire DB connection: pool exhausted (timeout after 3000ms)"),
                FaultPattern(780, "WARN", "Cumulative stats: total_requests=312, success=198, failed=114, error_rate=36.5%"),
            ],
        ),
        ServiceLogConfig(
            name="api-gateway",
            role="affected",
            log_profile="nginx_gateway",
            baseline_interval=(2, 4),
            noise_warn_rate=0.02,
            propagation_delay=45.0,
            fault_patterns=[
                FaultPattern(0, "WARN", "Slow response: GET /api/users/456 -> 200 (3012ms)"),
                FaultPattern(30, "WARN", "Slow response: POST /api/users/login -> 200 (4100ms)"),
                FaultPattern(60, "ERROR", "Upstream timeout: user-service:8081 did not respond within 5000ms"),
                FaultPattern(90, "ERROR", "Response: GET /api/users/789 -> 504 (5002ms)"),
                FaultPattern(120, "ERROR", "Upstream timeout: user-service:8081 did not respond within 5000ms"),
                FaultPattern(180, "ERROR", "Upstream timeout: user-service:8081 did not respond within 5000ms"),
                FaultPattern(240, "ERROR", "Upstream timeout: user-service:8081 did not respond within 5000ms"),
                FaultPattern(300, "WARN", "Circuit breaker OPEN for user-service (5 failures in 60s)"),
                FaultPattern(360, "ERROR", "Response: GET /api/users/321 -> 503 Service Unavailable (circuit breaker open)"),
                FaultPattern(420, "ERROR", "Response: POST /api/users/login -> 503 Service Unavailable (circuit breaker open)"),
                FaultPattern(540, "WARN", "Circuit breaker half-open: testing user-service"),
                FaultPattern(600, "ERROR", "Circuit breaker re-opened: test request to user-service failed"),
            ],
        ),
        ServiceLogConfig(
            name="postgres",
            role="affected",
            log_profile="postgres",
            baseline_interval=(8, 15),
            noise_warn_rate=0.02,
            propagation_delay=0.0,
            fault_patterns=[
                FaultPattern(0, "LOG", "connection received: host=10.0.1.50 port=45123"),
                FaultPattern(10, "LOG", "connection received: host=10.0.1.50 port=45124"),
                FaultPattern(20, "LOG", "connection received: host=10.0.1.50 port=45125"),
                FaultPattern(60, "WARN", "connection slots: 25 of 100 used"),
                FaultPattern(180, "WARN", "connection slots: 38 of 100 used"),
                FaultPattern(300, "LOG", "statement duration: 1523ms — SELECT * FROM users WHERE email = $1"),
                FaultPattern(400, "WARN", "connection slots: 42 of 100 used"),
            ],
        ),
        ServiceLogConfig(
            name="order-service",
            role="distractor",
            log_profile="java_web_order",
            baseline_interval=(4, 8),
            noise_warn_rate=0.04,
        ),
        ServiceLogConfig(
            name="redis",
            role="distractor",
            log_profile="redis",
            baseline_interval=(10, 20),
            noise_warn_rate=0.02,
        ),
    ],
    "metrics_configs": [
        ServiceMetricsConfig(name="user-service", role="primary_fault", metrics=[
            MetricDefinition("cpu", "percent", baseline=25, noise_pct=8, fault_curve="ramp", fault_peak=88),
            MetricDefinition("memory", "MB", baseline=256, noise_pct=5, fault_curve="ramp", fault_peak=420),
            MetricDefinition("latency_p99", "ms", baseline=80, noise_pct=15, fault_curve="ramp", fault_peak=5200),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="step", fault_peak=36.5),
            MetricDefinition("db_connections", "count", baseline=3, noise_pct=20, fault_curve="ramp", fault_peak=10, metadata={"max_pool_size": 10}),
        ]),
        ServiceMetricsConfig(name="api-gateway", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="ramp", fault_peak=45),
            MetricDefinition("memory", "MB", baseline=128, noise_pct=5, fault_curve="flat"),
            MetricDefinition("latency_p99", "ms", baseline=120, noise_pct=15, fault_curve="ramp", fault_peak=5100),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50, fault_curve="step", fault_peak=28.0),
        ]),
        ServiceMetricsConfig(name="postgres", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="ramp", fault_peak=28),
            MetricDefinition("memory", "MB", baseline=120, noise_pct=3, fault_curve="ramp", fault_peak=135),
            MetricDefinition("connections", "count", baseline=8, noise_pct=15, fault_curve="ramp", fault_peak=42, metadata={"max_connections": 100}),
        ]),
        ServiceMetricsConfig(name="order-service", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10),
            MetricDefinition("memory", "MB", baseline=300, noise_pct=3),
            MetricDefinition("latency_p99", "ms", baseline=95, noise_pct=15),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50),
        ]),
        ServiceMetricsConfig(name="redis", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=5, noise_pct=15),
            MetricDefinition("memory", "MB", baseline=64, noise_pct=5),
            MetricDefinition("connections", "count", baseline=12, noise_pct=10),
        ]),
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 02: Out of Memory (unbounded cache)
# Root cause: order-service cache has no max_size/ttl, grows until OOM
# ═══════════════════════════════════════════════════════════════════════

SCENARIO_02 = {
    "name": "scenario_02_oom",
    "date": "2024-03-15",
    "time_range": ("13:00:00", "15:00:00"),
    "fault_window": ("14:15:00", "14:35:00"),
    "log_configs": [
        ServiceLogConfig(
            name="order-service",
            role="primary_fault",
            log_profile="java_web_order",
            baseline_interval=(3, 6),
            noise_warn_rate=0.03,
            fault_patterns=[
                FaultPattern(0, "WARN", "Heap usage at 75.0% (192MB / 256MB) — approaching threshold"),
                FaultPattern(60, "INFO", "GC pause: G1 Young Generation, 45ms, freed 8MB"),
                FaultPattern(120, "WARN", "Heap usage at 82.0% (210MB / 256MB) — approaching threshold"),
                FaultPattern(180, "INFO", "GC pause: G1 Young Generation, 78ms, freed 5MB"),
                FaultPattern(240, "WARN", "Heap usage at 88.5% (226MB / 256MB) — critical"),
                FaultPattern(300, "WARN", "GC pause: G1 Mixed, 120ms, freed 3MB — diminishing returns"),
                FaultPattern(360, "WARN", "Heap usage at 93.0% (238MB / 256MB) — critical"),
                FaultPattern(420, "ERROR", "GC overhead limit exceeded: spent 92% of time in GC, recovered < 2% heap"),
                FaultPattern(480, "ERROR", "java.lang.OutOfMemoryError: GC overhead limit exceeded"),
                FaultPattern(481, "ERROR", "    at java.util.concurrent.ConcurrentHashMap.put(ConcurrentHashMap.java:1011)"),
                FaultPattern(482, "ERROR", "    at com.example.order.cache.OrderCache.put(OrderCache.java:45)"),
                FaultPattern(483, "ERROR", "    at com.example.order.service.OrderService.processOrder(OrderService.java:112)"),
                FaultPattern(500, "ERROR", "Service shutting down: OutOfMemoryError"),
                FaultPattern(540, "INFO", "========== SERVICE RESTARTING =========="),
                FaultPattern(541, "INFO", "JVM args: -Xms128m -Xmx256m -XX:+UseG1GC -XX:MaxGCPauseMillis=200"),
                FaultPattern(545, "INFO", "Service started on port 8082"),
                FaultPattern(600, "INFO", "JVM Memory: heap used=145MB, heap max=256MB"),
                FaultPattern(660, "WARN", "Heap usage at 72.0% (184MB / 256MB) — cache growing again"),
                FaultPattern(780, "WARN", "Heap usage at 80.0% (205MB / 256MB) — approaching threshold"),
                FaultPattern(900, "ERROR", "java.lang.OutOfMemoryError: GC overhead limit exceeded"),
                FaultPattern(901, "ERROR", "Service shutting down: OutOfMemoryError (2nd crash)"),
            ],
        ),
        ServiceLogConfig(
            name="api-gateway",
            role="affected",
            log_profile="nginx_gateway",
            baseline_interval=(2, 5),
            noise_warn_rate=0.02,
            propagation_delay=60.0,
            fault_patterns=[
                FaultPattern(420, "ERROR", "Upstream timeout: order-service:8082 did not respond within 5000ms"),
                FaultPattern(450, "ERROR", "Response: POST /api/orders/create -> 504 (5001ms)"),
                FaultPattern(480, "ERROR", "Upstream connection refused: order-service:8082"),
                FaultPattern(510, "ERROR", "Response: GET /api/orders/100 -> 502 Bad Gateway"),
                FaultPattern(540, "WARN", "Circuit breaker OPEN for order-service (3 failures in 30s)"),
                FaultPattern(600, "INFO", "Circuit breaker half-open: testing order-service"),
                FaultPattern(620, "INFO", "Circuit breaker CLOSED: order-service recovered"),
                FaultPattern(900, "ERROR", "Upstream connection refused: order-service:8082 (2nd crash)"),
            ],
        ),
        ServiceLogConfig(
            name="user-service",
            role="distractor",
            log_profile="java_web_user",
            baseline_interval=(4, 8),
            noise_warn_rate=0.03,
        ),
        ServiceLogConfig(
            name="redis",
            role="distractor",
            log_profile="redis",
            baseline_interval=(10, 20),
            noise_warn_rate=0.02,
        ),
    ],
    "metrics_configs": [
        ServiceMetricsConfig(name="order-service", role="primary_fault", metrics=[
            MetricDefinition("cpu", "percent", baseline=30, noise_pct=8, fault_curve="sawtooth", fault_peak=98),
            MetricDefinition("memory", "MB", baseline=180, noise_pct=3, fault_curve="sawtooth", fault_peak=256, metadata={"heap_max": 256}),
            MetricDefinition("gc_pause_time", "ms", baseline=15, noise_pct=20, fault_curve="ramp", fault_peak=350),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="spike", fault_peak=100),
            MetricDefinition("cache_entries", "count", baseline=5000, noise_pct=2, fault_curve="ramp", fault_peak=85000),
        ]),
        ServiceMetricsConfig(name="api-gateway", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="spike", fault_peak=35),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50, fault_curve="spike", fault_peak=45),
            MetricDefinition("latency_p99", "ms", baseline=100, noise_pct=15, fault_curve="spike", fault_peak=5100),
        ]),
        ServiceMetricsConfig(name="user-service", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10),
            MetricDefinition("memory", "MB", baseline=256, noise_pct=3),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50),
        ]),
        ServiceMetricsConfig(name="redis", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=5, noise_pct=15),
            MetricDefinition("memory", "MB", baseline=64, noise_pct=5),
        ]),
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 03: Configuration Error (wrong Redis hostname)
# Root cause: auth-service config has redis-prod instead of redis
# ═══════════════════════════════════════════════════════════════════════

SCENARIO_03 = {
    "name": "scenario_03_config",
    "date": "2024-03-15",
    "time_range": ("13:00:00", "15:00:00"),
    "fault_window": ("14:00:00", "14:20:00"),
    "log_configs": [
        ServiceLogConfig(
            name="auth-service",
            role="primary_fault",
            log_profile="java_web_auth",
            baseline_interval=(3, 6),
            noise_warn_rate=0.02,
            fault_patterns=[
                FaultPattern(0, "INFO", "Service started on port 8083"),
                FaultPattern(1, "INFO", "Attempting to connect to Redis at redis-prod:6379"),
                FaultPattern(3, "ERROR", "Failed to connect to Redis: java.net.UnknownHostException: redis-prod: Name or service not known"),
                FaultPattern(5, "WARN", "Redis connection pool: 0 active connections, retrying in 5s"),
                FaultPattern(10, "ERROR", "Redis connection failed: java.net.UnknownHostException: redis-prod: Name or service not known"),
                FaultPattern(30, "ERROR", "Failed to validate session sess_a3f8c91b: unable to connect to session store"),
                FaultPattern(31, "ERROR", "Response: GET /auth/verify -> 500 (2005ms) — Internal Server Error"),
                FaultPattern(60, "ERROR", "Redis connection failed: java.net.UnknownHostException: redis-prod: Name or service not known"),
                FaultPattern(90, "ERROR", "Failed to validate session sess_b7e2d41a: unable to connect to session store"),
                FaultPattern(91, "ERROR", "Response: GET /auth/session/validate -> 500 (2003ms) — Internal Server Error"),
                FaultPattern(120, "WARN", "Session validation fallback: rejecting all session-based auth"),
                FaultPattern(180, "ERROR", "Redis connection failed: java.net.UnknownHostException: redis-prod"),
                FaultPattern(240, "ERROR", "Failed to validate session sess_c9f1e52d: unable to connect to session store"),
                FaultPattern(300, "WARN", "Cumulative stats: total_requests=89, success=52, failed=37, error_rate=41.6%"),
                FaultPattern(360, "INFO", "Token-based auth requests: 100% success (JWT validation is local)"),
                FaultPattern(420, "ERROR", "Redis connection failed: java.net.UnknownHostException: redis-prod"),
                FaultPattern(600, "WARN", "Cumulative stats: total_requests=156, success=91, failed=65, error_rate=41.7%"),
            ],
        ),
        ServiceLogConfig(
            name="api-gateway",
            role="affected",
            log_profile="nginx_gateway",
            baseline_interval=(2, 5),
            noise_warn_rate=0.02,
            propagation_delay=30.0,
            fault_patterns=[
                FaultPattern(30, "WARN", "Slow response: GET /auth/verify -> 500 (2005ms)"),
                FaultPattern(60, "ERROR", "Upstream error: auth-service:8083 returned 500"),
                FaultPattern(120, "ERROR", "Response: GET /api/users/profile -> 401 Unauthorized (session validation failed)"),
                FaultPattern(240, "ERROR", "Upstream error: auth-service:8083 returned 500"),
                FaultPattern(360, "WARN", "Elevated error rate from auth-service: 41% of requests failing"),
            ],
        ),
        ServiceLogConfig(
            name="order-service",
            role="distractor",
            log_profile="java_web_order",
            baseline_interval=(4, 8),
            noise_warn_rate=0.03,
        ),
        ServiceLogConfig(
            name="postgres",
            role="distractor",
            log_profile="postgres",
            baseline_interval=(10, 20),
            noise_warn_rate=0.02,
        ),
    ],
    "metrics_configs": [
        ServiceMetricsConfig(name="auth-service", role="primary_fault", metrics=[
            MetricDefinition("cpu", "percent", baseline=12, noise_pct=10, fault_curve="ramp", fault_peak=25),
            MetricDefinition("memory", "MB", baseline=180, noise_pct=3, fault_curve="flat"),
            MetricDefinition("latency_p99", "ms", baseline=15, noise_pct=20, fault_curve="step", fault_peak=2100),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="step", fault_peak=41.7),
            MetricDefinition("redis_connections", "count", baseline=0, noise_pct=0, fault_curve="flat", metadata={"expected": 5}),
        ]),
        ServiceMetricsConfig(name="api-gateway", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="ramp", fault_peak=22),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50, fault_curve="step", fault_peak=18.0),
        ]),
        ServiceMetricsConfig(name="order-service", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10),
            MetricDefinition("memory", "MB", baseline=300, noise_pct=3),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50),
        ]),
        ServiceMetricsConfig(name="postgres", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=12, noise_pct=10),
            MetricDefinition("connections", "count", baseline=15, noise_pct=10),
        ]),
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 04: Cascade Failure (SSL Certificate Expiry)
# Root cause: auth-service client cert expired → OAuth fails → cascade
# ═══════════════════════════════════════════════════════════════════════

SCENARIO_04 = {
    "name": "scenario_04_cascade",
    "date": "2024-03-15",
    "time_range": ("13:00:00", "15:00:00"),
    "fault_window": ("14:05:00", "14:25:00"),
    "log_configs": [
        ServiceLogConfig(
            name="auth-service",
            role="primary_fault",
            log_profile="java_web_auth",
            baseline_interval=(3, 6),
            noise_warn_rate=0.02,
            fault_patterns=[
                FaultPattern(0, "ERROR", "SSL handshake failed connecting to https://accounts.google.com/o/oauth2/token"),
                FaultPattern(1, "ERROR", "javax.net.ssl.SSLHandshakeException: PKIX path validation failed: java.security.cert.CertPathValidatorException: validity check failed"),
                FaultPattern(2, "ERROR", "Caused by: java.security.cert.CertificateExpiredException: NotAfter: Fri Mar 15 00:00:00 UTC 2024"),
                FaultPattern(3, "ERROR", "Client certificate /etc/ssl/certs/auth-service/client.pem expired on 2024-03-15T00:00:00Z"),
                FaultPattern(30, "ERROR", "OAuth token refresh failed: SSL handshake error"),
                FaultPattern(60, "WARN", "Health check: status=DEGRADED, oauth_provider=disconnected, reason=SSL certificate expired"),
                FaultPattern(90, "ERROR", "Cannot authenticate user via OAuth: provider unreachable"),
                FaultPattern(120, "WARN", "Falling back to cached tokens (remaining: 4521)"),
                FaultPattern(180, "WARN", "Health check: status=DEGRADED, cached_tokens_remaining=3892, cache_expiry_rate=2.1/s"),
                FaultPattern(240, "ERROR", "Cannot re-validate token — OAuth provider unreachable"),
                FaultPattern(300, "WARN", "Health check: status=DOWN, cached_tokens_remaining=2650"),
                FaultPattern(420, "WARN", "cached_tokens_remaining=1183, cache_expiry_rate=2.1/s"),
                FaultPattern(540, "ERROR", "Token cache depleted for user group 'external'. All OAuth logins will fail."),
                FaultPattern(600, "ERROR", "ALERT: Certificate /etc/ssl/certs/auth-service/client.pem expired. Immediate renewal required."),
                FaultPattern(720, "WARN", "cached_tokens_remaining=312"),
                FaultPattern(900, "ERROR", "Token cache fully depleted. 100% of OAuth requests failing."),
            ],
        ),
        ServiceLogConfig(
            name="api-gateway",
            role="affected",
            log_profile="nginx_gateway",
            baseline_interval=(2, 5),
            noise_warn_rate=0.02,
            propagation_delay=120.0,
            fault_patterns=[
                FaultPattern(0, "WARN", "Elevated latency from auth-service: p99=1200ms"),
                FaultPattern(60, "ERROR", "Upstream error: auth-service:8083 returned 401 for OAuth user"),
                FaultPattern(120, "ERROR", "Response: GET /api/users/profile -> 401 Unauthorized"),
                FaultPattern(180, "WARN", "Auth failure rate increasing: 15% of requests"),
                FaultPattern(300, "ERROR", "Response: POST /api/orders/create -> 401 Unauthorized"),
                FaultPattern(420, "WARN", "Auth failure rate: 45% of requests"),
                FaultPattern(600, "WARN", "Auth failure rate: 78% of requests — approaching full outage"),
            ],
        ),
        ServiceLogConfig(
            name="user-service",
            role="affected",
            log_profile="java_web_user",
            baseline_interval=(4, 8),
            noise_warn_rate=0.02,
            propagation_delay=180.0,
            fault_patterns=[
                FaultPattern(0, "ERROR", "Token validation failed for user 12345: token expired, refresh failed"),
                FaultPattern(60, "ERROR", "Token validation failed for user 67890: unable to contact auth-service"),
                FaultPattern(120, "WARN", "Rejecting requests with expired tokens: auth-service unavailable for refresh"),
            ],
        ),
        ServiceLogConfig(
            name="order-service",
            role="distractor",
            log_profile="java_web_order",
            baseline_interval=(4, 8),
            noise_warn_rate=0.03,
        ),
    ],
    "metrics_configs": [
        ServiceMetricsConfig(name="auth-service", role="primary_fault", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="ramp", fault_peak=40),
            MetricDefinition("memory", "MB", baseline=200, noise_pct=3, fault_curve="flat"),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="ramp", fault_peak=100),
            MetricDefinition("oauth_connections", "count", baseline=8, noise_pct=10, fault_curve="step", fault_peak=0),
            MetricDefinition("cached_tokens", "count", baseline=5000, noise_pct=2, fault_curve="decay", fault_peak=0),
        ]),
        ServiceMetricsConfig(name="api-gateway", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="ramp", fault_peak=30),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50, fault_curve="ramp", fault_peak=78),
            MetricDefinition("latency_p99", "ms", baseline=100, noise_pct=15, fault_curve="ramp", fault_peak=1500),
        ]),
        ServiceMetricsConfig(name="user-service", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10, fault_curve="ramp", fault_peak=30),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="ramp", fault_peak=35),
        ]),
        ServiceMetricsConfig(name="order-service", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10),
            MetricDefinition("memory", "MB", baseline=300, noise_pct=3),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50),
        ]),
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# SCENARIO 05: Disk Full (WAL + logs fill disk)
# Root cause: postgres WAL archiving disabled + log rotation disabled
# ═══════════════════════════════════════════════════════════════════════

SCENARIO_05 = {
    "name": "scenario_05_disk",
    "date": "2024-03-15",
    "time_range": ("08:00:00", "10:30:00"),
    "fault_window": ("09:30:00", "10:10:00"),
    "log_configs": [
        ServiceLogConfig(
            name="postgres",
            role="primary_fault",
            log_profile="postgres",
            baseline_interval=(8, 15),
            noise_warn_rate=0.02,
            fault_patterns=[
                FaultPattern(0, "WARN", "disk usage on /var/lib/postgresql/14/main: 89% (178GB / 200GB)"),
                FaultPattern(1, "WARN", "WAL directory size: 13.5GB, pg_log directory size: 8.2GB, temp files: 3.1GB"),
                FaultPattern(120, "WARN", "disk usage: 92% (184GB / 200GB)"),
                FaultPattern(240, "WARN", "checkpoint write took 21.3s, expected < 15s; disk may be under pressure"),
                FaultPattern(360, "WARN", "slow write detected: fsync on WAL segment 0000000100000042000000A7 took 320ms"),
                FaultPattern(480, "WARN", "disk usage: 96% (192GB / 200GB)"),
                FaultPattern(600, "WARN", "slow write detected: fsync on WAL segment took 850ms"),
                FaultPattern(720, "WARN", "disk usage: 99% (198GB / 200GB) — CRITICAL"),
                FaultPattern(900, "ERROR", "could not write to file \"pg_wal/xlogtemp.88421\": No space left on device"),
                FaultPattern(901, "ERROR", "PANIC: WAL writer process failed: No space left on device"),
                FaultPattern(960, "ERROR", "could not extend file \"base/16384/18201\": No space left on device"),
                FaultPattern(961, "ERROR", "HINT: Check free disk space on the partition holding /var/lib/postgresql/14/main"),
                FaultPattern(1020, "ERROR", "FATAL: could not write lock file \"postmaster.pid\": No space left on device"),
                FaultPattern(1080, "ERROR", "database system is shut down due to disk full"),
            ],
        ),
        ServiceLogConfig(
            name="data-service",
            role="affected",
            log_profile="java_web_order",
            baseline_interval=(4, 8),
            noise_warn_rate=0.02,
            propagation_delay=120.0,
            fault_patterns=[
                FaultPattern(780, "ERROR", "Database write failed: org.postgresql.util.PSQLException: ERROR: could not extend file"),
                FaultPattern(840, "ERROR", "Transaction rollback: disk space error from postgres"),
                FaultPattern(900, "ERROR", "Database connection lost: postgres is shutting down"),
                FaultPattern(960, "ERROR", "Response: POST /api/data/ingest -> 500 (12ms) — Database unavailable"),
                FaultPattern(1020, "ERROR", "All database operations failing: postgres unreachable"),
                FaultPattern(1080, "WARN", "Queuing writes to local buffer (buffer size: 234 entries)"),
            ],
        ),
        ServiceLogConfig(
            name="api-gateway",
            role="affected",
            log_profile="nginx_gateway",
            baseline_interval=(2, 5),
            noise_warn_rate=0.02,
            propagation_delay=180.0,
            fault_patterns=[
                FaultPattern(900, "ERROR", "Upstream error: data-service:8084 returned 500"),
                FaultPattern(960, "ERROR", "Response: POST /api/data/ingest -> 502 Bad Gateway"),
                FaultPattern(1020, "WARN", "Elevated error rate from data-service: 100%"),
            ],
        ),
        ServiceLogConfig(
            name="redis",
            role="distractor",
            log_profile="redis",
            baseline_interval=(10, 20),
            noise_warn_rate=0.02,
        ),
    ],
    "metrics_configs": [
        ServiceMetricsConfig(name="postgres", role="primary_fault", metrics=[
            MetricDefinition("disk_usage", "percent", baseline=82, noise_pct=1, fault_curve="ramp", fault_peak=100),
            MetricDefinition("wal_size", "GB", baseline=10, noise_pct=3, fault_curve="ramp", fault_peak=18.5),
            MetricDefinition("write_iops", "ops/s", baseline=450, noise_pct=10, fault_curve="ramp", fault_peak=0),
            MetricDefinition("read_iops", "ops/s", baseline=800, noise_pct=10, fault_curve="ramp", fault_peak=200),
            MetricDefinition("cpu", "percent", baseline=20, noise_pct=10, fault_curve="ramp", fault_peak=65),
            MetricDefinition("connections", "count", baseline=30, noise_pct=8, fault_curve="step", fault_peak=0, metadata={"max_connections": 200}),
        ]),
        ServiceMetricsConfig(name="data-service", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=25, noise_pct=10, fault_curve="spike", fault_peak=50),
            MetricDefinition("error_rate", "percent", baseline=0.1, noise_pct=50, fault_curve="spike", fault_peak=100),
            MetricDefinition("latency_p99", "ms", baseline=50, noise_pct=15, fault_curve="spike", fault_peak=12000),
        ]),
        ServiceMetricsConfig(name="api-gateway", role="affected", metrics=[
            MetricDefinition("cpu", "percent", baseline=15, noise_pct=10, fault_curve="spike", fault_peak=25),
            MetricDefinition("error_rate", "percent", baseline=0.05, noise_pct=50, fault_curve="spike", fault_peak=55),
        ]),
        ServiceMetricsConfig(name="redis", role="distractor", metrics=[
            MetricDefinition("cpu", "percent", baseline=5, noise_pct=15),
            MetricDefinition("memory", "MB", baseline=64, noise_pct=5),
        ]),
    ],
}

# ═══════════════════════════════════════════════════════════════════════
# ALL SCENARIOS
# ═══════════════════════════════════════════════════════════════════════

ALL_SCENARIOS = [SCENARIO_01, SCENARIO_02, SCENARIO_03, SCENARIO_04, SCENARIO_05]
