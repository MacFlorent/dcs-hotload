"""hotload-setup.py -- set dcs-hotload up in a DCS mission folder. Python 3, standard library only.

  python hotload-setup.py status    [--mission DIR] [--dcs DCS_INSTALL] [--miz FILE]
      What the steps below would change. Exit 0 when hotload is fully set up, 2 when not.
  python hotload-setup.py deploy    [--mission DIR] [--update]
      Copy the tool into DIR/dcs-hotload/ (the release file set, .github/scripts/shipped.txt) and
      create its user-* folders. An older copy is replaced only with --update; user-* folders are
      never touched; a newer copy is left alone.
  python hotload-setup.py unlock    [--dcs DCS_INSTALL] [--yes]
      Comment out sanitizeModule('io') and ('lfs') in the install's Scripts/MissionScripting.lua,
      keeping the original as MissionScripting.lua.bak. Changes nothing without --yes.
  python hotload-setup.py patch-miz FILE [--mission DIR] [--retarget]
      Add a MISSION START trigger that loads DIR/dcs-hotload/dcs-hotload.lua, keeping the original
      as FILE.bak. A boot line pointing at another folder is rewritten only with --retarget.

DIR defaults to the current folder. The DCS install is --dcs, else the DCS_INSTALL environment
variable, else the first of the usual locations that exists.

Exit codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed (rerun with the
flag the message names, once the user agrees), 3 usage.

A .miz is a zip of Lua tables written by the Mission Editor. The `mission` table is read and
written here without Lua: the writer follows the style of the file it read (tabs or four spaces,
`{}` or an open pair for an empty table), so a table it does not change comes back as the same
text, and numbers are kept as they were written.
"""
import argparse
import os
import posixpath
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

OK, FAIL, DECIDE, USAGE = 0, 1, 2, 3

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DCS_CANDIDATES = [r"E:\DCS World", r"C:\Program Files\Eagle Dynamics\DCS World",
                  r"D:\DCS World", r"C:\Program Files\Eagle Dynamics\DCS World OpenBeta"]
USER_FOLDERS = ("user-lib", "user-scripts", "user-inbox", "user-outbox")


def say(message):
    print(f"hotload-setup: {message}")


# ── The Mission Editor's Lua table format ───────────────────────────────────────────────────────

class FormatError(Exception):
    pass


class Num(str):
    """A number as the file wrote it: kept as text, so writing it back changes nothing."""


class Style:
    """How a file is laid out: the indent unit, and whether an empty table is written `{}`."""

    def __init__(self, indent, compact_empty):
        self.indent, self.compact_empty = indent, compact_empty

    @classmethod
    def of(cls, text):
        m = re.search(r"\n([ \t]+)\S", text)
        indent = m.group(1) if m else "\t"
        if re.search(r"= \{\},", text):
            compact = True
        elif re.search(r"= \n[ \t]*\{\n[ \t]*\}, -- end of", text):
            compact = False
        else:
            compact = indent == "\t"
        return cls(indent, compact)


ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
           "\\": "\\", '"': '"', "'": "'", "\n": "\n"}
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


class Parser:
    def __init__(self, text):
        self.text, self.pos = text, 0

    def fail(self, what):
        line = self.text.count("\n", 0, self.pos) + 1
        raise FormatError(f"line {line}: {what}")

    def skip(self):
        while True:
            m = re.compile(r"\s*").match(self.text, self.pos)
            self.pos = m.end()
            if self.text.startswith("--", self.pos):
                end = self.text.find("\n", self.pos)
                self.pos = len(self.text) if end < 0 else end
            else:
                return

    def expect(self, token):
        self.skip()
        if not self.text.startswith(token, self.pos):
            self.fail(f"expected {token!r}")
        self.pos += len(token)

    def peek(self):
        self.skip()
        return self.text[self.pos:self.pos + 1]

    def name(self):
        self.skip()
        m = re.compile(r"[A-Za-z_]\w*").match(self.text, self.pos)
        if not m:
            self.fail("expected a name")
        self.pos = m.end()
        return m.group()

    def string(self):
        quote = self.text[self.pos]
        self.pos += 1
        out = []
        while True:
            if self.pos >= len(self.text):
                self.fail("unfinished string")
            c = self.text[self.pos]
            if c == quote:
                self.pos += 1
                return "".join(out)
            if c == "\\":
                e = self.text[self.pos + 1:self.pos + 2]
                if e in ESCAPES:
                    out.append(ESCAPES[e])
                    self.pos += 2
                elif e.isdigit():
                    m = re.compile(r"\d{1,3}").match(self.text, self.pos + 1)
                    code = int(m.group())
                    if code > 127:
                        self.fail("a byte escape above 127")
                    out.append(chr(code))
                    self.pos = m.end()
                else:
                    self.fail(f"unknown escape \\{e}")
            elif c == "\n":
                self.fail("unfinished string")
            else:
                out.append(c)
                self.pos += 1

    def value(self):
        c = self.peek()
        if c == "{":
            return self.table()
        if c in "\"'":
            return self.string()
        m = NUMBER.match(self.text, self.pos)
        if m:
            self.pos = m.end()
            return Num(m.group())
        for word, value in (("true", True), ("false", False)):
            if re.compile(word + r"\b").match(self.text, self.pos):
                self.pos += len(word)
                return value
        self.fail("expected a value")

    def table(self):
        self.expect("{")
        table = {}
        while self.peek() != "}":
            self.expect("[")
            c = self.peek()
            if c in "\"'":
                key = self.string()
            else:
                m = re.compile(r"-?\d+").match(self.text, self.pos)
                if not m:
                    self.fail("expected a string or integer key")
                self.pos = m.end()
                key = int(m.group())
            self.expect("]")
            self.expect("=")
            table[key] = self.value()
            if self.peek() == ",":
                self.pos += 1
        self.pos += 1
        return table


