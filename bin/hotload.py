#!/usr/bin/env python3
"""hotload.py -- drive a running DCS mission through dcs-hotload's mailbox.

    python hotload.py run    [--root DIR] [--name NAME] [--timeout S] [--silence S] [--keep] (-e LUA | FILE.lua)
    python hotload.py status [--root DIR]               the heartbeat, and whether it is advancing
    python hotload.py log    [--log FILE] [PATTERN]     HOTLOAD lines since the last "ready"
    python hotload.py check  [--miz FILE] SCRIPT SRC    is SCRIPT embedded in the running mission == SRC?

run: writes user-inbox/NAME.lua atomically, waits for its outbox to be final, prints it, deletes
     both files (unless --keep). --timeout is in sim seconds (default 600): past it, the command is
     stopped. --silence is in real seconds without a heartbeat (default 60): past it, the files are
     kept. Exit 0 done, 1 fail/refused/stopped, 2 timeout, 3 usage/setup, 4 lost (the mission
     restarted under it), 5 silent (paused, not started, or DCS is down).
status: exit 0 when the heartbeat is advancing, 1 when it is still or absent.
The root is --root, else $HOTLOAD_ROOT, else the folder above this file's bin/.

Also a module, standard library only, Python 3.8+: with this folder on sys.path, `import hotload`
gives parse/dump (Lua data), Mailbox, Driver and Outcome.
"""

import argparse
import datetime
import json
import math
import os
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["LuaDataError", "parse", "dump", "Mailbox", "Driver", "Outcome", "main"]

# ── Lua data ─────────────────────────────────────────────────────────────────────────────────────


class LuaDataError(ValueError):
    pass


_NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LONG_OPEN = re.compile(r"\[(=*)\[")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", '"': '"',
            "'": "'", "\n": "\n"}


