"""Tests of bin/hotload.py, the mailbox client: its Lua data reader, its waits and its command line.

The mission is a FakeMission: it plays hotload on real files in a temporary folder (pickup, runs,
Hotload.stop, the heartbeat), under a fake clock the client's sleep advances. No test sleeps for real.

    python -m unittest discover -s test/python
"""

import contextlib
import io
import json
import math
import os
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True  # bin/ ships as it is: no __pycache__ in it
sys.path.insert(0, str(REPO / "bin"))
import hotload  # noqa: E402

STOP = re.compile(r'^return Hotload\.stop\("inbox/(.+)"\)$')


class FakeMission:
    """hotload's side of the mailbox, on real files. A command's behaviour is scripted by its code."""

    REAL_LIMIT = 1000

    def __init__(self, root):
        self.root = Path(root)
        (self.root / "user-inbox").mkdir(parents=True)
        (self.root / "user-outbox").mkdir()
        self.real = 0.0
        self.sim = 5.0
        self.mission = "fake-mission"
        self.paused = False
        self.alive = True
        self.scripts = {}  # code -> (sim seconds or None for never, status, result, error)
        self.active = {}  # name -> sim time it ends at, or None
        self.code_of, self.started = {}, {}  # name -> its code, its start
        self.sent = []  # codes picked up, in order
        self.poll()

    def script(self, code, seconds=1.0, status="done", result=None, error=None):
        self.scripts[code] = (seconds, status, result, error)

    def restart(self, sim=0.0, mission=None):
        self.sim = sim
        self.active = {}
        self.mission = mission or self.mission

    # the client's clock
    def clock(self):
        return self.real

    def sleep(self, seconds):
        self.real += seconds
        if self.real > self.REAL_LIMIT:  # a wait that never ends fails the test rather than hang it
            raise AssertionError("still waiting after %g fake real seconds" % self.REAL_LIMIT)
        if self.alive and not self.paused:
            self.sim += seconds
            self.poll()

    # hotload
    def _write(self, name, record, header="result"):
        text = "-- dcs-hotload %s\n%s" % (header, hotload.dump(record))
        (self.root / "user-outbox" / name).write_text(text, encoding="utf-8")

    def poll(self):
        for name, ends in list(self.active.items()):
            if ends is not None and self.sim >= ends:
                seconds, status, result, error = self.scripts.get(self.code_of[name], (1.0, "done", None, None))
                self._finish(name, status, result, error)
        for path in sorted((self.root / "user-inbox").glob("*.lua")):
            if not (self.root / "user-outbox" / path.name).exists():
                self._pick_up(path)
        runs = {"inbox/" + name[:-4]: self.started[name] for name in self.active}
        self._write("_heartbeat.lua", {"mission": self.mission, "runs": runs, "time": self.sim,
                                       "version": "3.0.0"}, "heartbeat")

    def _pick_up(self, path):
        code = path.read_text(encoding="utf-8").strip()
        name = path.name
        self.sent.append(code)
        self.code_of[name], self.started[name] = code, self.sim
        self._write(name, {"label": "inbox/" + name[:-4], "status": "started", "started": self.sim})
        stop = STOP.match(code)
        if stop:
            target = stop.group(1) + ".lua"
            hit = target in self.active
            if hit:
                self._finish(target, "stopped", None, None)
            self.active[name] = None
            self._finish(name, "done", hit, None)
            return
        seconds = self.scripts.get(code, (1.0,))[0]
        self.active[name] = None if seconds is None else self.sim + seconds

    def _finish(self, name, status, result, error):
        self.active.pop(name, None)
        started = self.started[name]
        self._write(name, {"label": "inbox/" + name[:-4], "status": status, "started": started,
                           "finished": self.sim, "duration": self.sim - started, "result": result,
                           "error": error, "traceback": "stack" if error else None})

    def files(self):
        return sorted(p.name for p in (self.root / "user-inbox").iterdir()) + \
            sorted(p.name for p in (self.root / "user-outbox").iterdir() if p.name != "_heartbeat.lua")


class FakeWorldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.mission = FakeMission(Path(self.tmp.name) / "dcs-hotload")
        self.said = []
        self.mailbox = hotload.Mailbox(self.mission.root)

    def driver(self, journal=None, after=None):
        """A Driver on the fake clock. `after(real)` is called at each sleep, to change the world."""
        mission = self.mission

        def sleep(seconds):
            mission.sleep(seconds)
            if after:
                after(mission.real)

        return hotload.Driver(self.mailbox, journal=journal, say=self.said.append, clock=mission.clock,
                              sleep=sleep)


class ParseTest(unittest.TestCase):
    def test_an_outbox(self):
        text = ('-- dcs-hotload result\nreturn {\n  ["duration"] = 0.1,\n  ["label"] = "inbox/x",\n'
                '  ["result"] = {\n    [1] = "a",\n    [2] = true,\n  },\n  ["status"] = "done",\n}\n')
        self.assertEqual(hotload.parse(text), {"duration": 0.1, "label": "inbox/x", "result": ["a", True],
                                               "status": "done"})

    def test_bare_keys(self):
        self.assertEqual(hotload.parse('return { tier = "minimal", timeout = 120 }'),
                         {"tier": "minimal", "timeout": 120})

    def test_q_escapes(self):  # what %q writes: \" \\ backslash-newline \r \000
        self.assertEqual(hotload.parse('return "a\\"b\\\\c\\\nd\\re\\000"'), 'a"b\\c\nd\re\x00')

    def test_special_numbers(self):
        value = hotload.parse("return { math.huge, -math.huge, 0/0, -3, 1e-05 }")
        self.assertEqual(value[:2], [math.inf, -math.inf])
        self.assertTrue(math.isnan(value[2]))
        self.assertEqual(value[3:], [-3, 1e-05])

    def test_a_sparse_table_stays_a_dict(self):
        self.assertEqual(hotload.parse("return { [1] = 1, [3] = 3 }"), {1: 1, 3: 3})

    def test_an_empty_table_is_a_dict(self):
        self.assertEqual(hotload.parse("return {}"), {})

    def test_half_written_text_raises(self):
        with self.assertRaises(hotload.LuaDataError):
            hotload.parse('return {\n  ["status"] = "do')

    def test_dump_reads_back(self):
        value = {"a": [1, 2.5, "x\ny\"z"], 3: True, "n": -math.inf}
        self.assertEqual(hotload.parse(hotload.dump(value)), value)


class MailboxTest(FakeWorldTest):
    def test_an_absent_or_torn_outbox_is_none(self):
        self.assertIsNone(self.mailbox.outcome("nope"))
        (self.mission.root / "user-outbox" / "torn.lua").write_text('return { ["status"] = "st', encoding="utf-8")
        self.assertIsNone(self.mailbox.outcome("torn"))

    def test_the_heartbeat_and_its_modification_time(self):
        beat, mtime = self.mailbox.heartbeat()
        self.assertEqual(beat["mission"], "fake-mission")
        self.assertIsInstance(mtime, int)

    def test_no_heartbeat_is_none(self):
        (self.mission.root / "user-outbox" / "_heartbeat.lua").unlink()
        self.assertIsNone(self.mailbox.heartbeat())

    def test_send_leaves_no_tmp(self):
        self.mailbox.send("c", "return 1")
        self.assertEqual(sorted(p.name for p in (self.mission.root / "user-inbox").iterdir()), ["c.lua"])