def lua_load(text):
    """`name = { ... }` → (name, table). Tables are dicts in file order."""
    p = Parser(text)
    name = p.name()
    p.expect("=")
    if p.peek() != "{":
        p.fail("expected a table")
    value = p.table()
    p.skip()
    if p.pos != len(text):
        p.fail("unexpected text after the table")
    return name, value


def lua_quote(s):
    """A string as Lua 5.1's %q writes it, which is how the Mission Editor writes strings."""
    return '"' + (s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\\n")
                  .replace("\r", "\\r").replace("\0", "\\000")) + '"'


def lua_key(key):
    return f"[{key}]" if isinstance(key, int) else f"[{lua_quote(key)}]"


def lua_scalar(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, Num):
        return str(value)
    if isinstance(value, int) or isinstance(value, float):
        return repr(value)
    return lua_quote(value)


def lua_dump(name, value, style):
    """Writes `name = { ... }` the way the Mission Editor does, in the given style."""
    out = [f"{name} = \n{{\n"]

    def entries(table, depth):
        pad = style.indent * depth
        for key, v in table.items():
            k = lua_key(key)
            if not isinstance(v, dict):
                out.append(f"{pad}{k} = {lua_scalar(v)},\n")
            elif not v and style.compact_empty:
                out.append(f"{pad}{k} = {{}},\n")
            else:
                out.append(f"{pad}{k} = \n{pad}{{\n")
                entries(v, depth + 1)
                out.append(f"{pad}}}, -- end of {k}\n")

    entries(value, 1)
    out.append(f"}} -- end of {name}\n")
    return "".join(out)


# ── A .miz ──────────────────────────────────────────────────────────────────────────────────────

class Miz:
    """A .miz in memory: every entry as bytes, in order, and the `mission` table parsed."""

    def __init__(self, infos, entries, mission, style):
        self.infos, self.entries, self.mission, self.style = infos, entries, mission, style

    @classmethod
    def read(cls, path):
        with zipfile.ZipFile(path) as z:
            infos = {i.filename: i for i in z.infolist()}
            entries = {name: z.read(name) for name in infos}
        text = entries["mission"].decode("utf-8")
        name, mission = lua_load(text)
        if name != "mission":
            raise FormatError(f"the mission entry defines {name!r}")
        return cls(infos, entries, mission, Style.of(text))

    def write(self, path):
        text = lua_dump("mission", self.mission, self.style)
        if lua_load(text)[1] != self.mission:
            raise FormatError("the written mission does not read back the same")
        self.entries["mission"] = text.encode("utf-8")
        path = Path(path)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".miz")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for name, data in self.entries.items():
                    info = self.infos.get(name) or zipfile.ZipInfo(name)
                    if name not in self.infos:
                        info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, data)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def boot_line(lua_path):
    return f"dofile([[{lua_path}]])"


BOOT = re.compile(r"""dofile\s*\(\s*(?:\[(=*)\[(.*?)\]\1\]|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*\)""",
                  re.S)


def boot_paths(text):
    paths = []
    for m in BOOT.finditer(text):
        path = m.group(2) if m.group(2) is not None else (m.group(3) or m.group(4) or "").replace("\\\\", "\\")
        if path.replace("\\", "/").lower().endswith("dcs-hotload.lua"):
            paths.append(path)
    return paths


def find_boot(miz):
    """Every place the mission loads a dcs-hotload.lua: [(where, path)]."""
    found = []
    for n, rule in miz.mission.get("trigrules", {}).items():
        for action in rule.get("actions", {}).values():
            if isinstance(action, dict) and action.get("predicate") == "a_do_script":
                found += [(f"trigger {n}", p) for p in boot_paths(action.get("text", ""))]
    for name, data in miz.entries.items():
        if name.startswith("l10n/") and name.lower().endswith(".lua"):
            found += [(f"embedded {name}", p) for p in boot_paths(data.decode("utf-8", "replace"))]
    return found


