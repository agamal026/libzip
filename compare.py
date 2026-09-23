import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
TESTS = {
    "crypto_clear.test",
    "set_compression_store_to_lzma.test",
    "set_compression_lzma_to_store.test",
    "set_compression_store_to_xz.test",
    "set_compression_xz_to_store.test",
}
XZ_TESTS = {name for name in TESTS if "_xz" in name}
GENERATOR = ["-G", "Visual Studio 17 2022", "-A", "Win32", "-T", "v142"]
LIBLZMA_DEFINE = re.compile(r"^#define[ \t]+HAVE_LIBLZMA[ \t]*$", re.MULTILINE)
RESULT = {"classification": "INCOMPLETE", "commands": [], "variants": {}}
SOURCE_HEADS = {
    "libzip": "b2da382b9626a66d6084f4efcd216cd6ce24d718",
    "xz-old": "a522a226545730551f7e7c2685fab27cf567746c",
    "xz-fixed": "4b73f2ec19a99ef465282fbce633e8deb33691b3",
    "zlib": "51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf",
}


def save_result():
    (EVIDENCE / "result.json").write_text(
        json.dumps(RESULT, indent=2) + "\n", encoding="utf-8"
    )


def run(name, arguments, *, env=None, require_success=True):
    started = time.monotonic()
    with (EVIDENCE / (name + ".log")).open("w", encoding="utf-8") as output:
        completed = subprocess.run(
            list(map(str, arguments)), cwd=ROOT, env=env, stdout=output,
            stderr=subprocess.STDOUT, timeout=600, check=False,
        )
    RESULT["commands"].append({
        "name": name, "arguments": list(map(str, arguments)),
        "exit_code": completed.returncode,
        "wall_seconds": time.monotonic() - started,
    })
    save_result()
    print(name, "exit", completed.returncode, flush=True)
    if require_success and completed.returncode:
        print((EVIDENCE / (name + ".log")).read_text(encoding="utf-8")[-8000:])
        raise RuntimeError(name + " failed")
    return completed.returncode


def configure(name, source, options):
    build = ROOT / ("build-" + name)
    run(name + "-configure", ["cmake", "-S", source, "-B", build, *GENERATOR, *options])
    shutil.copyfile(build / "CMakeCache.txt", EVIDENCE / (name + "-CMakeCache.txt"))
    compiler_files = list((build / "CMakeFiles").glob("*/CMakeCCompiler.cmake"))
    if len(compiler_files) != 1:
        raise RuntimeError("Expected one compiler identity for " + name)
    compiler = compiler_files[0].read_text(encoding="utf-8")
    shutil.copyfile(compiler_files[0], EVIDENCE / (name + "-CMakeCCompiler.cmake"))
    if not re.search(r'set\(CMAKE_C_COMPILER_VERSION "19\.29\.', compiler):
        raise RuntimeError("Comparison requires the MSVC 19.29 compiler family")
    if not re.search(r'set\(CMAKE_C_SIZEOF_DATA_PTR "4"\)', compiler):
        raise RuntimeError("Comparison requires 32-bit objects")
    return build


def build_install(name, source, options):
    prefix = ROOT / ("install-" + name)
    build = configure(name, source, ["-DCMAKE_INSTALL_PREFIX=" + prefix.as_posix(), *options])
    run(name + "-build", ["cmake", "--build", build, "--config", "Release", "--parallel", "4"])
    run(name + "-install", ["cmake", "--install", build, "--config", "Release"])
    return prefix, build