class CallTest(FakeWorldTest):
    def test_done_with_its_result_and_the_files_cleared(self):
        self.mission.script("return 42", seconds=2, result=42)
        outcome = self.driver().call("c1", "return 42", timeout=10)
        self.assertEqual((outcome.status, outcome.result), ("done", 42))
        self.assertEqual(outcome.duration, 2)
        self.assertEqual(self.mission.files(), [])

    def test_keep_leaves_the_files(self):
        self.driver().call("c1", "return 1", timeout=10, keep=True)
        self.assertEqual(self.mission.files(), ["c1.lua", "c1.lua"])

    def test_fail_carries_the_error_and_traceback(self):
        self.mission.script("error('x')", status="fail", error="boom")
        outcome = self.driver().call("c1", "error('x')", timeout=10)
        self.assertEqual((outcome.status, outcome.error, outcome.traceback), ("fail", "boom", "stack"))

    def test_a_pause_does_not_time_a_run_out(self):
        self.mission.script("w", seconds=8)

        def pause(real):
            self.mission.paused = 3 <= real < 40

        outcome = self.driver(after=pause).call("c1", "w", timeout=10)
        self.assertEqual(outcome.status, "done")
        self.assertEqual(sum("no heartbeat" in s for s in self.said), 1)

    def test_past_its_timeout_a_run_is_stopped(self):
        self.mission.script("hang", seconds=None)
        outcome = self.driver().call("c1", "hang", timeout=5)
        self.assertEqual(outcome.status, "timeout")
        self.assertIn("5", outcome.error)
        self.assertTrue(any(STOP.match(code) for code in self.mission.sent))
        self.assertEqual(self.mission.files(), [])

    def test_never_picked_up_times_out_in_sim_time(self):
        # The mission runs, but an unreadable outbox is already there, so the command never runs.
        (self.mission.root / "user-outbox" / "c1.lua").write_text("", encoding="utf-8")
        outcome = self.driver().call("c1", "x", timeout=5)
        self.assertEqual(outcome.status, "timeout")
        self.assertLess(self.mission.real, 10)

    def test_a_restart_under_a_run_is_lost(self):
        self.mission.script("hang", seconds=None)

        def restart(real):
            if real == 3:
                self.mission.restart(sim=0)

        outcome = self.driver(after=restart).call("c1", "hang", timeout=100)
        self.assertEqual(outcome.status, "lost")
        self.assertLess(self.mission.real, 10)

    def test_a_restart_already_past_the_start_is_lost(self):
        self.mission.script("hang", seconds=None)

        def restart(real):
            if real == 3:
                self.mission.restart(sim=1000)

        outcome = self.driver(after=restart).call("c1", "hang", timeout=10000)
        self.assertEqual(outcome.status, "lost")

    def test_another_mission_under_a_run_is_lost(self):
        self.mission.script("hang", seconds=None)

        def restart(real):
            if real == 3:
                self.mission.restart(sim=50, mission="other")

        self.assertEqual(self.driver(after=restart).call("c1", "hang", timeout=1000).status, "lost")

    def test_a_restart_before_pickup_is_not_lost(self):
        self.mission.alive = False

        def start(real):
            if real == 2:
                self.mission.restart(sim=0)
                self.mission.alive = True

        self.assertEqual(self.driver(after=start).call("c1", "return 1", timeout=10).status, "done")

    def test_silence_past_its_cap_keeps_the_files(self):
        self.mission.script("w", seconds=30)

        def die(real):
            if real == 2:
                self.mission.alive = False

        outcome = self.driver(after=die).call("c1", "w", timeout=100, silence=20)
        self.assertEqual(outcome.status, "silent")
        self.assertLess(self.mission.real, 30)
        self.assertEqual(self.mission.files(), ["c1.lua", "c1.lua"])

    def test_without_a_cap_silence_waits(self):
        self.mission.script("w", seconds=4)

        def blackout(real):
            self.mission.alive = not (2 <= real < 200)

        self.assertEqual(self.driver(after=blackout).call("c1", "w", timeout=100).status, "done")

    def test_a_refused_command(self):
        self.mission.script("bad", status="refused", error="syntax")
        self.assertEqual(self.driver().call("c1", "bad", timeout=10).status, "refused")


