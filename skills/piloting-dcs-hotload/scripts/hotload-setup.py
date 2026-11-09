"""hotload-setup.py -- set dcs-hotload up in a DCS mission folder. Python 3, standard library only.

  python hotload-setup.py status    --dcs DCS [--mission DIR] [--miz FILE]
      What the steps below would change. Exit 0 when hotload is fully set up, 2 when not.
  python hotload-setup.py deploy    [--mission DIR] [--update]
      Copy the tool into DIR/dcs-hotload/ (the release file set, .github/scripts/shipped.txt) and
      create its user-* folders. An older copy is replaced only with --update; user-* folders are
      never touched; a newer copy is left alone.
  python hotload-setup.py unlock    --dcs DCS [--yes]
      Comment out sanitizeModule('io') and ('lfs') in the install's Scripts/MissionScripting.lua,
      keeping the original as MissionScripting.lua.bak. Changes nothing without --yes.
  python hotload-setup.py patch-miz FILE [--mission DIR] [--retarget]
      Add a MISSION START trigger that sets BASE_HOTLOAD_PATH to DIR/dcs-hotload, then loads
      dcs-hotload.lua from it when it is there (boot-guard.lua, next to this script), keeping the
      original as FILE.bak. A boot pointing at another folder, or cleared, is rewritten only with
      --retarget.
  python hotload-setup.py boot-path FILE [--set DIR | --clear]
      Show the folder BASE_HOTLOAD_PATH names in the trigger patch-miz writes, write another
      folder (one holding dcs-hotload.lua), or empty it, so the mission only logs where it starts.
      Run --clear on a copy that leaves this machine. Refuses a mission without exactly one
      BASE_HOTLOAD_PATH assignment, or whose compiled trigger does not hold it once.

DIR defaults to the current folder. DCS is the DCS World folder, the one holding
Scripts/MissionScripting.lua: nothing guesses it.

Exit codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed (rerun with the
flag the message names, once the user agrees), 3 usage.

A .miz is a zip of Lua tables, written by the Mission Editor or by a build tool such as VEAF
Mission Creation Tools. The `mission` table is read and written here without Lua: the writer
follows the layout of the file it read (indent, line ending, `["key"]` or bare `key`, where a
table opens and how it closes, `{}` or an open pair for an empty table), so a table it does not
change comes back as the same text, and numbers are kept as they were written.
"""
import argparse
import collections
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
USER_FOLDERS = ("user-lib", "user-f10", "user-inbox", "user-outbox")


def say(message):
    print(f"hotload-setup: {message}")


# ── The Lua table format of a .miz ──────────────────────────────────────────────────────────────

class FormatError(Exception):
    pass


class Num(str):
    """A number as the file wrote it: kept as text, so writing it back changes nothing."""


class Style:
    """How a file is laid out. The Mission Editor's layout is the default:
    indent        the indent unit
    compact_empty an empty table is written `{}`, not as an open pair
    bare_keys     a key that is a Lua name is written `key =`, not `["key"] =`
    inline_open   a table opens on its key's line, `key = {`, not on the next
    end_comments  a table closes with `}, -- end of <key>`
    head          what follows `<name> =` up to the outer table's `{`
    tail          what follows the outer table's `}`; None for ` -- end of <name>` and a newline
    newline       the line ending
    """

    def __init__(self, indent, compact_empty, bare_keys=False, inline_open=False, end_comments=True,
                 head=" \n", tail=None, newline="\n"):
        self.indent, self.compact_empty, self.bare_keys = indent, compact_empty, bare_keys
        self.inline_open, self.end_comments = inline_open, end_comments
        self.head, self.tail, self.newline = head, tail, newline

    @classmethod
    def of(cls, text):
        newline = "\r\n" if "\r\n" in text else "\n"
        text = text.replace("\r\n", "\n")
        top = re.match(r"\s*\w+ =([ \t]*\n?[ \t]*)\{\n([ \t]+)(\[?)", text)
        head, indent, bracket = top.groups() if top else (" \n", "\t", "[")
        nested = re.search(r"\n[ \t]+(?:\[[^\]\n]+\]|\w+) =( \{|[ \t]*\n[ \t]*\{)\n", text)
        inline_open = bool(nested) and nested.group(1) == " {"
        end_comments = bool(re.search(r"\}, -- end of ", text))
        if re.search(r"= \{\},", text):
            compact = True
        elif re.search(r"=[ \t]*\n?[ \t]*\{\n[ \t]*\},", text):
            compact = False
        else:
            compact = indent == "\t" or not end_comments
        m = re.search(r"\}([^}]*)\Z", text)
        tail = m.group(1) if m else None
        return cls(indent, compact, bracket != "[", inline_open, end_comments, head, tail, newline)


ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "a": "\a", "b": "\b", "f": "\f", "v": "\v",
           "\\": "\\", '"': '"', "'": "'", "\n": "\n"}
