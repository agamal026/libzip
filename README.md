# libzip Windows x86 XZ comparison

This isolated diagnostic supports the Windows CI investigation requested in
[libzip PR 576](https://github.com/nih-at/libzip/pull/576). It is separate from
the existing pull-request branch.

Mainline AppVeyor build [1.0.1108](https://ci.appveyor.com/project/nih-at/libzip/builds/54765284)
reported 193 x86 test cases: 186 passed, two failed and five skipped, with
MSVC 19.29.30159.0 and liblzma 5.8.1. Only the two XZ conversion tests failed.
XZ 5.8.2's release notes describe a workaround for
old-MSVC 32-bit CRC miscompilation; this comparison tests that explanation.

One Windows 2022 runner builds all dependencies with the v142 toolset and
requires MSVC 19.29 plus 32-bit objects. Source revisions are pinned. Three
variants use XZ 5.8.1 with CLMUL CRC enabled, the same source with CLMUL CRC
disabled, and XZ 5.8.3 with its normal option and upstream compiler workaround.
The latter is not a claim that CLMUL remains active. XZ 5.8.3 is the version
in the vcpkg commit already used by upstream libzip's GitHub workflow.

Each variant runs the same five existing tests: crypto clearing, both LZMA
conversions, and both XZ conversions. No skipped or missing test is accepted.
The expected differential requires the same two XZ failure signatures and
CTest exit 8 in the old/ON baseline, and all five passing in each treatment.
Infrastructure errors, extra failure bits and different failures do not count.
Commands, timings, source
heads, compiler metadata, CMake caches, DLL hashes and JUnit results are
uploaded as a single artifact even after failure.

The generated CTest environments must include each variant's dependency DLL
directories. They are provided at configure time because libzip records PATH
then, overriding the later test invocation's PATH. A DLL-loading failure is
setup failure, not evidence about compression behavior. The first two runs
are retained: run 35829998405 stopped at an incorrect feature-macro guard;
run 35830895109 reached tests but failed DLL loading in all three variants.

This isolates the dependency behavior on the recorded GitHub runner. The
AppVeyor image, full optional-codec matrix and ARM SDK problem need their own
validation before an AppVeyor-wide fix is claimed.
