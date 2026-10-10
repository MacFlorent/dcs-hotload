"""Tests of skills/piloting-dcs-hotload/scripts/hotload-setup.py, the setup helper of the plugin.

    python -m unittest discover -s test/python

The round trip over every mission that comes with DCS World takes about a minute and a half, so
it runs only on request, with HOTLOAD_TEST_DCS_MISSIONS=1 and a DCS install found (DCS_INSTALL, or
one of the usual places). Run it after changing the table reader or writer.
"""
import importlib.util
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "empty-caucasus.miz"

spec = importlib.util.spec_from_file_location(
    "hotload_setup", ROOT / "skills" / "piloting-dcs-hotload" / "scripts" / "hotload-setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def miz_entries(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()}


class Scratch(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hotload-setup-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)


# ── The Mission Editor's Lua table format ───────────────────────────────────────────────────────

SPACES = '''mission =
{
    ["trig"] =
    {
        ["actions"] =
        {
            [1] = "a_do_script(\\"x\\");",
        }, -- end of ["actions"]
        ["flag"] =
        {
        }, -- end of ["flag"]
    }, -- end of ["trig"]
    ["x"] = -0.0051662641880086,
    ["big"] = 1e+20,
    ["on"] = true,
    ["off"] = false,
} -- end of mission
'''.replace(" =" + chr(10), " = " + chr(10))   # the Mission Editor writes "= " before a table


class TableFormat(unittest.TestCase):
    def test_round_trip_is_exact_with_tabs(self):
        text = miz_entries(FIXTURE)["mission"].decode("utf-8")
        name, value = setup.lua_load(text)
        self.assertEqual(name, "mission")
        self.assertEqual(setup.lua_dump(name, value, setup.Style.of(text)), text)

    def test_round_trip_is_exact_with_spaces_and_open_empty_tables(self):
        name, value = setup.lua_load(SPACES)
        self.assertEqual(setup.lua_dump(name, value, setup.Style.of(SPACES)), SPACES)

    def test_values(self):
        _, mission = setup.lua_load(SPACES)
        self.assertEqual(mission["trig"]["actions"][1], 'a_do_script("x");')
        self.assertEqual(mission["trig"]["flag"], {})
        self.assertIsInstance(mission["x"], setup.Num)
        self.assertEqual(str(mission["x"]), "-0.0051662641880086")
        self.assertEqual(str(mission["big"]), "1e+20")
        self.assertIs(mission["on"], True)
        self.assertIs(mission["off"], False)

    def test_string_escapes(self):
        text = 'x = \n{\n    [1] = "q\\" b\\\\ nl\\\nend \\r \\000 \\t",\n} -- end of x\n'
        _, x = setup.lua_load(text)
        self.assertEqual(x[1], 'q" b\\ nl\nend \r \0 \t')

    def test_dump_escapes_as_lua_q(self):
        value = {1: 'q" b\\ nl\nend \r \0'}
        out = setup.lua_dump("x", value, setup.Style("\t", True))
        self.assertIn('[1] = "q\\" b\\\\ nl\\\nend \\r \\000",', out)
        self.assertEqual(setup.lua_load(out)[1], value)

    def test_refuses_what_it_cannot_read(self):
        with self.assertRaises(setup.FormatError):
            setup.lua_load("mission = { [1] = some_function() }")


@unittest.skipUnless(os.environ.get("HOTLOAD_TEST_DCS_MISSIONS") and setup.find_dcs(None),
                     "set HOTLOAD_TEST_DCS_MISSIONS=1, with a DCS install found")
class DcsMissions(unittest.TestCase):
    """Every mission that comes with DCS World reads and writes back to the same text."""

    def test_round_trip_on_every_dcs_mission(self):
        dcs = setup.find_dcs(None)
        failures, count = [], 0
        for miz in sorted(dcs.rglob("*.miz")):
            try:
                with zipfile.ZipFile(miz) as z:
                    text = z.read("mission").decode("utf-8")
            except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
                continue
            count += 1
            try:
                name, value = setup.lua_load(text)
                if setup.lua_dump(name, value, setup.Style.of(text)) != text:
                    failures.append(f"{miz}: text differs")
            except setup.FormatError as e:
                failures.append(f"{miz}: {e}")
        self.assertGreater(count, 0)
        self.assertEqual(failures, [], f"{len(failures)} of {count} missions")
        print(f"{count} DCS missions read and written back unchanged")


# ── The boot line in a .miz ─────────────────────────────────────────────────────────────────────

class BootLine(Scratch):
    def setUp(self):
        super().setUp()
        self.miz = self.dir / "m.miz"
        shutil.copy(FIXTURE, self.miz)
        self.lua = r"D:\Missions\M\dcs-hotload\dcs-hotload.lua"

    def test_absent_in_an_empty_mission(self):
        self.assertEqual(setup.find_boot(setup.Miz.read(self.miz)), [])

    def test_added_as_a_mission_start_trigger(self):
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, self.lua)
        miz.write(self.miz)

        mission = setup.Miz.read(self.miz).mission
        rule = mission["trigrules"][1]
        self.assertEqual(rule["predicate"], "triggerStart")
        self.assertEqual(rule["actions"][1]["predicate"], "a_do_script")
        self.assertEqual(rule["actions"][1]["text"], setup.boot_line(self.lua))
        trig = mission["trig"]
        self.assertEqual(trig["actions"][1], 'a_do_script(%s);' % setup.lua_quote(setup.boot_line(self.lua)))
        self.assertEqual(trig["conditions"][1], "return(true)")
        self.assertIs(trig["flag"][1], True)
        self.assertEqual(trig["funcStartup"][1],
                         "if mission.trig.conditions[1]() then mission.trig.actions[1]() end")

    def test_added_after_existing_triggers_index_for_index(self):
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, r"C:\other\dcs-hotload.lua")
        setup.add_boot(miz, self.lua)
        self.assertEqual(sorted(miz.mission["trigrules"]), [1, 2])
        self.assertEqual(sorted(miz.mission["trig"]["funcStartup"]), [1, 2])
        self.assertIn("conditions[2]", miz.mission["trig"]["funcStartup"][2])

    def test_found_once_added(self):
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, self.lua)
        self.assertEqual(setup.find_boot(miz), [("trigger 1", self.lua)])

    def test_found_in_an_embedded_script(self):
        miz = setup.Miz.read(self.miz)
        miz.entries["l10n/DEFAULT/boot.lua"] = b'-- mission scripts\ndofile([[' + self.lua.encode() + b']])\n'
        self.assertEqual(setup.find_boot(miz), [("embedded l10n/DEFAULT/boot.lua", self.lua)])

    def test_found_with_a_quoted_path(self):
        miz = setup.Miz.read(self.miz)
        miz.entries["l10n/DEFAULT/boot.lua"] = b'dofile("D:/Missions/M/dcs-hotload/dcs-hotload.lua")\n'
        self.assertEqual(setup.find_boot(miz), [("embedded l10n/DEFAULT/boot.lua",
                                                  "D:/Missions/M/dcs-hotload/dcs-hotload.lua")])

    def test_rewritten_in_place_when_pointing_elsewhere(self):
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, r"C:\old\dcs-hotload\dcs-hotload.lua")
        setup.retarget_boot(miz, r"C:\old\dcs-hotload\dcs-hotload.lua", self.lua)
        self.assertEqual(setup.find_boot(miz), [("trigger 1", self.lua)])
        self.assertNotIn("old", miz.mission["trig"]["actions"][1])
        self.assertEqual(len(miz.mission["trigrules"]), 1)

    def test_other_entries_unchanged(self):
        before = miz_entries(self.miz)
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, self.lua)
        miz.write(self.miz)
        after = miz_entries(self.miz)
        self.assertEqual(list(after), list(before))
        for name in before:
            if name != "mission":
                self.assertEqual(after[name], before[name], name)

    def test_same_path_matches_whatever_the_case_and_slashes(self):
        self.assertTrue(setup.same_path(r"D:\Missions\M\dcs-hotload\dcs-hotload.lua",
                                        "d:/missions/m/dcs-hotload/dcs-hotload.lua"))
        self.assertFalse(setup.same_path(r"D:\Missions\M\dcs-hotload.lua", r"D:\Missions\N\dcs-hotload.lua"))

    def test_patch_command(self):
        mission_dir = self.dir
        shutil.copy(FIXTURE, mission_dir / "m.miz")
        lua = mission_dir / "dcs-hotload" / "dcs-hotload.lua"

        self.assertEqual(setup.main(["patch-miz", str(mission_dir / "m.miz"), "--mission", str(mission_dir)]),
                         setup.OK)
        self.assertTrue((mission_dir / "m.miz.bak").exists())
        found = setup.find_boot(setup.Miz.read(mission_dir / "m.miz"))
        self.assertEqual(len(found), 1)
        self.assertTrue(setup.same_path(found[0][1], str(lua)))

        # Again: nothing to do.
        before = (mission_dir / "m.miz").read_bytes()
        self.assertEqual(setup.main(["patch-miz", str(mission_dir / "m.miz"), "--mission", str(mission_dir)]),
                         setup.OK)
        self.assertEqual((mission_dir / "m.miz").read_bytes(), before)

    def test_patch_command_asks_before_retargeting(self):
        miz = setup.Miz.read(self.miz)
        setup.add_boot(miz, r"C:\old\dcs-hotload\dcs-hotload.lua")
        miz.write(self.miz)
        args = ["patch-miz", str(self.miz), "--mission", str(self.dir)]
        self.assertEqual(setup.main(args), setup.DECIDE)
        self.assertEqual(setup.main(args + ["--retarget"]), setup.OK)
        self.assertTrue(setup.same_path(setup.find_boot(setup.Miz.read(self.miz))[0][1],
                                        str(self.dir / "dcs-hotload" / "dcs-hotload.lua")))


