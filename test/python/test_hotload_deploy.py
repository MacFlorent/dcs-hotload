"""Tests of skills/piloting-dcs-hotload/scripts/hotload-deploy.py, the deploy script of the plugin.

    python -m unittest discover -s test/python
"""
import contextlib
import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True   # the script is loaded from the plugin's folder: leave no __pycache__

spec = importlib.util.spec_from_file_location(
    "hotload_deploy", ROOT / "skills" / "piloting-dcs-hotload" / "scripts" / "hotload-deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class Deploy(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="hotload-deploy-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def deployed(self):
        return self.dir / "dcs-hotload"

    def set_version(self, version):
        lua = self.deployed() / "dcs-hotload.lua"
        text = lua.read_text(encoding="utf-8")
        current = deploy.lua_version(lua)
        lua.write_text(text.replace(f'Hotload.version = "{current}"', f'Hotload.version = "{version}"'),
                       encoding="utf-8")

    def test_shipped_list_is_the_release_list(self):
        self.assertEqual(deploy.shipped(), ["dcs-hotload.lua", "README.md", "LICENSE.md", "bin", "examples"])

    def test_fresh(self):
        self.assertEqual(deploy.main(["--mission", str(self.dir)]), deploy.OK)
        for path in deploy.shipped():
            self.assertTrue((self.deployed() / path).exists(), path)
        for folder in ("user-lib", "user-f10", "user-inbox", "user-outbox"):
            self.assertTrue((self.deployed() / folder).is_dir(), folder)
        self.assertFalse((self.deployed() / "user-scripts").exists())
        self.assertFalse((self.deployed() / "skills").exists())
        self.assertEqual(deploy.lua_version(self.deployed() / "dcs-hotload.lua"), deploy.plugin_version())

    def test_up_to_date_changes_nothing(self):
        deploy.main(["--mission", str(self.dir)])
        marker = self.deployed() / "dcs-hotload.lua"
        stamp = marker.stat().st_mtime_ns
        self.assertEqual(deploy.main(["--mission", str(self.dir)]), deploy.OK)
        self.assertEqual(marker.stat().st_mtime_ns, stamp)

    def test_recreates_missing_user_folders_on_a_current_copy(self):
        deploy.main(["--mission", str(self.dir)])
        (self.deployed() / "user-inbox").rmdir()
        self.assertEqual(deploy.main(["--mission", str(self.dir)]), deploy.OK)
        self.assertTrue((self.deployed() / "user-inbox").is_dir())

    def test_the_copy_holds_the_setup_script_and_its_guard(self):
        deploy.main(["--mission", str(self.dir)])
        self.assertTrue((self.deployed() / "bin" / "hotload-setup.py").is_file())
        self.assertTrue((self.deployed() / "bin" / "boot-guard.lua").is_file())

    def test_older_waits_for_a_decision_then_keeps_user_files(self):
        deploy.main(["--mission", str(self.dir)])
        self.set_version("0.0.1")
        (self.deployed() / "user-lib" / "mine.lua").write_text("return 1", encoding="utf-8")
        (self.deployed() / "user-outbox" / "x.lua").write_text("return 2", encoding="utf-8")

        self.assertEqual(deploy.main(["--mission", str(self.dir)]), deploy.DECIDE)
        self.assertEqual(deploy.lua_version(self.deployed() / "dcs-hotload.lua"), "0.0.1")

        self.assertEqual(deploy.main(["--mission", str(self.dir), "--update"]), deploy.OK)
        self.assertEqual(deploy.lua_version(self.deployed() / "dcs-hotload.lua"), deploy.plugin_version())
        self.assertEqual((self.deployed() / "user-lib" / "mine.lua").read_text(encoding="utf-8"), "return 1")
        self.assertEqual((self.deployed() / "user-outbox" / "x.lua").read_text(encoding="utf-8"), "return 2")

    def test_an_older_copy_prompts_on_stderr(self):
        deploy.main(["--mission", str(self.dir)])
        self.set_version("0.0.1")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = deploy.main(["--mission", str(self.dir)])
        self.assertEqual(code, deploy.DECIDE)
        self.assertIn("rerun with --update", err.getvalue())
        self.assertNotIn("the user", out.getvalue() + err.getvalue())   # temp paths hold "Users"
        self.assertTrue(all(line.startswith("hotload-deploy: ") for line in err.getvalue().splitlines()))

    def test_update_over_user_scripts_says_to_rename_it_and_adds_no_empty_user_f10(self):
        deploy.main(["--mission", str(self.dir)])
        self.set_version("1.3.0")
        (self.deployed() / "user-f10").rmdir()
        (self.deployed() / "user-scripts").mkdir()
        (self.deployed() / "user-scripts" / "a.lua").write_text("return 1", encoding="utf-8")

        with mock.patch("builtins.print") as printed:
            self.assertEqual(deploy.main(["--mission", str(self.dir), "--update"]), deploy.OK)
        self.assertFalse((self.deployed() / "user-f10").exists())
        self.assertTrue((self.deployed() / "user-scripts" / "a.lua").exists())
        self.assertIn("rename user-scripts/ to user-f10/", " ".join(str(c) for c in printed.call_args_list))

    def test_newer_is_left_alone(self):
        deploy.main(["--mission", str(self.dir)])
        self.set_version("99.0.0")
        self.assertEqual(deploy.main(["--mission", str(self.dir), "--update"]), deploy.FAIL)
        self.assertEqual(deploy.lua_version(self.deployed() / "dcs-hotload.lua"), "99.0.0")

    def test_version_order(self):
        self.assertLess(deploy.version_key("1.9.0"), deploy.version_key("1.10.0"))

    def test_usage(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(deploy.main(["--nonsense"]), deploy.USAGE)


if __name__ == "__main__":
    unittest.main()