NUMBER = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
NAME = re.compile(r"[A-Za-z_]\w*\Z", re.A)
KEYWORDS = frozenset("and break do else elseif end false for function if in local nil not or repeat "
                     "return then true until while".split())


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
        m = re.compile(r"[A-Za-z_]\w*", re.A).match(self.text, self.pos)
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
                if self.text.startswith("\r\n", self.pos + 1):
                    out.append("\n")
                    self.pos += 3
                elif e in ESCAPES:
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
            if self.peek() != "[":
                key = self.name()
                if key in KEYWORDS:
                    self.fail(f"expected a key, found {key!r}")
            else:
                self.pos += 1
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


def lua_key(key, bare=False):
    if isinstance(key, int):
        return f"[{key}]"
    if bare and NAME.match(key) and key not in KEYWORDS:
        return key
    return f"[{lua_quote(key)}]"


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
    """Writes `name = { ... }` in the given style."""
    out = [f"{name} ={style.head}{{\n"]

    def entries(table, depth):
        pad = style.indent * depth
        for key, v in table.items():
            k = lua_key(key, style.bare_keys)
            if not isinstance(v, dict):
                out.append(f"{pad}{k} = {lua_scalar(v)},\n")
            elif not v and style.compact_empty:
                out.append(f"{pad}{k} = {{}},\n")
            else:
                out.append(f"{pad}{k} = {{\n" if style.inline_open else f"{pad}{k} = \n{pad}{{\n")
                entries(v, depth + 1)
                out.append(f"{pad}}}, -- end of {k}\n" if style.end_comments else f"{pad}}},\n")

    entries(value, 1)
    out.append("}" + (f" -- end of {name}\n" if style.tail is None else style.tail))
    text = "".join(out)
    return text if style.newline == "\n" else text.replace("\n", style.newline)


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


# The boot trigger: a first DO SCRIPT sets BASE_HOTLOAD_PATH, the second (BOOT_GUARD) loads
# dcs-hotload.lua from it, or logs one line when it cannot. A bare dofile, the boot this script
# wrote before, is still recognized: it is "unguarded".

BOOT_GUARD = (Path(__file__).resolve().parent / "boot-guard.lua").read_text(encoding="utf-8").rstrip("\n")
LUA_NAME = "dcs-hotload.lua"
Boot = collections.namedtuple("Boot", "where path guarded")   # path: the dcs-hotload.lua, "" when cleared

PATH_LINE = re.compile(r"""\s*BASE_HOTLOAD_PATH\s*=\s*(?:\[(=*)\[(.*?)\]\1\]|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')"""
                       r"""\s*;?\s*\Z""", re.S)


def lua_long(s):
    """A Lua long string holding s: [[s]], with as many = as it takes not to close early."""
    level = ""
    while f"]{level}]" in s:
        level += "="
    return f"[{level}[{s}]{level}]"


def path_line(folder):
    return f"BASE_HOTLOAD_PATH = {lua_long(folder)}"


def path_of(m):
    """The text of a string literal matched as groups (level, long, double, single)."""
    if m.group(2) is not None:
        return m.group(2)
    return (m.group(3) if m.group(3) is not None else m.group(4) or "").replace("\\\\", "\\")


def lua_in(folder):
    if not folder:
        return ""
    sep = "\\" if "\\" in folder and "/" not in folder else "/"
    return folder.rstrip("\\/") + sep + LUA_NAME


BOOT = re.compile(r"""dofile\s*\(\s*(?:\[(=*)\[(.*?)\]\1\]|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')\s*\)""",
                  re.S)


def boot_paths(text):
    paths = []
    for m in BOOT.finditer(text):
        path = path_of(m)
        if path.replace("\\", "/").lower().endswith(LUA_NAME):
            paths.append(path)
    return paths


def scripts(miz):
    """Each DO SCRIPT action of the triggers: (trigger index, action dict)."""
    for n, rule in miz.mission.get("trigrules", {}).items():
        for action in rule.get("actions", {}).values():
            if isinstance(action, dict) and action.get("predicate") == "a_do_script":
                yield n, action


def find_boot(miz):
    """Every place the mission boots a dcs-hotload.lua: [Boot]."""
    found = []
    for n, action in scripts(miz):
        text = action.get("text", "")
        m = PATH_LINE.match(text)
        if m:
            found.append(Boot(f"trigger {n}", lua_in(path_of(m)), True))
        else:
            found += [Boot(f"trigger {n}", p, False) for p in boot_paths(text)]
    for name, data in miz.entries.items():
        if name.startswith("l10n/") and name.lower().endswith(".lua"):
            found += [Boot(f"embedded {name}", p, False) for p in boot_paths(data.decode("utf-8", "replace"))]
    return found