# ── Deploying the tool into a mission folder ────────────────────────────────────────────────────

class Deploy(Scratch):
    def deployed(self):
        return self.dir / "dcs-hotload"

    def set_version(self, version):
        lua = self.deployed() / "dcs-hotload.lua"
        text = lua.read_text(encoding="utf-8")
        current = setup.lua_version(lua)
        lua.write_text(text.replace(f'Hotload.version = "{current}"', f'Hotload.version = "{version}"'),
                       encoding="utf-8")

    def test_shipped_list_is_the_release_list(self):
        self.assertEqual(setup.shipped(), ["dcs-hotload.lua", "README.md", "LICENSE.md", "bin", "examples"])

    def test_fresh(self):
        self.assertEqual(setup.main(["deploy", "--mission", str(self.dir)]), setup.OK)
        for path in setup.shipped():
            self.assertTrue((self.deployed() / path).exists(), path)
        for folder in ("user-lib", "user-scripts", "user-inbox", "user-outbox"):
            self.assertTrue((self.deployed() / folder).is_dir(), folder)
        self.assertFalse((self.deployed() / "skills").exists())
        self.assertEqual(setup.lua_version(self.deployed() / "dcs-hotload.lua"), setup.plugin_version())

    def test_up_to_date_changes_nothing(self):
        setup.main(["deploy", "--mission", str(self.dir)])
        marker = self.deployed() / "dcs-hotload.lua"
        stamp = marker.stat().st_mtime_ns
        self.assertEqual(setup.main(["deploy", "--mission", str(self.dir)]), setup.OK)
        self.assertEqual(marker.stat().st_mtime_ns, stamp)

    def test_older_waits_for_a_decision_then_keeps_user_files(self):
        setup.main(["deploy", "--mission", str(self.dir)])
        self.set_version("0.0.1")
        (self.deployed() / "user-lib" / "mine.lua").write_text("return 1", encoding="utf-8")
        (self.deployed() / "user-outbox" / "x.lua").write_text("return 2", encoding="utf-8")

        self.assertEqual(setup.main(["deploy", "--mission", str(self.dir)]), setup.DECIDE)
        self.assertEqual(setup.lua_version(self.deployed() / "dcs-hotload.lua"), "0.0.1")

        self.assertEqual(setup.main(["deploy", "--mission", str(self.dir), "--update"]), setup.OK)
        self.assertEqual(setup.lua_version(self.deployed() / "dcs-hotload.lua"), setup.plugin_version())
        self.assertEqual((self.deployed() / "user-lib" / "mine.lua").read_text(encoding="utf-8"), "return 1")
        self.assertEqual((self.deployed() / "user-outbox" / "x.lua").read_text(encoding="utf-8"), "return 2")

    def test_newer_is_left_alone(self):
        setup.main(["deploy", "--mission", str(self.dir)])
        self.set_version("99.0.0")
        self.assertEqual(setup.main(["deploy", "--mission", str(self.dir), "--update"]), setup.FAIL)
        self.assertEqual(setup.lua_version(self.deployed() / "dcs-hotload.lua"), "99.0.0")

    def test_version_order(self):
        self.assertLess(setup.version_key("1.9.0"), setup.version_key("1.10.0"))


