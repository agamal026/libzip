# Prepared upstream pull request

Title: Add opt-in configure-time checks for regression test dependencies

Status: source and verification complete; upstream PR creation returned HTTP 403, Resource not accessible by integration. No upstream PR was created. The description below is preserved for review.

## Description

Implement the Tests → CI item in [TODO.md](https://github.com/nih-at/libzip/blob/da9448dec74a14ed2d20815c15846be89fb713a0/TODO.md): add a CMake option to fail when regression-test prerequisites are unavailable and use it in test-running CI jobs.

`REQUIRE_TEST_DEPENDENCIES` defaults to `OFF`, preserving the existing warning-and-disable behavior. When it and `BUILD_REGRESS` are enabled, configuration fails if:

- `BUILD_TOOLS` is disabled;
- nihtest cannot be found; or
- the selected nihtest executable cannot complete `--version` successfully.

Explicit `BUILD_REGRESS=OFF` remains supported. Optional compression/encryption libraries retain their existing feature-dependent behavior.

The option is documented in INSTALL.md and enabled in the four main CI matrix jobs, NetBSD, Solaris, and the two AppVeyor rows that run tests. The six build-only AppVeyor rows remain unchanged. The completed dependency-option TODO is removed.

Existing CI already uses `ctest --no-tests=error`; this change reports missing prerequisites earlier, during configuration, and provides the same strict option to other builds.

## Validation

On Linux x86_64 with GCC 13.3, CMake 4.4.4, nihtest 1.11.1, and Ninja 1.13.2:

- Three unchanged-upstream configuration cases and seven candidate cases passed. These cover preserved defaults, strict missing/unusable nihtest, disabled tools, explicitly disabled tests, and healthy prerequisites.
- Healthy baseline and strict candidate configurations each discover the same 199 tests.
- The complete Release build succeeded.
- The final complete CTest run reported **185 passed, 14 skipped, 0 failures**. The skips are three filesystem-cloning prechecks and eleven optional-compression cases.
- YAML parsing and independent automated source, CI-integration, and evidence reviews passed. CMake 3.14 and non-Linux execution are not claimed.

The first full run had one launch failure because the generated `fopen_unchanged` executable lacked execute bits. The original artifact and failure were preserved. The test passed against unchanged upstream; a normal candidate-target rebuild produced identical executable bytes with mode 0755, and the complete rerun passed. No source, expected output, or test selection changed. The cause of the original mode change remains unknown.

[Commands, configuration matrix, original failure, control, complete rerun logs, and source/hash manifests](https://github.com/agamal026/libzip/tree/2eb9279fa5a62c1007d685587dbe69fc68582328/contribution-proof/2026-10-30-required-test-dependencies) are on a separate proof branch and are not part of this seven-file source diff.

## Additional Context

The `nihtest --version` check validates the selected launcher's Python runtime without requiring a separate Python executable that could differ from the launcher's interpreter. It is bounded by a 30-second timeout and runs only in strict regression-test builds.