def add_boot(miz, folder):
    """A MISSION START trigger setting BASE_HOTLOAD_PATH to `folder`, then running the guard:
    trigrules (what the editor shows) and trig (what DCS runs), index for index."""
    rules = miz.mission.setdefault("trigrules", {})
    trig = miz.mission.setdefault("trig", {})
    for part in ("actions", "conditions", "flag", "funcStartup"):
        trig.setdefault(part, {})
    n = max([k for k in rules if isinstance(k, int)] + [0]) + 1
    texts = (path_line(folder), BOOT_GUARD)
    rules[n] = {"comment": "dcs-hotload boot", "predicate": "triggerStart", "eventlist": "",
                "colorItem": "0x00ffffff", "rules": {},
                "actions": {i: {"predicate": "a_do_script", "text": t} for i, t in enumerate(texts, 1)}}
    trig["actions"][n] = "".join(f"a_do_script({lua_quote(t)});" for t in texts)
    trig["conditions"][n] = "return(true)"
    trig["flag"][n] = True
    trig["funcStartup"][n] = f"if mission.trig.conditions[{n}]() then mission.trig.actions[{n}]() end"


def replace_in_trigger(miz, n, action, new_text):
    """Rewrites a DO SCRIPT action in both copies DCS keeps: the trigrules text and the compiled
    trig.actions string, which must hold the old text exactly once."""
    actions = miz.mission.get("trig", {}).get("actions", {})
    old_q, new_q = lua_quote(action["text"]), lua_quote(new_text)
    compiled = actions.get(n, "")
    if compiled.count(old_q) != 1:
        raise FormatError(f"trigger {n}: the compiled trigger does not hold its DO SCRIPT text once")
    actions[n] = compiled.replace(old_q, new_q)
    action["text"] = new_text


def retarget_boot(miz, boot, folder):
    """Points a Boot found by find_boot at `folder`, keeping its form."""
    if boot.guarded:
        for n, action in scripts(miz):
            if f"trigger {n}" == boot.where and PATH_LINE.match(action.get("text", "")):
                replace_in_trigger(miz, n, action, path_line(folder))
        return
    old, new = boot.path, lua_in(folder)
    for n, action in scripts(miz):
        if f"trigger {n}" == boot.where and old in action.get("text", ""):
            replace_in_trigger(miz, n, action, action["text"].replace(old, new))
    name = boot.where[len("embedded "):]
    if boot.where.startswith("embedded ") and name in miz.entries:
        miz.entries[name] = miz.entries[name].replace(old.encode("utf-8"), new.encode("utf-8"))


def same_path(a, b):
    def norm(p):
        return posixpath.normpath(p.replace("\\", "/")).lower()
    return bool(a) and bool(b) and norm(a) == norm(b)


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


def is_dcs(path):
    return (Path(path) / "Scripts" / "MissionScripting.lua").is_file()


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
    # An empty user-f10/ beside a mission's user-scripts/ would hide hotload's own rename message.
    renaming = (target / "user-scripts").is_dir() and not (target / "user-f10").exists()
    for folder in USER_FOLDERS:
        if not (renaming and folder == "user-f10"):
            (target / folder).mkdir(exist_ok=True)
    if renaming:
        say(f"rename user-scripts/ to user-f10/ in {target}: the F10 menu reads only user-f10/")
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
    if not is_dcs(dcs_arg):
        say(f"not a DCS install (no Scripts/MissionScripting.lua): {dcs_arg}")
        return FAIL
    dcs = Path(dcs_arg)
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


def unguarded_note(boot):
    return (f"{boot.where} boots with a bare dofile: where that file is missing, as on a player's "
            "machine, DCS shows a script error. Remove it and run patch-miz for a boot that only logs")


def what_it_loads(boot):
    return f"its boot path is cleared ({boot.where})" if not boot.path else f"loads {boot.path} ({boot.where})"


