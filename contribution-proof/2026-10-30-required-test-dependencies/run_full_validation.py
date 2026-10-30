#!/usr/bin/env python3
"""Run the native default build and CTest suite with strict test dependencies."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent.parent
source = root / "libzip-sustained"
evidence = Path(__file__).resolve().parent
output = evidence / "full-validation"
output.mkdir(parents=True, exist_ok=False)
build = output / "build"
toolbin = root / "build-tools/libzip-tools/bin"
manifest = json.loads((evidence / "frozen-source.json").read_text())
checkpoint = json.loads((evidence / "source-checkpoint.json").read_text())
for f in manifest["files"]:
    assert hashlib.sha256((source / f["path"]).read_bytes()).hexdigest() == f["sha256"]
env = dict(os.environ)
env["PATH"] = str(toolbin) + os.pathsep + env.get("PATH", "")
report = {"source_commit": checkpoint["commit"], "source_tree": manifest["tree"], "base": manifest["base"], "started_utc": datetime.now(timezone.utc).isoformat(), "steps": [], "status": "running", "platform_scope": "native Linux x86_64; hosted/other operating systems not executed"}

def save():
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")

def run(name, command, timeout):
    began = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    with (output / (name + ".log")).open("wb") as log:
        p = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=timeout)
    b = (output / (name + ".log")).read_bytes()
    step = {"name": name, "command": command, "started_utc": started, "completed_utc": datetime.now(timezone.utc).isoformat(), "seconds": round(time.monotonic() - began, 3), "exit_code": p.returncode, "log_bytes": len(b), "log_sha256": hashlib.sha256(b).hexdigest()}
    report["steps"].append(step)
    save()
    print(json.dumps(step), flush=True)
    if p.returncode:
        report["status"] = "failed: " + name
        save()
        raise SystemExit(p.returncode)

save()
run("configure", [str(toolbin / "cmake"), "-S", str(source), "-B", str(build), "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=" + str(toolbin / "ninja"), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_REGRESS=ON", "-DREQUIRE_TEST_DEPENDENCIES=ON"], 180)
run("build", [str(toolbin / "cmake"), "--build", str(build), "--config", "Release", "--parallel", "2"], 600)
run("ctest-discovery", [str(toolbin / "ctest"), "--test-dir", str(build), "--show-only=json-v1", "-C", "Release"], 30)
discovered = json.loads((output / "ctest-discovery.log").read_text())["tests"]
assert len(discovered) > 0, "No native tests discovered"
report["discovered_test_count"] = len(discovered)
run("ctest", [str(toolbin / "ctest"), "--test-dir", str(build), "--output-on-failure", "--no-tests=error", "-V", "-C", "Release", "--output-junit", str(output / "ctest-results.xml")], 600)
tests = ET.parse(output / "ctest-results.xml").getroot()
cases = list(tests.iter("testcase"))
passed = []; skipped = []; failed = []
for case in cases:
    name = case.attrib.get("name", "")
    if case.find("skipped") is not None:
        skipped.append(name)
    elif case.find("failure") is not None or case.find("error") is not None:
        failed.append(name)
    else:
        passed.append(name)
assert len(cases) == len(discovered), "Executed case accounting differs from discovery"
assert not failed, failed
for f in manifest["files"]:
    assert hashlib.sha256((source / f["path"]).read_bytes()).hexdigest() == f["sha256"], f["path"]
report.update(status="passed", completed_utc=datetime.now(timezone.utc).isoformat(), test_totals={"reported": len(cases), "passed": len(passed), "skipped": len(skipped), "failed_or_errors": len(failed)}, skipped_tests=skipped, failed_tests=failed, source_unchanged=True)
save()
print(json.dumps({"status": report["status"], "test_totals": report["test_totals"], "skipped_tests": skipped}), flush=True)
