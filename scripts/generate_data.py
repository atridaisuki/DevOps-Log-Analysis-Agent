"""Generate realistic log and metrics data for all scenarios.

Usage:
    python -m scripts.generate_data              # all scenarios
    python -m scripts.generate_data --scenario 1 # single scenario
    python -m scripts.generate_data --seed 123   # custom seed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.generators.log_engine import ServiceLogGenerator
from scripts.generators.metrics_engine import ServiceMetricsGenerator
from scripts.scenario_configs import ALL_SCENARIOS

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"


def generate_scenario(scenario: dict, seed: int) -> dict[str, int]:
    """Generate logs and metrics for one scenario. Returns file stats."""
    name = scenario["name"]
    date = scenario["date"]
    time_range = scenario["time_range"]
    fault_window = scenario["fault_window"]

    scenario_dir = DATA_DIR / name
    logs_dir = scenario_dir / "logs"
    metrics_dir = scenario_dir / "metrics"
    logs_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    stats = {"log_files": 0, "log_lines": 0, "metric_files": 0, "metric_points": 0}

    for i, log_config in enumerate(scenario["log_configs"]):
        gen = ServiceLogGenerator(
            config=log_config,
            time_range=time_range,
            fault_window=fault_window,
            date=date,
            seed=seed + i,
        )
        lines = gen.generate()
        log_path = logs_dir / f"{log_config.name}.log"
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        stats["log_files"] += 1
        stats["log_lines"] += len(lines)

    for i, metrics_config in enumerate(scenario["metrics_configs"]):
        gen = ServiceMetricsGenerator(
            config=metrics_config,
            time_range=time_range,
            fault_window=fault_window,
            seed=seed + 100 + i,
        )
        data = gen.generate()
        metrics_path = metrics_dir / f"{metrics_config.name}.json"
        metrics_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        stats["metric_files"] += 1
        for metric_data in data.values():
            stats["metric_points"] += len(metric_data.get("data", []))

    return stats


def main():
    parser = argparse.ArgumentParser(description="Generate scenario data")
    parser.add_argument("--scenario", type=int, help="Scenario number (1-5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    if args.scenario:
        if not 1 <= args.scenario <= len(ALL_SCENARIOS):
            print(f"Error: scenario must be 1-{len(ALL_SCENARIOS)}")
            sys.exit(1)
        scenarios = [ALL_SCENARIOS[args.scenario - 1]]
    else:
        scenarios = ALL_SCENARIOS

    total = {"log_files": 0, "log_lines": 0, "metric_files": 0, "metric_points": 0}

    for scenario in scenarios:
        stats = generate_scenario(scenario, args.seed)
        print(f"  {scenario['name']}: {stats['log_lines']} log lines, "
              f"{stats['metric_points']} metric points")
        for k in total:
            total[k] += stats[k]

    print(f"\nTotal: {total['log_files']} log files ({total['log_lines']} lines), "
          f"{total['metric_files']} metric files ({total['metric_points']} points)")


if __name__ == "__main__":
    main()