class JournalTest(FakeWorldTest):
    def setUp(self):
        super().setUp()
        self.journal = Path(self.tmp.name) / "results" / "journal.jsonl"

    def entries(self):
        return [json.loads(line) for line in self.journal.read_text(encoding="utf-8").splitlines()]

    def test_sent_then_ended(self):
        self.mission.script("return 7", result={"a": 1, 2: "b"})
        outcome = self.driver(self.journal).run("k1", "lane", "return 7", timeout=10)
        self.assertEqual(outcome.result, {"a": 1, 2: "b"})
        sent, ended = self.entries()
        self.assertEqual((sent["key"], sent["state"], ended["state"]), ("k1", "sent", "ended"))
        self.assertTrue(sent["name"].startswith("lane-"))

    def test_an_ended_key_is_not_sent_again(self):
        self.mission.script("return 7", result={"a": 1, 2: "b"})
        self.driver(self.journal).run("k1", "lane", "return 7", timeout=10)
        again = self.driver(self.journal).run("k1", "lane", "return 7", timeout=10)
        self.assertEqual(again.result, {"a": 1, 2: "b"})
        self.assertEqual(self.mission.sent, ["return 7"])

    def test_a_sent_key_is_waited_on_under_its_name(self):
        self.mission.script("w", seconds=3, result=1)
        self.mailbox.send("lane-old", "w")
        self.journal.parent.mkdir()
        self.journal.write_text(json.dumps({"key": "k1", "name": "lane-old", "sent_at": 5, "state": "sent"})
                                + "\n{\"torn", encoding="utf-8")
        outcome = self.driver(self.journal).run("k1", "lane", "w", timeout=10)
        self.assertEqual(outcome.result, 1)
        self.assertEqual(self.mission.sent, ["w"])

    def test_a_silent_wait_is_not_journalled_as_ended(self):
        self.mission.alive = False
        outcome = self.driver(self.journal).run("k1", "lane", "w", timeout=10, silence=5)
        self.assertEqual(outcome.status, "silent")
        self.assertEqual([e["state"] for e in self.entries()], ["sent"])

    def test_unique_names(self):
        driver = self.driver(self.journal)
        driver.run("k1", "lane", "return 1", timeout=10)
        driver.run("k2", "lane", "return 1", timeout=10)
        names = [e["name"] for e in self.entries() if e["state"] == "sent"]
        self.assertEqual(len(set(names)), 2)