def patch_miz(miz_path, mission, retarget):
    folder = str((mission / "dcs-hotload").resolve())
    lua = lua_in(folder)
    miz = Miz.read(miz_path)
    found = find_boot(miz)
    here = [b for b in found if same_path(b.path, lua)]
    if here:
        say(f"{miz_path.name} already loads {lua}")
        for boot in here:
            if not boot.guarded:
                say(unguarded_note(boot))
        return OK
    if found and not retarget:
        for boot in found:
            say(f"{miz_path.name} {what_it_loads(boot)}, not {lua}")
        say("rerun with --retarget to point it at this mission's copy, once the user agrees")
        return DECIDE
    backup = miz_path.with_name(miz_path.name + ".bak")
    if not backup.exists():
        shutil.copy2(miz_path, backup)
    if found:
        for boot in found:
            retarget_boot(miz, boot, folder)
            say(f"{boot.where}: now loads {lua}")
    else:
        add_boot(miz, folder)
        say(f"added a MISSION START trigger loading {lua} where it is there, and only logging elsewhere")
    miz.write(miz_path)
    say("re-open the mission from the Mission menu: Restart replays the copy loaded at launch")
    return OK


def boot_path(miz_path, set_dir, clear):
    miz = Miz.read(miz_path)
    found = find_boot(miz)
    guarded = [b for b in found if b.guarded]
    if not guarded:
        for boot in found:
            say(unguarded_note(boot))
        say(f"{miz_path.name} has no BASE_HOTLOAD_PATH" + ("" if found else ": run patch-miz"))
        return FAIL
    if len(guarded) > 1:
        say(f"{miz_path.name} sets BASE_HOTLOAD_PATH {len(guarded)} times ("
            + ", ".join(b.where for b in guarded) + "): keep one")
        return FAIL
    boot = guarded[0]
    current = boot.path[:-len(LUA_NAME)].rstrip("\\/") if boot.path else ""
    if set_dir is None and not clear:
        say(f"{miz_path.name}: BASE_HOTLOAD_PATH " + (f"= {current}" if current else "is cleared")
            + f" ({boot.where})")
        return OK
    folder = ""
    if not clear:
        folder = str(Path(set_dir).resolve())
        if not (Path(folder) / LUA_NAME).is_file():
            say(f"no dcs-hotload.lua in {folder}")
            return FAIL
    if current == folder or same_path(current, folder):
        say(f"{miz_path.name}: BASE_HOTLOAD_PATH is already " + (folder or "cleared"))
        return OK
    retarget_boot(miz, boot, folder)
    miz.write(miz_path)
    say(f"{miz_path.name}: BASE_HOTLOAD_PATH " + (f"= {folder}" if folder else "cleared")
        + ("" if folder else ": the mission only logs where it starts"))
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

    if not is_dcs(dcs_arg):
        say(f"not a DCS install (no Scripts/MissionScripting.lua): {dcs_arg}")
        ready = False
    else:
        locked = locked_modules(Path(dcs_arg) / "Scripts" / "MissionScripting.lua")
        say("MissionScripting.lua: " + (f"{' and '.join(locked)} locked: run unlock" if locked else "unlocked"))
        ready = ready and not locked

    mizs = [Path(miz_arg)] if miz_arg else sorted(mission.glob("*.miz"))
    if len(mizs) != 1:
        say(f"{len(mizs)} .miz files in {mission}: pass --miz")
        return DECIDE
    expected = str(lua.resolve())
    found = find_boot(Miz.read(mizs[0]))
    here = [b for b in found if same_path(b.path, expected)]
    if here:
        say(f"{mizs[0].name} loads this mission's dcs-hotload")
        for boot in here:
            if not boot.guarded:
                say(unguarded_note(boot))
    else:
        say(f"{mizs[0].name} " + (f"{what_it_loads(found[0])} instead: patch-miz --retarget" if found
                                   else "does not load dcs-hotload: run patch-miz"))
        ready = False
    return OK if ready else DECIDE


def main(argv=None):
    p = argparse.ArgumentParser(prog="hotload-setup.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--mission", default=".")
    s.add_argument("--dcs", required=True)
    s.add_argument("--miz")
    d = sub.add_parser("deploy")
    d.add_argument("--mission", default=".")
    d.add_argument("--update", action="store_true")
    u = sub.add_parser("unlock")
    u.add_argument("--dcs", required=True)
    u.add_argument("--yes", action="store_true")
    m = sub.add_parser("patch-miz")
    m.add_argument("miz")
    m.add_argument("--mission", default=".")
    m.add_argument("--retarget", action="store_true")
    b = sub.add_parser("boot-path")
    b.add_argument("miz")
    change = b.add_mutually_exclusive_group()
    change.add_argument("--set", metavar="DIR")
    change.add_argument("--clear", action="store_true")
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
        if args.cmd == "boot-path":
            return boot_path(Path(args.miz), args.set, args.clear)
        return patch_miz(Path(args.miz), Path(args.mission), args.retarget)
    except (FormatError, zipfile.BadZipFile, KeyError) as e:
        say(f"cannot read the mission: {e}")
        return FAIL


if __name__ == "__main__":
    sys.exit(main())