def compare_variant(name, xz_source, clmul, zlib_prefix):
    xz_prefix, xz_build = build_install(name + "-xz", ROOT / xz_source, [
        "-DBUILD_SHARED_LIBS=ON", "-DBUILD_TESTING=OFF", "-DXZ_NLS=OFF",
        "-DXZ_DOC=OFF", "-DXZ_TOOL_XZ=OFF", "-DXZ_TOOL_XZDEC=OFF",
        "-DXZ_TOOL_LZMADEC=OFF", "-DXZ_TOOL_LZMAINFO=OFF", "-DXZ_CLMUL_CRC=" + clmul,
    ])
    cache = (xz_build / "CMakeCache.txt").read_text(encoding="utf-8")
    if "XZ_CLMUL_CRC:BOOL=" + clmul not in cache:
        raise RuntimeError("CLMUL option was not bound")
    if name == "old-on" and "HAVE_USABLE_CLMUL:INTERNAL=1" not in cache:
        raise RuntimeError("The baseline did not compile the CLMUL path")
    libzip_build = configure(name + "-libzip", ROOT / "libzip", [
        "-DBUILD_SHARED_LIBS=OFF", "-DBUILD_DOC=OFF", "-DBUILD_EXAMPLES=OFF",
        "-DBUILD_OSSFUZZ=OFF", "-DENABLE_BZIP2=OFF", "-DENABLE_ZSTD=OFF",
        "-DENABLE_OPENSSL=OFF", "-DENABLE_GNUTLS=OFF", "-DENABLE_COMMONCRYPTO=OFF",
        "-DZLIB_INCLUDE_DIR=" + (zlib_prefix / "include").as_posix(),
        "-DZLIB_LIBRARY=" + (zlib_prefix / "lib/zlib.lib").as_posix(),
        "-DLIBLZMA_INCLUDE_DIR=" + (xz_prefix / "include").as_posix(),
        "-DLIBLZMA_LIBRARY=" + (xz_prefix / "lib/lzma.lib").as_posix(),
    ])
    config = (libzip_build / "config.h").read_text(encoding="utf-8")
    shutil.copyfile(libzip_build / "config.h", EVIDENCE / (name + "-libzip-config.h"))
    if not LIBLZMA_DEFINE.search(config):
        raise RuntimeError("Libzip did not enable liblzma")
    run(name + "-libzip-build", ["cmake", "--build", libzip_build, "--config", "Release", "--parallel", "4"])
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join([
        str(xz_prefix / "bin"), str(zlib_prefix / "bin"), environment["PATH"],
    ])
    expression = "^(" + "|".join(re.escape(value) for value in sorted(TESTS)) + ")$"
    junit = EVIDENCE / (name + "-tests.xml")
    exit_code = run(name + "-tests", [
        "ctest", "--test-dir", libzip_build, "-C", "Release", "-R", expression,
        "--output-on-failure", "--no-tests=error", "--output-junit", junit,
    ], env=environment, require_success=False)
    cases = ET.parse(junit).findall(".//testcase")
    if {case.get("name") for case in cases} != TESTS or len(cases) != len(TESTS):
        raise RuntimeError("Unexpected test selection for " + name)
    if any(case.find("skipped") is not None for case in cases):
        raise RuntimeError("A selected test was skipped")
    if any(case.find("error") is not None or case.get("status") not in ("run", "fail") for case in cases):
        raise RuntimeError("A selected test has an infrastructure error or did not run")
    if any((case.get("status") == "fail") != (case.find("failure") is not None) for case in cases):
        raise RuntimeError("A selected test has inconsistent status and failure elements")
    failures = sorted(case.get("name") for case in cases if case.find("failure") is not None)
    outputs = {case.get("name"): case.findtext("system-out", "") for case in cases}
    libraries = sorted(xz_prefix.rglob("*.dll"))
    RESULT["variants"][name] = {
        "ctest_exit_code": exit_code, "test_count": len(cases), "failures": failures,
        "clmul_option": clmul,
        "xz_clmul_configure_check": "HAVE_USABLE_CLMUL:INTERNAL=1" in cache,
        "expected_failure_signatures": (
            "3221225477" in outputs["set_compression_store_to_xz.test"]
            and "Compressed data invalid" in outputs["set_compression_xz_to_store.test"]
        ),
        "xz_dll_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in libraries},
    }
    save_result()


def main():
    if sys.platform != "win32":
        raise RuntimeError("This comparison must run on Windows")
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    EVIDENCE.mkdir()
    RESULT["source_heads"] = {
        name: subprocess.check_output(["git", "-C", str(ROOT / name), "rev-parse", "HEAD"], text=True).strip()
        for name in ("libzip", "xz-old", "xz-fixed", "zlib")
    }
    if RESULT["source_heads"] != SOURCE_HEADS:
        raise RuntimeError("The checked-out source identities differ from the pinned comparison")
    save_result()
    zlib_prefix, _ = build_install("zlib", ROOT / "zlib", ["-DZLIB_BUILD_EXAMPLES=OFF"])
    for name, source, clmul in (("old-on", "xz-old", "ON"), ("old-off", "xz-old", "OFF"), ("fixed-default", "xz-fixed", "ON")):
        compare_variant(name, source, clmul, zlib_prefix)
    variants = RESULT["variants"]
    if (set(variants["old-on"]["failures"]) == XZ_TESTS
            and variants["old-on"]["ctest_exit_code"] == 8
            and variants["old-on"]["expected_failure_signatures"]):
        if all(not variants[name]["failures"] and variants[name]["ctest_exit_code"] == 0 for name in ("old-off", "fixed-default")):
            RESULT["classification"] = "DIFFERENTIAL_CONFIRMED"
    if RESULT["classification"] != "DIFFERENTIAL_CONFIRMED":
        RESULT["classification"] = "EXPECTED_DIFFERENTIAL_NOT_CONFIRMED"
    save_result()
    print(json.dumps(RESULT["variants"], indent=2), flush=True)
    print(RESULT["classification"], flush=True)
    return 0 if RESULT["classification"] == "DIFFERENTIAL_CONFIRMED" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        if EVIDENCE.exists():
            RESULT["error"] = str(exc)
            save_result()
        raise