# ── Unlocking MissionScripting.lua ──────────────────────────────────────────────────────────────

STOCK = """--Initialization script for the Mission lua Environment (SSE)

dofile('Scripts/ScriptingSystem.lua')

local function sanitizeModule(name)
\t_G[name] = nil
\tpackage.loaded[name] = nil
end

do
\tsanitizeModule('os')
\tsanitizeModule('io')
\tsanitizeModule('lfs')
\t_G['require'] = nil
\t_G['loadlib'] = nil
\t_G['package'] = nil
end
"""


class Unlock(Scratch):
    def setUp(self):
        super().setUp()
        (self.dir / "Scripts" / "Database").mkdir(parents=True)
        self.file = self.dir / "Scripts" / "MissionScripting.lua"
        self.file.write_text(STOCK, encoding="utf-8", newline="\n")

    def test_locked_modules(self):
        self.assertEqual(setup.locked_modules(self.file), ["io", "lfs"])

    def test_asks_first(self):
        self.assertEqual(setup.main(["unlock", "--dcs", str(self.dir)]), setup.DECIDE)
        self.assertEqual(self.file.read_text(encoding="utf-8"), STOCK)

    def test_unlocks_io_and_lfs_only_and_keeps_the_original(self):
        self.assertEqual(setup.main(["unlock", "--dcs", str(self.dir), "--yes"]), setup.OK)
        text = self.file.read_text(encoding="utf-8")
        self.assertIn("\t--sanitizeModule('io')", text)
        self.assertIn("\t--sanitizeModule('lfs')", text)
        self.assertIn("\tsanitizeModule('os')", text)
        self.assertEqual(setup.locked_modules(self.file), [])
        self.assertEqual((self.dir / "Scripts" / "MissionScripting.lua.bak").read_text(encoding="utf-8"), STOCK)

    def test_unlocked_changes_nothing(self):
        setup.main(["unlock", "--dcs", str(self.dir), "--yes"])
        (self.dir / "Scripts" / "MissionScripting.lua.bak").unlink()
        self.assertEqual(setup.main(["unlock", "--dcs", str(self.dir)]), setup.OK)
        self.assertFalse((self.dir / "Scripts" / "MissionScripting.lua.bak").exists())


# ── status ──────────────────────────────────────────────────────────────────────────────────────

class Status(Scratch):
    def setUp(self):
        super().setUp()
        self.dcs = self.dir / "dcs"
        (self.dcs / "Scripts" / "Database").mkdir(parents=True)
        (self.dcs / "Scripts" / "MissionScripting.lua").write_text(STOCK, encoding="utf-8")
        self.mission = self.dir / "mission"
        self.mission.mkdir()
        shutil.copy(FIXTURE, self.mission / "m.miz")
        self.args = ["status", "--mission", str(self.mission), "--dcs", str(self.dcs)]

    def test_reports_what_is_missing(self):
        self.assertEqual(setup.main(self.args), setup.DECIDE)

    def test_all_set(self):
        setup.main(["deploy", "--mission", str(self.mission)])
        setup.main(["unlock", "--dcs", str(self.dcs), "--yes"])
        setup.main(["patch-miz", str(self.mission / "m.miz"), "--mission", str(self.mission)])
        self.assertEqual(setup.main(self.args), setup.OK)

    def test_usage(self):
        self.assertEqual(setup.main(["nonsense"]), setup.USAGE)


if __name__ == "__main__":
    unittest.main()
