#!/usr/bin/env python3
"""Preserve an observed launch failure, compare upstream, and rebuild normally."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

evidence = Path(__file__).resolve().parent
root = evidence.parent
source = root / "libzip-sustained"
output = evidence / "launch-failure-diagnosis"
output.mkdir(exist_ok=False)
toolbin = root / "build-tools/libzip-tools/bin"
env = dict(os.environ)
env["PATH"] = str(toolbin) + os.pathsep + env.get("PATH", "")
manifest = json.loads((evidence / "frozen-source.json").read_text())
report = {"started_utc": datetime.now(timezone.utc).isoformat(), "source_commit": "c8eb979d0c0c5e4a9612d07c3849ec677659b165", "source_tree": manifest["tree"], "base": manifest["base"], "steps": [], "status": "running"}

def save():
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")

def file_info(path):
    s = path.stat()
    data = path.read_bytes()
    return {"path": str(path), "mode": oct(s.st_mode), "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "executable": os.access(path, os.X_OK)}

def account(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))
    failed = [t.attrib["name"] for t in cases if t.find("failure") is not None or t.find("error") is not None]
    skipped = [t.attrib["name"] for t in cases if t.find("skipped") is not None]
    return {"reported": len(cases), "passed": len(cases)-len(failed)-len(skipped), "failed": len(failed), "skipped": len(skipped), "failed_tests": failed, "skipped_tests": skipped}

def run(name, command, timeout=180):
    began = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    with (output / (name + ".log")).open("wb") as log:
        p = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout)
    data = (output / (name + ".log")).read_bytes()
    step = {"name": name, "command": command, "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(), "seconds": round(time.monotonic()-began, 3), "exit_code": p.returncode, "log_bytes": len(data), "log_sha256": hashlib.sha256(data).hexdigest()}
    report["steps"].append(step)
    save()
    print(json.dumps(step), flush=True)
    return p.returncode

original = evidence / "full-validation"
report["original_run"] = {"ctest_exit": 8, "tests": account(original / "ctest-results.xml"), "failure_kind": "nihtest could not launch the test executable: Errno 13 Permission denied", "original_report_unchanged": True}
binary = original / "build/regress/fopen_unchanged"
report["original_binary"] = file_info(binary)
assert report["original_binary"]["mode"] == "0o100644"
assert not report["original_binary"]["executable"]
for f in manifest["files"]:
    assert hashlib.sha256((source / f["path"]).read_bytes()).hexdigest() == f["sha256"]
report["candidate_source_matches_frozen_before"] = True
save()

base_source = evidence / "upstream-control-source"
assert subprocess.check_output(["git", "-C", str(base_source), "rev-parse", "HEAD"], text=True).strip() == manifest["base"]
assert subprocess.check_output(["git", "-C", str(base_source), "status", "--porcelain"]) == b""
base_build = output / "upstream-build"
assert run("upstream-configure", [str(toolbin / "cmake"), "-S", str(base_source), "-B", str(base_build), "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + str(toolbin / "ninja"), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_REGRESS=ON"]) == 0
assert run("upstream-build-fopen", [str(toolbin / "cmake"), "--build", str(base_build), "--target", "fopen_unchanged", "--parallel", "2"]) == 0
report["upstream_binary"] = file_info(base_build / "regress/fopen_unchanged")
base_exit = run("upstream-fopen-test", [str(toolbin / "ctest"), "--test-dir", str(base_build), "--no-tests=error", "--output-on-failure", "-V", "-R", "^fopen_unchanged[.]test$", "--output-junit", str(output / "upstream-fopen-results.xml")])
report["upstream_test"] = account(output / "upstream-fopen-results.xml")
report["upstream_source_unchanged"] = subprocess.check_output(["git", "-C", str(base_source), "status", "--porcelain"]) == b""
save()
assert base_exit == 0

# Preserve the generated artifact; the normal build recreates its missing output.
# Do not chmod binaries or alter test expectations to obtain a pass.
preserved = output / "initial-fopen_unchanged"
binary.rename(preserved)
report["preserved_initial_binary"] = file_info(preserved)
assert report["preserved_initial_binary"]["sha256"] == report["original_binary"]["sha256"]
assert run("candidate-rebuild-fopen", [str(toolbin / "cmake"), "--build", str(original / "build"), "--target", "fopen_unchanged", "--parallel", "2"]) == 0
report["rebuilt_candidate_binary"] = file_info(binary)
report["rebuilt_candidate_bytes_equal_original"] = report["rebuilt_candidate_binary"]["sha256"] == report["original_binary"]["sha256"]
save()
assert report["rebuilt_candidate_binary"]["executable"]
test_exit = run("candidate-full-ctest", [str(toolbin / "ctest"), "--test-dir", str(original / "build"), "--output-on-failure", "--no-tests=error", "-V", "-C", "Release", "--output-junit", str(output / "candidate-full-results.xml")], 600)
report["candidate_retest"] = account(output / "candidate-full-results.xml")
report["candidate_binary_after_tests"] = file_info(binary)
for f in manifest["files"]:
    assert hashlib.sha256((source / f["path"]).read_bytes()).hexdigest() == f["sha256"]
report["candidate_source_matches_frozen_after"] = True
report["completed_utc"] = datetime.now(timezone.utc).isoformat()
report["status"] = "passed" if test_exit == 0 and report["candidate_retest"]["failed"] == 0 else "failed"
report["attribution_limit"] = "The original artifact lacked execute bits; the actor or mechanism that changed its mode has not been established. The original launch failure is retained, not counted as a pass."
save()
print(json.dumps({"status": report["status"], "original": report["original_run"]["tests"], "upstream": report["upstream_test"], "candidate_retest": report["candidate_retest"], "rebuilt_candidate_bytes_equal_original": report["rebuilt_candidate_bytes_equal_original"]}), flush=True)
raise SystemExit(0 if report["status"] == "passed" else 1)
