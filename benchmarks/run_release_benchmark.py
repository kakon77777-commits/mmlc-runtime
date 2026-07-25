from __future__ import annotations

import argparse
import json
from pathlib import Path

from mmlc.benchmark import run_release_benchmarks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("release/benchmark_v1.0.json"))
    parser.add_argument("--sizes", nargs="+", type=int, default=[64, 256, 1024])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    result = run_release_benchmarks(sizes=args.sizes, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
