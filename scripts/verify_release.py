from __future__ import annotations

import compileall
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )


def main() -> None:
    # Test suite.
    test_run = run([sys.executable, "-m", "pytest", "-q"])
    collected = run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    test_count = sum(
        int(match.group(1))
        for line in collected.stdout.splitlines()
        if (match := re.search(r":\s*(\d+)\s*$", line))
    )

    # Python, JSON, Markdown and examples.
    python_files = [p for p in ROOT.rglob("*.py") if not any(part in {"build", "dist", ".venv"} for part in p.parts)]
    compiled = compileall.compile_dir(str(ROOT / "mmlc"), quiet=1, force=True)
    compiled &= compileall.compile_dir(str(ROOT / "tests"), quiet=1, force=True)
    if not compiled:
        raise RuntimeError("Python compilation failed")

    json_files = [p for p in ROOT.rglob("*.json") if "dist" not in p.parts and "build" not in p.parts]
    for path in json_files:
        json.loads(path.read_text(encoding="utf-8"))

    markdown_files = [p for p in ROOT.rglob("*.md") if "dist" not in p.parts and "build" not in p.parts]
    bad_fences = [str(p.relative_to(ROOT)) for p in markdown_files if p.read_text(encoding="utf-8").count("```") % 2]
    if bad_fences:
        raise RuntimeError(f"Unbalanced Markdown code fences: {bad_fences}")

    examples = sorted(p for p in (ROOT / "examples").iterdir() if p.suffix.lower() in {".yaml", ".yml", ".json"})
    validation_script = (
        "from mmlc import validate_file; import sys; "
        "[validate_file(p) for p in sys.argv[1:]]; print(len(sys.argv)-1)"
    )
    validated = run([sys.executable, "-c", validation_script, *map(str, examples)])

    release_validation = json.loads((ROOT / "release" / "release_validation_v1.0.json").read_text(encoding="utf-8"))
    if release_validation["migration_validation_failures"] != 0:
        raise RuntimeError("Migration validation failures detected")
    if release_validation["representative_equivalence_failures"] != 0:
        raise RuntimeError("Migration execution-equivalence failures detected")

    # Rebuild release distributions.
    dist = ROOT / "dist"
    build = ROOT / "build"
    egg_info = ROOT / "mmlc_runtime.egg-info"
    shutil.rmtree(dist, ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    shutil.rmtree(egg_info, ignore_errors=True)
    dist.mkdir(parents=True)
    run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "-w", str(dist), "."])
    run([
        sys.executable,
        "-c",
        "from setuptools.build_meta import build_sdist; print(build_sdist('dist'))",
    ])
    wheel = next(dist.glob("*.whl"))
    sdist = next(dist.glob("*.tar.gz"))

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        packaged_schemas = [name for name in wheel_names if name.startswith("mmlc/schemas/") and name.endswith(".json")]
        if len(packaged_schemas) != 10:
            raise RuntimeError(f"Wheel schema count mismatch: {len(packaged_schemas)}")
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = archive.getnames()
        required_fragments = ["README.md", "docs/API.md", "benchmarks/run_release_benchmark.py", "experiments/release_v1/run_release_v1.py"]
        for fragment in required_fragments:
            if not any(name.endswith(fragment) for name in sdist_names):
                raise RuntimeError(f"Source distribution missing {fragment}")

    # Installed-wheel smoke test from outside the source tree.
    with tempfile.TemporaryDirectory(prefix="mmlc-v1-install-") as target_dir, tempfile.TemporaryDirectory(prefix="mmlc-v1-cwd-") as cwd_dir:
        run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            target_dir,
            str(wheel),
        ], cwd=Path(cwd_dir))
        env = dict(os.environ)
        env["PYTHONPATH"] = target_dir
        smoke = run([
            sys.executable,
            "-c",
            (
                "from importlib.resources import files; "
                "from mmlc import runtime_info, validate_file; "
                "assert runtime_info()['version']=='1.0.0'; "
                "assert len([p for p in files('mmlc.schemas').iterdir() if p.name.endswith('.json')])==10; "
                f"assert validate_file({str(ROOT / 'examples' / 'mmlf_v1_stable.yaml')!r}).version=='1.0'; "
                "print('PASS')"
            ),
        ], cwd=Path(cwd_dir), env=env)
        if "PASS" not in smoke.stdout:
            raise RuntimeError("Installed wheel smoke test failed")

    result = {
        "verification_format": "MMLC-FINAL-VERIFICATION v1",
        "runtime_version": "1.0.0",
        "pytest_passed": test_count,
        "python_files_checked": len(python_files),
        "python_compilation": "PASS",
        "json_files_checked": len(json_files),
        "markdown_files_checked": len(markdown_files),
        "markdown_fence_errors": bad_fences,
        "examples_validated": int(validated.stdout.strip().splitlines()[-1]),
        "migrated_examples": release_validation["migrated_example_count"],
        "migration_equivalence_cases": release_validation["representative_equivalence_count"],
        "migration_equivalence_failures": release_validation["representative_equivalence_failures"],
        "benchmark_cases": release_validation["benchmark_cases"],
        "benchmark_hashes_identical": release_validation["all_benchmark_hashes_identical"],
        "benchmark_audits_pass": release_validation["all_benchmark_audits_pass"],
        "wheel": wheel.name,
        "wheel_file_count": len(wheel_names),
        "wheel_schema_count": len(packaged_schemas),
        "sdist": sdist.name,
        "sdist_file_count": len(sdist_names),
        "installed_wheel_smoke": "PASS",
        "release_validation_hash": release_validation["release_hash"],
        "status": "PASS",
    }
    (ROOT / "FINAL_VERIFICATION.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
