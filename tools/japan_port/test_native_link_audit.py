"""Pure unit tests for archive-wide undefined-symbol reporting."""
import unittest

try:
    from .native_link_audit import parse_nm, classify
except ImportError:
    from native_link_audit import parse_nm, classify


class NativeLinkAuditTests(unittest.TestCase):
    def test_archive_output_and_internal_resolution(self):
        sample = """archive.a[funcs_0.o]:
internal T 00000000 00000010
osRecvMesg_recomp U
internal U
__assert_fail U
archive.a[funcs_1.o]:
osRecvMesg_recomp U
get_function U
"""
        defined, undefined = parse_nm(sample)
        self.assertEqual(defined, {"internal"})
        self.assertEqual(undefined, {
            "internal", "osRecvMesg_recomp", "__assert_fail", "get_function"
        })
        self.assertEqual(undefined - defined, {
            "osRecvMesg_recomp", "__assert_fail", "get_function"
        })

    def test_categories(self):
        self.assertEqual(classify("osRecvMesg_recomp"), "n64_host_runtime")
        self.assertEqual(classify("__assert_fail"), "libc_or_math")
        self.assertEqual(classify("section_addresses"), "recomp_dispatch_or_platform")
        self.assertEqual(classify("unexpected_symbol"), "unclassified")

    def test_provider_defined_symbols(self):
        produced = """native.a[f.o]:
osPiStartDma_recomp U
osAiGetLength_recomp U
"""
        provider = """runtime.a[pi.o]:
osPiStartDma_recomp T 00000000 0000000C
"""
        _, missing = parse_nm(produced)
        provided, _ = parse_nm(provider)
        self.assertEqual(missing - provided, {"osAiGetLength_recomp"})


if __name__ == "__main__":
    unittest.main()
