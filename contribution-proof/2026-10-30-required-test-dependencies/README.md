# Required test dependencies: verification evidence

Source: [c8eb979d0c0c5e4a9612d07c3849ec677659b165](https://github.com/agamal026/libzip/commit/c8eb979d0c0c5e4a9612d07c3849ec677659b165).
Upstream base: `da9448dec74a14ed2d20815c15846be89fb713a0`.
Source tree: `9b1694dbdfdae7119c01969d2eecdc2c83913ac6`.

This evidence accompanies the seven-file opt-in `REQUIRE_TEST_DEPENDENCIES` change. It is kept on a separate proof branch; it is not part of the proposed source diff.

## Executed verification

| Scope | Result |
|---|---|
| Unchanged upstream configuration | 3/3 cases passed: default missing nihtest, disabled tools, and available dependencies |
| Candidate configuration | 7/7 cases passed: preserved defaults, strict missing/unusable nihtest, disabled tools, explicitly disabled tests, healthy dependencies |
| Actual test discovery | 199 entries with healthy dependencies; zero when tests are intentionally or compatibly disabled |
| Complete native default build | Passed, Release configuration |
| First complete CTest run | 184 passed, 14 skipped, 1 launch failure; exit 8; preserved in full-validation |
| Unchanged upstream control | The single affected test passed after a fresh configure/build of the exact upstream base |
| Candidate after normal target rebuild | 185 passed, 14 skipped, 0 failures out of 199; exit 0 |

Native platform: Linux x86_64, GCC 13.3.0, Python 3.12, CMake 4.4.4, nihtest 1.11.1, Ninja 1.13.2 (Kitware jobserver-pipe build). CMake 3.14 compatibility and CI integration were statically reviewed; no execution on CMake 3.14, Windows, macOS, NetBSD, Solaris, or hosted CI is claimed here.

The 14 skips comprise three filesystem-cloning precheck skips and 11 tests requiring optional bzip2, LZMA/XZ, or Zstandard support. Optional library behavior is unchanged by this option.

## Initial launch failure and resolution

`fopen_unchanged.test` initially failed before its program ran: nihtest reported `Errno 13: Permission denied`. The generated executable alone had mode 0644; the other regression executables had mode 0755. The test did not reach its expected libzip behavior assertion in that run.

The original executable's bytes and metadata were recorded and the artifact preserved. An isolated, unchanged upstream checkout built the same target and passed the targeted test. Moving the candidate's generated output aside and rebuilding the target normally recreated mode 0755 with **identical bytes**, SHA-256 `145274ce6f9014e6b09dd9b32316d8df62c0fce70d4d6618e3c58629596c6394`. No chmod, test suppression, expectation change, or source modification was used. The complete candidate suite then passed with the same 14 skips. All seven source-file digests matched the frozen manifest before and after.

The actor or mechanism that changed the original executable's mode is unknown. The original failed run is retained and is not counted as a pass. `full-validation/report.json` intentionally retains its failed status; `launch-failure-diagnosis/report.json` contains complete original and final accounting.

## Independent review

Three independent automated reviewers examined the exact source semantics, workflow integration, and evidence. These are agent reviews, not human maintainer approval. Static review found the four main CI matrix jobs, NetBSD, Solaris, and the two test-running AppVeyor rows opt in; all six build-only AppVeyor rows remain unchanged. YAML parsing succeeded. Evidence review separately checked logs, source digests, and test accounting.

## Reproduction and provenance

Install the declared build dependencies and a working nihtest executable. From the candidate checkout:

```sh
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_REGRESS=ON -DREQUIRE_TEST_DEPENDENCIES=ON
cmake --build build --config Release --parallel 2
ctest --test-dir build --output-on-failure --no-tests=error -V -C Release
```

The configuration driver and reports retain every case's exact flags. To reproduce the default baseline, check out the upstream base first. To reproduce candidate cases, use the linked source. The preserved drivers describe the original scratch-directory layout and should be adapted to local paths; they are evidence, not an upstream test-framework addition. No network service is needed to run these regression tests after dependencies are installed.

`manifest.json` maps original and public SHA-256 hashes. `<WORKSPACE>`, `<RUNTIME_HOME>`, `<RUNTIME_PATH>`, and `<BUILD_HOST>` replace transient machine identifiers only. Step receipts use explicit UTC timestamps. CTest JUnit timestamps lack a timezone and are retained as emitted, not relabeled UTC. Source file hashes and the patch are unchanged by sanitization.

This evidence proves the recorded local results. It does not establish upstream acceptance or execution on other platforms.
