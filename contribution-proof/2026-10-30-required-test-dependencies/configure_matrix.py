#!/usr/bin/env python3
"""Exercise libzip's real CMake configuration and actual CTest discovery."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

parser = argparse.ArgumentParser()
parser.add_argument("phase", choices=["baseline", "candidate"])
args = parser.parse_args()
root = Path(__file__).resolve().parent.parent
source = root / "libzip-sustained"
tools = root / "build-tools/libzip-tools/bin"
out = Path(__file__).resolve().parent / args.phase
out.mkdir(parents=True, exist_ok=False)
cmake = str(tools / "cmake")
ctest = str(tools / "ctest")
nihtest = str(tools / "nihtest")
env = dict(os.environ)
env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")
base = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
patch = subprocess.check_output(["git", "-C", str(source), "diff", "--binary", "HEAD"])
(out / "tested-source.patch").write_bytes(patch)
source_identity = {"base": base, "patch_sha256": hashlib.sha256(patch).hexdigest()}
cases = [
    ("default-missing-nihtest", ["-DNIHTEST:FILEPATH="], True, False, "nihtest not found"),
    ("default-tools-disabled", ["-DBUILD_TOOLS=OFF", "-DNIHTEST:FILEPATH=" + nihtest], True, False, "tools build has been disabled"),
]
if args.phase == "baseline":
    cases.append(("default-tests-available", ["-DNIHTEST:FILEPATH=" + nihtest], True, True, None))
else:
    cases += [
        ("strict-missing-nihtest", ["-DREQUIRE_TEST_DEPENDENCIES=ON", "-DNIHTEST:FILEPATH="], False, None, "Regression tests require nihtest"),
        ("strict-tools-disabled", ["-DREQUIRE_TEST_DEPENDENCIES=ON", "-DBUILD_TOOLS=OFF", "-DNIHTEST:FILEPATH=" + nihtest], False, None, "Regression tests require BUILD_TOOLS"),
        ("strict-tests-intentionally-disabled", ["-DREQUIRE_TEST_DEPENDENCIES=ON", "-DBUILD_REGRESS=OFF", "-DBUILD_TOOLS=OFF", "-DNIHTEST:FILEPATH="], True, False, None),
        ("strict-unusable-nihtest", ["-DREQUIRE_TEST_DEPENDENCIES=ON", "-DNIHTEST:FILEPATH=" + str(out / "nonexistent-nihtest")], False, None, "Regression tests require a working nihtest"),
        ("strict-tests-available", ["-DREQUIRE_TEST_DEPENDENCIES=ON", "-DNIHTEST:FILEPATH=" + nihtest], True, True, None),
    ]

def run_case(case):
    name, extra, success, have_tests, diagnostic = case
    build = out / name
    command = [cmake, "-S", str(source), "-B", str(build), "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + str(tools / "ninja"), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_REGRESS=ON", "-DBUILD_DOC=OFF", "-DBUILD_EXAMPLES=OFF", "-DBUILD_OSSFUZZ=OFF"] + extra
    started = datetime.now(timezone.utc).isoformat()
    begin = time.monotonic()
    proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True, timeout=120)
    (out / (name + ".log")).write_text(proc.stdout)
    tests = None
    discovery_code = None
    if proc.returncode == 0:
        discovery = subprocess.run([ctest, "--test-dir", str(build), "--show-only=json-v1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True, timeout=30)
        discovery_code = discovery.returncode
        (out / (name + "-ctest.json")).write_text(discovery.stdout)
        if discovery.returncode == 0:
            tests = len(json.loads(discovery.stdout)["tests"])
    checks = {"expected_configure_result": (proc.returncode == 0) == success}
    if have_tests is not None:
        checks["actual_test_discovery"] = discovery_code == 0 and tests is not None and ((tests > 0) if have_tests else tests == 0)
    if diagnostic:
        checks["expected_diagnostic"] = diagnostic in proc.stdout
    result = {"name": name, "command": command, "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(), "seconds": round(time.monotonic()-begin, 3), "configure_exit": proc.returncode, "ctest_discovery_exit": discovery_code, "discovered_tests": tests, "checks": checks, "passed": all(checks.values()), "log_sha256": hashlib.sha256(proc.stdout.encode()).hexdigest()}
    print(json.dumps({k: result[k] for k in ["name", "configure_exit", "discovered_tests", "passed", "seconds"]}), flush=True)
    return result

with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(run_case, cases))
after = subprocess.check_output(["git", "-C", str(source), "diff", "--binary", "HEAD"])
assert patch == after, "Source changed during configuration verification"
report = {"phase": args.phase, "source": source_identity, "tool_versions": {}, "cases": results, "source_unchanged_during_run": True, "all_cases_passed": all(x["passed"] for x in results)}
for name, cmd in [("cmake", [cmake, "--version"]), ("nihtest", [nihtest, "--version"]), ("ninja", [str(tools / "ninja"), "--version"]), ("compiler", ["cc", "--version"])]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
    report["tool_versions"][name] = p.stdout.strip()
(out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
raise SystemExit(0 if report["all_cases_passed"] else 1)