def add_boot(miz, lua_path):
    """A MISSION START trigger running the boot line: trigrules (what the editor shows) and trig
    (what DCS runs), index for index."""
    rules = miz.mission.setdefault("trigrules", {})
    trig = miz.mission.setdefault("trig", {})
    for part in ("actions", "conditions", "flag", "funcStartup"):
        trig.setdefault(part, {})
    n = max([k for k in rules if isinstance(k, int)] + [0]) + 1
    text = boot_line(lua_path)
    rules[n] = {"comment": "dcs-hotload", "predicate": "triggerStart", "eventlist": "",
                "colorItem": "0x00ffffff", "rules": {},
                "actions": {1: {"predicate": "a_do_script", "text": text}}}
    trig["actions"][n] = f"a_do_script({lua_quote(text)});"
    trig["conditions"][n] = "return(true)"
    trig["flag"][n] = True
    trig["funcStartup"][n] = f"if mission.trig.conditions[{n}]() then mission.trig.actions[{n}]() end"


def retarget_boot(miz, old, new):
    """Rewrites a boot line found by find_boot from `old` to `new`, wherever it is."""
    for n, rule in miz.mission.get("trigrules", {}).items():
        for action in rule.get("actions", {}).values():
            if isinstance(action, dict) and old in action.get("text", ""):
                action["text"] = action["text"].replace(old, new)
                actions = miz.mission.get("trig", {}).get("actions", {})
                if n in actions:
                    actions[n] = actions[n].replace(lua_quote(old)[1:-1], lua_quote(new)[1:-1])
    for name, data in miz.entries.items():
        if name.startswith("l10n/") and name.lower().endswith(".lua"):
            miz.entries[name] = data.replace(old.encode("utf-8"), new.encode("utf-8"))


def same_path(a, b):
    def norm(p):
        return posixpath.normpath(p.replace("\\", "/")).lower()
    return norm(a) == norm(b)


# ── Versions and the release file set ──────────────────────────────────────────────────────────

