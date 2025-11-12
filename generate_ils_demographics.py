#!/usr/bin/env python3
"""
Generate synthetic patient data with ILS-specific demographics.

ILS specializes in Medicare, Medicaid, and Dual-Eligible markets with focus on
long-term care. This script generates a demographically appropriate population:
- Majority 65+ (Medicare eligible)
- Substantial portion 80+ (long-term care)
- Younger adults 18-64 with disabilities (Medicaid/Dual-Eligible)

Usage:
    python generate_ils_demographics.py --total-patients 100 --city Miami --state Florida
"""

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate ILS-specific demographic patient data."
    )
    parser.add_argument(
        "--total-patients",
        "-t",
        type=int,
        default=100,
        help="Total number of patients to generate (default: 100).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("synthea/ils_demographics"),
        help="Output directory (default: synthea/ils_demographics).",
    )
    parser.add_argument("--city", help="City name (e.g., 'Miami').")
    parser.add_argument("--state", help="State name (e.g., 'Florida').")
    parser.add_argument(
        "--version", default="3.4.0", help="Synthea version (default: 3.4.0)."
    )
    parser.add_argument("--seed", type=int, help="Base seed for reproducibility.")
    return parser.parse_args()


def generate_cohort(
    base_cmd: list[str],
    num_patients: int,
    min_age: int,
    max_age: int,
    cohort_name: str,
    seed_offset: int = 0,
) -> None:
    """Generate a single age cohort."""
    cmd = base_cmd + [
        "--num-patients",
        str(num_patients),
        "--min-age",
        str(min_age),
        "--max-age",
        str(max_age),
    ]

    if seed_offset:
        # Adjust seed if provided
        for i, arg in enumerate(cmd):
            if arg == "--seed" and i + 1 < len(cmd):
                cmd[i + 1] = str(int(cmd[i + 1]) + seed_offset)
                break

    print(f"\n{'='*60}")
    print(f"Generating {cohort_name}: {num_patients} patients aged {min_age}-{max_age}")
    print(f"{'='*60}")
    subprocess.run(cmd, check=True)


def main() -> None:
    args = parse_args()

    # Define demographic distribution based on ILS population profile
    # These percentages reflect typical Medicare/Medicaid/LTC populations
    total = args.total_patients

    # Age cohorts (percentages approximate ILS market)
    cohorts = [
        # Younger adults with disabilities (Medicaid, ~15%)
        {
            "name": "Young Adults with Disabilities (18-44)",
            "min_age": 18,
            "max_age": 44,
            "percentage": 0.08,
        },
        {
            "name": "Middle-Aged Adults with Disabilities (45-64)",
            "min_age": 45,
            "max_age": 64,
            "percentage": 0.12,
        },
        # Medicare eligible (65+, ~75%)
        {
            "name": "Young-Old Medicare (65-74)",
            "min_age": 65,
            "max_age": 74,
            "percentage": 0.25,
        },
        {
            "name": "Old Medicare (75-84)",
            "min_age": 75,
            "max_age": 84,
            "percentage": 0.30,
        },
        {
            "name": "Oldest-Old LTC Focus (85-100)",
            "min_age": 85,
            "max_age": 100,
            "percentage": 0.25,
        },
    ]

    # Build base command
    base_cmd = [
        "python",
        "generate_synthea_ndjson.py",
        "--output-dir",
        str(args.output_dir),
        "--version",
        args.version,
    ]

    if args.city:
        base_cmd += ["--city", args.city]
    if args.state:
        base_cmd += ["--state", args.state]
    if args.seed is not None:
        base_cmd += ["--seed", str(args.seed)]

    # Generate each cohort
    print(f"\nGenerating {total} patients with ILS demographic profile")
    print(f"Output directory: {args.output_dir}")

    for i, cohort in enumerate(cohorts):
        num_patients = max(1, int(total * cohort["percentage"]))
        generate_cohort(
            base_cmd,
            num_patients,
            cohort["min_age"],
            cohort["max_age"],
            cohort["name"],
            seed_offset=i * 1000 if args.seed else 0,
        )

    print(f"\n{'='*60}")
    print(f"✓ Successfully generated ILS demographic population")
    print(f"  Total patients: ~{total}")
    print(f"  Output: {args.output_dir}")
    print(f"  Demographics:")
    print(f"    - 18-64 (Disabilities): ~20%")
    print(f"    - 65-74 (Medicare):     ~25%")
    print(f"    - 75-84 (Medicare):     ~30%")
    print(f"    - 85-100 (LTC Focus):   ~25%")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted by user.")
    except subprocess.CalledProcessError as e:
        sys.exit(f"\nError running Synthea: {e}")
