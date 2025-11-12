#!/usr/bin/env python3
"""
Download Synthea, synthesize patient data, and export FHIR NDJSON files locally.

Typical usage:
    python generate_synthea_ndjson.py --num-patients 50 --output-dir ./synthea_ndjson

Prerequisites:
- Java 11+ available on PATH.
- Internet access to download the Synthea release (cached after first run).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import requests

DEFAULT_VERSION = "3.2.1"
RELEASE_BASE = "https://github.com/synthetichealth/synthea/releases/download"
CACHE_DIR = Path(".synthea_cache")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Synthea FHIR NDJSON files.")
    parser.add_argument("--num-patients", "-p", type=int, default=25, help="Patients to synthesize (default: 25).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("synthea_ndjson"),
        help="Directory to store NDJSON output (default: ./synthea_ndjson).",
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("SYNTHEA_VERSION", DEFAULT_VERSION),
        help=f"Synthea release version to download (default: {DEFAULT_VERSION}).",
    )
    parser.add_argument("--seed", type=int, help="Seed for deterministic runs.")
    parser.add_argument("--city", help="City name understood by Synthea (e.g., 'Boston').")
    parser.add_argument("--state", help="State name understood by Synthea (e.g., 'Massachusetts').")
    parser.add_argument(
        "--modules",
        nargs="+",
        metavar="MODULE",
        help="Optional list of module filenames to run (omit to use defaults).",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="Retain the raw Synthea output directory for inspection.",
    )
    parser.add_argument(
        "--synthea-jar",
        type=Path,
        help="Path to an existing synthea-with-dependencies.jar (skips download).",
    )
    return parser.parse_args()


def ensure_java() -> None:
    if not shutil.which("java"):
        sys.exit("Java executable not found in PATH. Install Java 11+ to run Synthea.")


def ensure_synthea_jar(version: str, override: Path | None) -> Path:
    if override:
        return override.resolve()
    jar_dir = CACHE_DIR / version
    jar_path = jar_dir / "synthea-with-dependencies.jar"
    if jar_path.exists():
        return jar_path
    jar_dir.mkdir(parents=True, exist_ok=True)
    url = f"{RELEASE_BASE}/v{version}/synthea-with-dependencies.jar"
    print(f"Downloading Synthea {version} from {url}")
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with jar_path.open("wb") as fp:
            for chunk in response.iter_content(chunk_size=1_048_576):
                if chunk:
                    fp.write(chunk)
    return jar_path


def run_synthea(jar_path: Path, args: argparse.Namespace, work_dir: Path) -> Path:
    cmd = ["java", "-jar", str(jar_path), "-p", str(args.num_patients)]
    if args.seed is not None:
        cmd += ["-s", str(args.seed)]
    if args.modules:
        cmd += ["-m", ",".join(args.modules)]
    if args.city:
        cmd += ["-c", args.city]
    if args.state:
        cmd.append(args.state)
    print(f"Running Synthea: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=work_dir, check=True)
    bundle_dir = work_dir / "output" / "fhir"
    if not bundle_dir.exists():
        sys.exit(f"Expected FHIR bundles under {bundle_dir}, but none were found.")
    return bundle_dir


def load_bundle(path: Path) -> Dict:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fp:
        return json.load(fp)


def convert_bundles_to_ndjson(bundle_dir: Path, ndjson_dir: Path) -> int:
    ndjson_dir.mkdir(parents=True, exist_ok=True)
    resources: Dict[str, List[Dict]] = defaultdict(list)
    bundle_paths = sorted([p for p in bundle_dir.glob("**/*.json*") if p.is_file()])
    if not bundle_paths:
        sys.exit(f"No bundle JSON files found in {bundle_dir}")

    for path in bundle_paths:
        bundle = load_bundle(path)
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if not resource:
                continue
            resource_type = resource.get("resourceType")
            if not resource_type or resource_type == "Bundle":
                continue
            resources[resource_type].append(resource)

    for resource_type, payloads in resources.items():
        out_path = ndjson_dir / f"{resource_type}.ndjson"
        with out_path.open("w", encoding="utf-8") as fp:
            for resource in payloads:
                fp.write(json.dumps(resource))
                fp.write("\n")
        print(f"Wrote {len(payloads):>5} {resource_type} resources -> {out_path}")

    return sum(len(items) for items in resources.values())


def main() -> None:
    args = parse_args()
    ensure_java()
    jar_path = ensure_synthea_jar(args.version, args.synthea_jar)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ndjson_dir = args.output_dir.resolve()
    with tempfile.TemporaryDirectory(prefix="synthea-run-") as tmpdir:
        work_dir = Path(tmpdir)
        bundle_dir = run_synthea(jar_path, args, work_dir)
        total_resources = convert_bundles_to_ndjson(bundle_dir, ndjson_dir)
        print(f"Finished generating NDJSON under {ndjson_dir} ({total_resources} resources).")

        if args.keep_raw:
            raw_copy = ndjson_dir / "raw_fhir_output"
            if raw_copy.exists():
                shutil.rmtree(raw_copy)
            shutil.copytree(work_dir / "output", raw_copy)
            print(f"Raw Synthea output retained at {raw_copy}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted by user.")
