"""Compile and run exact injected C++ mode with test stubs (not a full game build)."""
import os
import subprocess
import tempfile
from pathlib import Path
import unittest
import jp_decompressed_runtime_test_v14 as p

HEAD = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <vector>
#include <system_error>
#include <fstream>
#include <cassert>
#define GOEMON_JAPAN_NATIVE
namespace recomp {
struct GameEntry {
    uint64_t rom_hash;
    std::u8string game_id;
    std::string mod_game_id;
    void* decompression_routine;
    bool has_compressed_code;
};
struct Version {};
enum class RomValidationError { Good, IncorrectRom };
static std::filesystem::path root;
inline RomValidationError select_rom(const std::filesystem::path& p, std::u8string& id) {
    if (p.string() != "good" || id != u8"mnsg.jp.decomp-test")
        return RomValidationError::IncorrectRom;
    auto path = root / "mnsg.jp.decomp-test.z64";
    std::ofstream o(path, std::ios::binary);
    o.seekp(33554431);
    o.put('x');
    o.close();
    return RomValidationError::Good;
}
inline bool register_game(const GameEntry&) { return true; }
}
namespace goemon64 { inline std::filesystem::path get_app_folder_path() { return recomp::root; } }
std::vector<recomp::GameEntry> supported_games = {{
    0xD526A3DB80EB7924ULL, u8"mnsg.jp", "mnsg.jp", (void*)0x10, true}};
int main(int argc, char** argv) {
    if (argc >= 2 && std::strcmp(argv[1], "--version") == 0) {
        return EXIT_SUCCESS;
    }
'''
TAIL = r'''
    recomp::Version project_version{};
    assert(project_version.operator& == nullptr); // REPLACE
    recomp::root = std::filesystem::path(std::getenv("JP_V14_FIXTURE_ROOT"));
    // Register supported games and patches
    for (const auto& game : supported_games) {
        recomp::register_game(game);
    }
    if (jpDecompressedTestInput == nullptr) {
        assert(supported_games[0].rom_hash == 0xD526A3DB80EB7924ULL);
        assert(supported_games[0].has_compressed_code);
        assert(supported_games[0].game_id == u8"mnsg.jp");
    } else {
        assert(supported_games[0].rom_hash == 0xC519E0E26FA0D20EULL);
        assert(!supported_games[0].has_compressed_code);
        assert(supported_games[0].decompression_routine == nullptr);
        assert(supported_games[0].game_id == u8"mnsg.jp.decomp-test");
        assert(supported_games[0].mod_game_id == "mnsg.jp");
    }
    return 0;
}
'''


class TestCppV14(unittest.TestCase):
    def test_compiled_control_paths(self):
        # Build a synthetic main using the actual two injected source blocks,
        # no source text supplied by user and no ROM bytes.
        code = HEAD + TAIL.lstrip('\n').replace('    assert(project_version.operator& == nullptr); // REPLACE\n', '')
        code = p.one(code, p.VERSION_ANCHOR, p.VERSION_PATCH, 'version')
        code = p.one(code, p.REGISTER_ANCHOR, p.REGISTER_PATCH, 'register')
        code = code.replace('    recomp::Version project_version{};\n', '    recomp::Version project_version{};\n    (void)project_version;\n')
        # Declare root before mode, so create_directories is safe in fixture.
        code = code.replace('    // Register supported games and patches',
                            '    recomp::root = std::filesystem::path(std::getenv("JP_V14_FIXTURE_ROOT"));\n    // Register supported games and patches')
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            c = work / 'test.cpp'
            exe = work / 'test'
            c.write_text(code)
            r = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            env = {**os.environ, "JP_V14_FIXTURE_ROOT": str(work)}
            baseline = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            alt = subprocess.run([str(exe), '--test-decompressed-jp', 'good'], capture_output=True, text=True, env=env)
            self.assertEqual(alt.returncode, 0, alt.stderr)
            self.assertIn('Accepted exact expected XXH3', alt.stderr)
            bad = subprocess.run([str(exe), '--test-decompressed-jp', 'bad'], capture_output=True, text=True, env=env)
            self.assertNotEqual(bad.returncode, 0)
            malformed = subprocess.run([str(exe), '--test-decompressed-jp'], capture_output=True, text=True, env=env)
            self.assertNotEqual(malformed.returncode, 0)


if __name__ == '__main__':
    unittest.main()