def lua_version(lua):
    m = re.search(r'^Hotload\.version = "([^"]+)"', Path(lua).read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def plugin_version():
    return lua_version(PLUGIN_ROOT / "dcs-hotload.lua")


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def shipped():
    lines = (PLUGIN_ROOT / ".github" / "scripts" / "shipped.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def find_dcs(explicit):
    explicit = explicit or os.environ.get("DCS_INSTALL")
    for cand in ([explicit] if explicit else DCS_CANDIDATES):
        if cand and (Path(cand) / "Scripts" / "MissionScripting.lua").is_file():
            return Path(cand)
    return None


LOCK = re.compile(r"""^([ \t]*)(sanitizeModule\(\s*['"](io|lfs)['"]\s*\))""", re.M)


def locked_modules(mission_scripting):
    return [m.group(3) for m in LOCK.finditer(Path(mission_scripting).read_text(encoding="utf-8"))]


# ── Commands ────────────────────────────────────────────────────────────────────────────────────

def deploy(mission, update):
    target = mission / "dcs-hotload"
    want = plugin_version()
    lua = target / "dcs-hotload.lua"
    if lua.exists():
        have = lua_version(lua)
        if have == want:
            say(f"dcs-hotload {have} is already deployed in {target}")
        elif have is None or version_key(have) > version_key(want):
            say(f"{target} holds dcs-hotload {have}, not older than the plugin's {want}: left alone")
            return FAIL
        elif not update:
            say(f"{target} holds dcs-hotload {have}; the plugin has {want}. A mission keeps the version it "
                "was tested with: rerun with --update once the user agrees")
            return DECIDE
        else:
            for path in shipped():
                old = target / path
                if old.is_dir():
                    shutil.rmtree(old)
                elif old.exists():
                    old.unlink()
            copy_shipped(target)
            say(f"updated {target} from {have} to {want}; user-* folders untouched")
    else:
        copy_shipped(target)
        say(f"deployed dcs-hotload {want} into {target}")
    for folder in USER_FOLDERS:
        (target / folder).mkdir(exist_ok=True)
    return OK


def copy_shipped(target):
    target.mkdir(parents=True, exist_ok=True)
    for path in shipped():
        src = PLUGIN_ROOT / path
        if src.is_dir():
            shutil.copytree(src, target / path)
        else:
            shutil.copy2(src, target / path)


def unlock(dcs_arg, yes):
    dcs = find_dcs(dcs_arg)
    if not dcs:
        say("DCS install not found: pass --dcs or set DCS_INSTALL")
        return FAIL
    file = dcs / "Scripts" / "MissionScripting.lua"
    locked = locked_modules(file)
    if not locked:
        say(f"{file} already leaves io and lfs to missions")
        return OK
    if not yes:
        say(f"{file} removes {' and '.join(locked)} from missions; hotload needs both. The edit is "
            "install-wide (every mission gets file access, multiplayer ones included), affects "
            "multiplayer integrity checks, and DCS updates revert it. Rerun with --yes once the user agrees")
        return DECIDE
    text = file.read_text(encoding="utf-8")
    try:
        backup = file.with_name(file.name + ".bak")
        if not backup.exists():
            shutil.copy2(file, backup)
        with open(file, "w", encoding="utf-8", newline="") as f:
            f.write(LOCK.sub(r"\1--\2", text))
    except PermissionError:
        say(f"no permission to write {file}: run as administrator, or comment out the "
            "sanitizeModule('io') and ('lfs') lines by hand")
        return FAIL
    say(f"unlocked {' and '.join(locked)} in {file}")
    return OK


def patch_miz(miz_path, mission, retarget):
    lua = str((mission / "dcs-hotload" / "dcs-hotload.lua").resolve())
    miz = Miz.read(miz_path)
    found = find_boot(miz)
    if any(same_path(path, lua) for _, path in found):
        say(f"{miz_path.name} already loads {lua}")
        return OK
    if found and not retarget:
        for where, path in found:
            say(f"{miz_path.name} loads {path} ({where}), not {lua}")
        say("rerun with --retarget to point it at this mission's copy, once the user agrees")
        return DECIDE
    backup = miz_path.with_name(miz_path.name + ".bak")
    if not backup.exists():
        shutil.copy2(miz_path, backup)
    if found:
        for where, path in found:
            retarget_boot(miz, path, lua)
            say(f"{where}: now loads {lua}")
    else:
        add_boot(miz, lua)
        say(f"added a MISSION START trigger loading {lua}")
    miz.write(miz_path)
    say("re-open the mission from the Mission menu: Restart replays the copy loaded at launch")
    return OK


def status(mission, dcs_arg, miz_arg):
    ready = True
    lua = mission / "dcs-hotload" / "dcs-hotload.lua"
    if not lua.exists():
        say(f"not deployed in {mission}: run deploy")
        ready = False
    else:
        have, want = lua_version(lua), plugin_version()
        say(f"deployed: {have}" + ("" if have == want else f" (the plugin has {want}: deploy --update)"))
        missing = [f for f in ("user-inbox", "user-outbox") if not (lua.parent / f).is_dir()]
        if missing:
            say(f"mailbox off ({', '.join(missing)} missing): run deploy")
            ready = False

    dcs = find_dcs(dcs_arg)
    if not dcs:
        say("DCS install not found: pass --dcs or set DCS_INSTALL")
        ready = False
    else:
        locked = locked_modules(dcs / "Scripts" / "MissionScripting.lua")
        say("MissionScripting.lua: " + (f"{' and '.join(locked)} locked: run unlock" if locked else "unlocked"))
        ready = ready and not locked

    mizs = [Path(miz_arg)] if miz_arg else sorted(mission.glob("*.miz"))
    if len(mizs) != 1:
        say(f"{len(mizs)} .miz files in {mission}: pass --miz")
        return DECIDE
    expected = str(lua.resolve())
    found = find_boot(Miz.read(mizs[0]))
    if any(same_path(path, expected) for _, path in found):
        say(f"{mizs[0].name} loads this mission's dcs-hotload")
    else:
        say(f"{mizs[0].name} " + (f"loads {found[0][1]} instead: patch-miz --retarget" if found
                                   else "does not load dcs-hotload: run patch-miz"))
        ready = False
    return OK if ready else DECIDE


def main(argv=None):
    p = argparse.ArgumentParser(prog="hotload-setup.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--mission", default=".")
    s.add_argument("--dcs")
    s.add_argument("--miz")
    d = sub.add_parser("deploy")
    d.add_argument("--mission", default=".")
    d.add_argument("--update", action="store_true")
    u = sub.add_parser("unlock")
    u.add_argument("--dcs")
    u.add_argument("--yes", action="store_true")
    m = sub.add_parser("patch-miz")
    m.add_argument("miz")
    m.add_argument("--mission", default=".")
    m.add_argument("--retarget", action="store_true")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return OK if e.code == 0 else USAGE

    try:
        if args.cmd == "status":
            return status(Path(args.mission), args.dcs, args.miz)
        if args.cmd == "deploy":
            return deploy(Path(args.mission), args.update)
        if args.cmd == "unlock":
            return unlock(args.dcs, args.yes)
        return patch_miz(Path(args.miz), Path(args.mission), args.retarget)
    except (FormatError, zipfile.BadZipFile, KeyError) as e:
        say(f"cannot read the mission: {e}")
        return FAIL


if __name__ == "__main__":
    sys.exit(main())