class CommandLineTest(FakeWorldTest):
    def main(self, *argv, after=None):
        mission = self.mission

        def sleep(seconds):
            mission.sleep(seconds)
            if after:
                after(mission.real)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hotload.main(list(argv), clock=mission.clock, sleep=sleep)
        return code, out.getvalue(), err.getvalue()

    def test_run_prints_the_outbox_and_exits_0(self):
        self.mission.script("return 42", result=42)
        code, out, _ = self.main("run", "--root", str(self.mission.root), "-e", "return 42")
        self.assertEqual(code, 0)
        self.assertEqual(hotload.parse(out)["result"], 42)
        self.assertEqual(self.mission.files(), [])

    def test_run_a_file(self):
        script = Path(self.tmp.name) / "s.lua"
        script.write_text("return 42\n", encoding="utf-8")
        self.mission.script("return 42", result=42)
        self.assertEqual(self.main("run", "--root", str(self.mission.root), str(script))[0], 0)

    def test_run_exit_codes(self):
        root = str(self.mission.root)
        self.mission.script("fail", status="fail", error="boom")
        self.mission.script("hang", seconds=None)
        self.assertEqual(self.main("run", "--root", root, "-e", "fail")[0], 1)
        self.assertEqual(self.main("run", "--root", root, "--timeout", "3", "-e", "hang")[0], 2)

    def test_run_lost_exits_4(self):
        self.mission.script("hang", seconds=None)

        def restart(real):
            if real == 3:
                self.mission.restart(sim=0)

        code, _, err = self.main("run", "--root", str(self.mission.root), "-e", "hang", after=restart)
        self.assertEqual(code, 4)
        self.assertIn("restarted", err)

    def test_run_silent_exits_5_and_says_how_to_stop(self):
        self.mission.alive = False
        code, _, err = self.main("run", "--root", str(self.mission.root), "--name", "n1", "--silence", "15",
                                 "-e", "x")
        self.assertEqual(code, 5)
        self.assertIn('Hotload.stop("inbox/n1")', err)

    def test_run_usage_errors_exit_3(self):
        root = str(self.mission.root)
        self.assertEqual(self.main("run", "--root", root)[0], 3)
        self.assertEqual(self.main("run", "--root", self.tmp.name, "-e", "x")[0], 3)
        self.mailbox.send("taken", "x")
        self.assertEqual(self.main("run", "--root", root, "--name", "taken", "-e", "x")[0], 3)
        self.assertEqual(self.main("nope")[0], 3)

    def test_status_advancing_exits_0(self):
        code, out, _ = self.main("status", "--root", str(self.mission.root))
        self.assertEqual(code, 0)
        self.assertIn("fake-mission", out)
        self.assertIn("advancing", out)

    def test_status_still_exits_1(self):
        self.mission.paused = True
        code, out, _ = self.main("status", "--root", str(self.mission.root))
        self.assertEqual(code, 1)
        self.assertIn("still", out)

    def test_status_without_a_heartbeat_exits_1(self):
        (self.mission.root / "user-outbox" / "_heartbeat.lua").unlink()
        self.assertEqual(self.main("status", "--root", str(self.mission.root))[0], 1)

    def test_the_root_defaults_to_hotload_root_then_above_bin(self):
        with mock.patch.dict(os.environ, {"HOTLOAD_ROOT": str(self.mission.root)}):
            self.assertEqual(self.main("status")[0], 0)
        with mock.patch.dict(os.environ):
            os.environ.pop("HOTLOAD_ROOT", None)
            self.assertEqual(hotload.default_root(), REPO)

    def test_log_since_the_last_ready(self):
        log = Path(self.tmp.name) / "dcs.log"
        line = "2026-11-02 20:38:48.773 INFO    SCRIPTING (Main): HOTLOAD: %s\n"
        log.write_text(line % "ready old" + line % "start inbox/a" + line % "ready new" + "noise\n"
                       + line % "start inbox/b" + line % "done inbox/b", encoding="utf-8")
        code, out, err = self.main("log", "--log", str(log))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["2026-11-02 20:38:48.773 ready new", "2026-11-02 20:38:48.773 start inbox/b",
                                            "2026-11-02 20:38:48.773 done inbox/b"])
        self.assertIn("UTC", err)
        self.assertEqual(self.main("log", "--log", str(log), "done")[1].count("\n"), 1)

    def test_log_errors_exit_3(self):
        log = Path(self.tmp.name) / "dcs.log"
        log.write_text("nothing\n", encoding="utf-8")
        self.assertEqual(self.main("log", "--log", str(log))[0], 3)
        self.assertEqual(self.main("log", "--log", str(log) + ".absent")[0], 3)

    def test_check(self):
        miz = Path(self.tmp.name) / "tempMission.miz"
        with zipfile.ZipFile(miz, "w") as archive:
            archive.writestr("l10n/DEFAULT/s.lua", "return 1\n")
        same, other = Path(self.tmp.name) / "same.lua", Path(self.tmp.name) / "other.lua"
        same.write_bytes(b"return 1\n")
        other.write_bytes(b"return 2\n")
        code, out, _ = self.main("check", "--miz", str(miz), "s.lua", str(same))
        self.assertEqual((code, out.split(":")[0]), (0, "MATCH"))
        code, out, _ = self.main("check", "--miz", str(miz), "s.lua", str(other))
        self.assertEqual((code, out.split(":")[0]), (1, "DIFFERENT"))
        code, out, _ = self.main("check", "--miz", str(miz), "t.lua", str(same))
        self.assertEqual((code, out.split(":")[0]), (1, "NOT EMBEDDED"))
        self.assertEqual(self.main("check", "--miz", str(miz) + ".absent", "s.lua", str(same))[0], 3)


if __name__ == "__main__":
    unittest.main()