class _Reader:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def fail(self, message):
        raise LuaDataError("%s at offset %d" % (message, self.pos))

    def skip(self):
        text = self.text
        while self.pos < len(text):
            if text[self.pos].isspace():
                self.pos += 1
            elif text.startswith("--", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end + 1
            else:
                break

    def peek(self):
        self.skip()
        return self.text[self.pos:self.pos + 1]

    def expect(self, char):
        if self.peek() != char:
            self.fail("expected %r" % char)
        self.pos += 1

    def keyword(self, word):
        self.skip()
        match = _NAME.match(self.text, self.pos)
        if not match or match.group(0) != word:
            self.fail("expected %r" % word)
        self.pos = match.end()

    def chunk(self):
        self.keyword("return")
        value = self.value()
        if self.peek() == ";":
            self.pos += 1
        if self.peek():
            self.fail("unexpected text after the value")
        return value

    def value(self):
        char = self.peek()
        if not char:
            self.fail("unexpected end of text")
        if char == "{":
            return self.table()
        if char in ('"', "'"):
            return self.quoted(char)
        if char == "[":
            return self.long_string()
        if char == "-":
            self.pos += 1
            return -self.number_or_special()
        if char.isdigit() or char == ".":
            return self.number_or_special()
        match = _NAME.match(self.text, self.pos)
        if not match:
            self.fail("unexpected %r" % char)
        name = match.group(0)
        if name in ("true", "false", "nil"):
            self.pos = match.end()
            return {"true": True, "false": False, "nil": None}[name]
        return self.number_or_special()

    def number_or_special(self):
        self.skip()
        text = self.text
        if text.startswith("math.huge", self.pos):
            self.pos += len("math.huge")
            return math.inf
        if text.startswith("0/0", self.pos):
            self.pos += 3
            return math.nan
        match = _NUMBER.match(text, self.pos)
        if not match:
            self.fail("expected a number")
        self.pos = match.end()
        literal = match.group(0)
        if literal[:2] in ("0x", "0X"):
            return int(literal, 16)
        if literal.isdigit():
            return int(literal)
        return float(literal)

    def quoted(self, quote):
        text = self.text
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(text):
                self.fail("unfinished string")
            char = text[self.pos]
            self.pos += 1
            if char == quote:
                return "".join(out)
            if char == "\n":
                self.fail("newline in string")
            if char != "\\":
                out.append(char)
                continue
            if self.pos >= len(text):
                self.fail("unfinished string")
            esc = text[self.pos]
            if esc.isdigit():
                digits = re.match(r"\d{1,3}", text[self.pos:]).group(0)
                self.pos += len(digits)
                if int(digits) > 255:
                    self.fail("escape out of range")
                out.append(chr(int(digits)))
            elif esc in _ESCAPES:
                self.pos += 1
                out.append(_ESCAPES[esc])
            else:
                self.fail("unknown escape \\%s" % esc)

    def long_string(self):
        match = _LONG_OPEN.match(self.text, self.pos)
        if not match:
            self.fail("expected a value")
        close = "]" + match.group(1) + "]"
        end = self.text.find(close, match.end())
        if end < 0:
            self.fail("unfinished long string")
        body = self.text[match.end():end]
        self.pos = end + len(close)
        return body[1:] if body.startswith("\n") else body

    def table(self):
        self.expect("{")
        result = {}
        position = 0
        while self.peek() != "}":
            if not self.peek():
                self.fail("unfinished table")
            if self.peek() == "[" and not _LONG_OPEN.match(self.text, self.pos):
                self.pos += 1
                key = self.value()
                self.expect("]")
                self.expect("=")
                if key is None:
                    self.fail("nil table key")
                result[key] = self.value()
            else:
                name = _NAME.match(self.text, self.pos)
                if name and name.group(0) not in ("true", "false", "nil", "math") and self._equals_follows(name.end()):
                    self.pos = name.end()
                    self.expect("=")
                    result[name.group(0)] = self.value()
                else:
                    position += 1
                    result[position] = self.value()
            if self.peek() in (",", ";"):
                self.pos += 1
            elif self.peek() != "}":
                self.fail("expected ',' or '}'")
        self.pos += 1
        count = len(result)
        if count and all(isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= count for k in result):
            return [result[k] for k in range(1, count + 1)]
        return result

    def _equals_follows(self, index):
        text = self.text
        while index < len(text) and text[index].isspace():
            index += 1
        return text.startswith("=", index) and not text.startswith("==", index)


def parse(text):
    """The value of a `return <value>` chunk. Tables become dict, or list when the keys are exactly 1..n."""
    return _Reader(text).chunk()


_DUMP_ESCAPES = {'"': '\\"', "\\": "\\\\", "\n": "\\\n", "\r": "\\r"}


def _string(value):
    out = []
    for index, char in enumerate(value):
        if char in _DUMP_ESCAPES:
            out.append(_DUMP_ESCAPES[char])
        elif ord(char) < 32 or ord(char) == 127:
            # three digits when a digit follows, as Lua's %q does, so the next character is not absorbed
            following = value[index + 1:index + 2]
            out.append("\\%03d" % ord(char) if following.isdigit() else "\\%d" % ord(char))
        else:
            out.append(char)
    return '"' + "".join(out) + '"'


def _value(value):
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "0/0"
        if value == math.inf:
            return "math.huge"
        if value == -math.inf:
            return "-math.huge"
        return repr(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "{" + ", ".join(_value(v) for v in value) + "}"
    if isinstance(value, dict):
        return "{" + ", ".join("[%s] = %s" % (_value(k), _value(v)) for k, v in value.items()) + "}"
    raise LuaDataError("cannot dump %s" % type(value).__name__)


def dump(value):
    """`value` as a chunk plain Lua 5.1 can `dofile`."""
    return "return " + _value(value) + "\n"


# ── The mailbox ──────────────────────────────────────────────────────────────────────────────────

HEARTBEAT = "_heartbeat.lua"


class Mailbox:
    """`user-inbox/<name>.lua` in, `user-outbox/<name>.lua` out, and the heartbeat. Knows no command's meaning."""

    def __init__(self, root):
        self.root = Path(root)
        self.inbox = self.root / "user-inbox"
        self.outbox = self.root / "user-outbox"

    def exists(self):
        return self.inbox.is_dir() and self.outbox.is_dir()

    def has(self, name):
        return (self.inbox / (name + ".lua")).exists() or (self.outbox / (name + ".lua")).exists()

    def send(self, name, code):
        """Write `<name>.lua.tmp`, then rename it: hotload only picks `*.lua`, so it never sees half a command."""
        tmp = self.inbox / (name + ".lua.tmp")
        tmp.write_text(code, encoding="utf-8", newline="\n")
        os.replace(tmp, self.inbox / (name + ".lua"))

    def text(self, name):
        try:
            return (self.outbox / (name + ".lua")).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def outcome(self, name):
        """The outbox as a dict, or None while it is absent or half-written."""
        return self._read(self.outbox / (name + ".lua"))

    def heartbeat(self):
        """(the heartbeat as a dict, its modification time in ns), or None while absent or half-written."""
        path = self.outbox / HEARTBEAT
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return None
        record = self._read(path)
        return None if record is None else (record, mtime)

    def clear(self, name):
        """The inbox file first: an outbox left without its inbox file can never make hotload run it again."""
        if self._remove(self.inbox / (name + ".lua")):
            self._remove(self.outbox / (name + ".lua"))

    @staticmethod
    def _read(path):
        try:
            record = parse(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):  # LuaDataError is a ValueError
            return None
        return record if isinstance(record, dict) else None

    @staticmethod
    def _remove(path):
        """True once `path` is gone; a file something holds open stays, and that is not an error."""
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True


# ── The driver ───────────────────────────────────────────────────────────────────────────────────

POLL = 0.5  # real seconds between two looks
SILENCE_SAID_AFTER = 10.0  # real seconds without a new heartbeat before it is said
SILENCE = "no heartbeat: paused, not started, or DCS is down"
FINAL = ("done", "fail", "stopped", "refused")


@dataclass
class Outcome:
    status: str  # done, fail, stopped, refused; or the client's: timeout, lost, silent
    result: object = None
    error: str = None
    traceback: str = None
    duration: float = None


def unique():
    return format(time.time_ns(), "x")


def _record_outcome(record):
    return Outcome(record["status"], record.get("result"), record.get("error"), record.get("traceback"),
                   record.get("duration"))


class Driver:
    """Sends mailbox commands and waits for them in sim time, read from the heartbeat."""

    def __init__(self, mailbox, journal=None, say=print, clock=time.monotonic, sleep=time.sleep):
        self.mailbox = mailbox
        self.journal = Path(journal) if journal else None
        self.say = say
        self.clock = clock
        self.sleep = sleep

    def call(self, name, code, timeout, silence=None, keep=False):
        """Sends `code` as `name` and waits for its Outcome. `timeout` in sim seconds; `silence` in real
        seconds without a heartbeat, None to wait for ever. The files are cleared unless `keep`, or
        the wait ended `silent`."""
        self.mailbox.send(name, code)
        return self._await(name, timeout, silence, keep)

    def run(self, key, prefix, code, timeout, silence=None):
        """`call` under the journal: a key that ended is not sent again; a key sent is waited on under its name."""
        entry = read_journal(self.journal).get(key)
        if entry and entry["state"] == "ended":
            return _journal_outcome(entry)
        if entry:
            name = entry["name"]
        else:
            name = "%s-%s" % (prefix, unique())
            beat = self.mailbox.heartbeat()
            self._append({"key": key, "name": name, "sent_at": beat[0].get("time") if beat else None,
                          "state": "sent"})
            self.mailbox.send(name, code)
        outcome = self._await(name, timeout, silence, False)
        if outcome.status != "silent":
            fields = dict(outcome.__dict__, result=dump(outcome.result))
            self._append({"key": key, "name": name, "state": "ended", "outcome": fields})
        return outcome

    def _await(self, name, timeout, silence, keep):
        mailbox, label = self.mailbox, "inbox/" + name
        last_key, last_time = None, None
        last_change = self.clock()
        said = False
        waited = 0.0  # sim seconds seen before pickup
        seen_started = None  # the heartbeat key when the outbox was first seen `started`
        stop = None
        outcome = None
        try:
            while outcome is None:
                # The heartbeat before the outbox: one that no longer lists the run was written after its final outbox.
                beat = mailbox.heartbeat()
                record = mailbox.outcome(name)
                status = record.get("status") if record else None
                if status in FINAL:
                    outcome = _record_outcome(record)
                    if status == "stopped" and stop:
                        outcome.status, outcome.error = "timeout", "timed out after %g s of sim time" % timeout
                    break
                now = self.clock()
                elapsed = None
                if beat:
                    record_beat, mtime = beat
                    key = (mtime, record_beat.get("time"), record_beat.get("mission"))
                    t = record_beat.get("time")
                    if key != last_key:
                        last_change, said = now, False
                        if status is None and last_time is not None and isinstance(t, (int, float)) and t > last_time:
                            waited += t - last_time
                    if status == "started":
                        started = record.get("started")
                        if seen_started is None:
                            seen_started = key
                        runs = record_beat.get("runs")
                        listed = isinstance(runs, dict) and label in runs
                        if not listed and (key != seen_started or (t is not None and started is not None and t >= started)):
                            outcome = Outcome("lost", error="the mission restarted under %s: its run is gone" % label)
                            break
                        if t is not None and started is not None:
                            elapsed = t - started
                    else:
                        elapsed = waited
                    last_key, last_time = key, t
                if not said and now - last_change > SILENCE_SAID_AFTER:
                    said = True
                    self.say(SILENCE)
                if silence is not None and now - last_change > silence:
                    return Outcome("silent", error="no heartbeat for %g s: paused, not started, or DCS is down" % silence)
                if elapsed is not None and elapsed > timeout and stop is None:
                    if status is None:
                        outcome = Outcome("timeout", error="not picked up after %g s of sim time" % timeout)
                        break
                    stop = "stop-" + unique()
                    mailbox.send(stop, 'return Hotload.stop("%s")' % label)
                self.sleep(POLL)
        finally:
            if stop:
                mailbox.clear(stop)
        if not keep:
            mailbox.clear(name)
        return outcome

    def _append(self, entry):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
            handle.flush()


def read_journal(path):
    """Each key's last entry; a missing file is an empty journal, a torn line is skipped."""
    entries = {}
    if path and Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            entries[entry["key"]] = entry
    return entries


def _journal_outcome(entry):
    fields = dict(entry["outcome"])
    fields["result"] = parse(fields["result"])
    return Outcome(**fields)


# ── The command line ─────────────────────────────────────────────────────────────────────────────

EXIT = {"done": 0, "fail": 1, "refused": 1, "stopped": 1, "timeout": 2, "lost": 4, "silent": 5}
STATUS_LOOK = 1.5  # real seconds between the two looks of `status`


class Usage(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Usage(message)


def default_root():
    return Path(os.environ.get("HOTLOAD_ROOT") or Path(__file__).resolve().parent.parent)


def default_log():
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    return Path(home) / "Saved Games" / "DCS" / "Logs" / "dcs.log"


def _mailbox(root):
    mailbox = Mailbox(root or default_root())
    if not mailbox.exists():
        raise Usage("no user-inbox/ and user-outbox/ under %s (mailbox off?)" % mailbox.root)
    return mailbox


def cmd_run(args, clock, sleep):
    mailbox = _mailbox(args.root)
    if (args.e is None) == (args.file is None):
        raise Usage("give -e 'LUA' or a .lua file")
    name = args.name or "cli-" + unique()
    if mailbox.has(name):
        raise Usage("%s already in the mailbox; pick another --name or delete it" % name)
    if args.e is not None:
        code = args.e + "\n"
    else:
        try:
            code = Path(args.file).read_text(encoding="utf-8")
        except OSError as err:
            raise Usage("cannot read %s: %s" % (args.file, err))
    driver = Driver(mailbox, say=lambda text: print("hotload.py: " + text, file=sys.stderr), clock=clock,
                    sleep=sleep)
    outcome = driver.call(name, code, args.timeout, silence=args.silence, keep=True)
    if outcome.status in FINAL:
        print(mailbox.text(name), end="")
    else:
        print("hotload.py: " + outcome.error, file=sys.stderr)
    if outcome.status == "silent":
        print("hotload.py: files kept: %s; to stop it: python %s run --root \"%s\" -e 'return Hotload.stop(\"inbox/%s\")'"
              % (mailbox.inbox / (name + ".lua"), sys.argv[0] or "hotload.py", mailbox.root, name), file=sys.stderr)
    elif not args.keep:
        mailbox.clear(name)
    return EXIT[outcome.status]


def cmd_status(args, clock, sleep):
    mailbox = _mailbox(args.root)
    first = mailbox.heartbeat()
    if first is None:
        print("no heartbeat in %s (hotload older than 3.0.0, or the mission never started)" % mailbox.outbox)
        return 1
    sleep(STATUS_LOOK)
    second = mailbox.heartbeat()
    advancing = second is not None and (second[1], second[0].get("time")) != (first[1], first[0].get("time"))
    beat = (second or first)[0]
    print("%s: mission %s, time %s, version %s" % ("advancing" if advancing else "still (paused, not started, or not running)",
                                                   beat.get("mission"), beat.get("time"), beat.get("version")))
    for label, started in sorted((beat.get("runs") or {}).items()):
        print("  %s, since %s" % (label, started))
    return 0 if advancing else 1


def cmd_log(args, clock, sleep):
    path = Path(args.log) if args.log else default_log()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        raise Usage("no log at %s" % path)
    starts = [i for i, line in enumerate(lines) if "HOTLOAD: ready" in line]
    if not starts:
        raise Usage("no 'HOTLOAD: ready' in %s (hotload not loaded this session?)" % path)
    print("# dcs.log times are UTC", file=sys.stderr)
    pattern = re.compile(args.pattern or "")
    for line in lines[starts[-1]:]:
        if "HOTLOAD" in line and pattern.search(line):
            print(line.replace(" INFO    SCRIPTING (Main): HOTLOAD:", ""))
    return 0


def cmd_check(args, clock, sleep):
    miz = Path(args.miz) if args.miz else Path(os.environ.get("TEMP") or "/tmp") / "DCS" / "tempMission.miz"
    if not miz.is_file():
        raise Usage("no running-mission copy at %s" % miz)
    written = datetime.datetime.fromtimestamp(miz.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    try:
        ondisk = Path(args.src).read_bytes()
    except OSError as err:
        raise Usage("cannot read %s: %s" % (args.src, err))
    try:
        with zipfile.ZipFile(miz) as archive:
            running = archive.read("l10n/DEFAULT/" + args.script)
    except KeyError:
        print("NOT EMBEDDED: %s is not in the running mission (%s, written %s)" % (args.script, miz, written))
        return 1
    if running == ondisk:
        print("MATCH: the running mission embeds %s as it is on disk" % args.src)
        return 0
    print("DIFFERENT: the running mission (%s, written %s) embeds another version of %s -- re-open the rebuilt .miz "
          "from the Mission menu (Restart replays the old copy)" % (miz, written, args.script))
    return 1


def _parser():
    parser = _Parser(prog="hotload.py", description="Drive a running DCS mission through dcs-hotload's mailbox.")
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)
    run = commands.add_parser("run")
    run.add_argument("--root")
    run.add_argument("--name")
    run.add_argument("--timeout", type=float, default=600)
    run.add_argument("--silence", type=float, default=60)
    run.add_argument("--keep", action="store_true")
    run.add_argument("-e")
    run.add_argument("file", nargs="?")
    status = commands.add_parser("status")
    status.add_argument("--root")
    log = commands.add_parser("log")
    log.add_argument("--log")
    log.add_argument("pattern", nargs="?")
    check = commands.add_parser("check")
    check.add_argument("--miz")
    check.add_argument("script")
    check.add_argument("src")
    return parser


def main(argv=None, clock=time.monotonic, sleep=time.sleep):
    try:
        args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
        handler = {"run": cmd_run, "status": cmd_status, "log": cmd_log, "check": cmd_check}.get(args.command)
        if handler is None:
            raise Usage("usage: python hotload.py run|status|log|check ...  (see the top of this file)")
        return handler(args, clock, sleep)
    except Usage as err:
        print("hotload.py: %s" % err, file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
