import copy
import unittest

import compare


class ComparisonAdmissionTests(unittest.TestCase):
    def test_feature_directive(self):
        for text, expected in (
            ("#define HAVE_LIBLZMA\n", True),
            ("#define\tHAVE_LIBLZMA \n", True),
            ("/* #undef HAVE_LIBLZMA */\n", False),
            ("/* #define HAVE_LIBLZMA */\n", False),
            ("#define HAVE_LIBLZMA 0\n", False),
            ("#define HAVE_LIBLZMA_EXTRA\n", False),
            ("", False),
        ):
            with self.subTest(text=text):
                self.assertEqual(bool(compare.LIBLZMA_DEFINE.search(text)), expected)

    def test_generated_environment(self):
        directories = ["D:/pinned-xz/bin", "D:/pinned-zlib/bin"]
        inventory = {"tests": [
            {"name": name, "properties": [{
                "name": "ENVIRONMENT",
                "value": ["PATH=D:\\PINNED-XZ\\bin;D:\\pinned-zlib\\bin;C:\\Windows"],
            }]}
            for name in sorted(compare.TESTS)
        ]}
        compare.verify_test_environment(inventory, directories)
        for mutation in ("absent", "missing-xz", "wrong-variant", "duplicate-path", "missing-test", "duplicate-test"):
            with self.subTest(mutation=mutation):
                altered = copy.deepcopy(inventory)
                first = altered["tests"][0]
                if mutation == "absent":
                    first["properties"] = []
                elif mutation == "missing-xz":
                    first["properties"][0]["value"] = ["PATH=D:/pinned-zlib/bin"]
                elif mutation == "wrong-variant":
                    first["properties"][0]["value"] = ["PATH=D:/other-xz/bin;D:/pinned-zlib/bin"]
                elif mutation == "duplicate-path":
                    first["properties"][0]["value"] *= 2
                elif mutation == "missing-test":
                    altered["tests"].pop()
                elif mutation == "duplicate-test":
                    altered["tests"].append(copy.deepcopy(first))
                with self.assertRaises(RuntimeError):
                    compare.verify_test_environment(altered, directories)


if __name__ == "__main__":
    unittest.main()
