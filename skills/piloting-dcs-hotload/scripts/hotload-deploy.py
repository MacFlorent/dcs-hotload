"""hotload-deploy.py -- copy dcs-hotload from the plugin into a mission folder. Python 3.8+, standard library only.

  python hotload-deploy.py [--mission DIR] [--update]
      Copy the tool into DIR/dcs-hotload/ (the release file set, .github/scripts/shipped.txt) and
      create its user-* folders. An older copy is replaced only with --update; user-* folders are
      never touched, but missing ones are created; a newer copy is left alone. DIR defaults to the
      current folder.

Exit codes: 0 done or nothing to do, 1 failed or refused, 2 a decision is needed (rerun with the
flag the message names), 3 usage.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

OK, FAIL, DECIDE, USAGE = 0, 1, 2, 3

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
USER_FOLDERS = ("user-lib", "user-f10", "user-inbox", "user-outbox")


def say(message):
    print(f"hotload-deploy: {message}")


def warn(message):
    print(f"hotload-deploy: {message}", file=sys.stderr)


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


def copy_shipped(target):
    target.mkdir(parents=True, exist_ok=True)
    for path in shipped():
        src = PLUGIN_ROOT / path
        if src.is_dir():
            shutil.copytree(src, target / path, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, target / path)


def deploy(mission, update):
    target = mission / "dcs-hotload"
    want = plugin_version()
    lua = target / "dcs-hotload.lua"
    if lua.exists():
        have = lua_version(lua)
        if have == want:
            say(f"dcs-hotload {have} is already deployed in {target}")
        elif have is None or version_key(have) > version_key(want):
            warn(f"{target} holds dcs-hotload {have}, not older than the plugin's {want}: left alone")
            return FAIL
        elif not update:
            warn(f"{target} holds dcs-hotload {have}; the plugin has {want}. A mission keeps the version it "
                 "was tested with: rerun with --update to replace it")
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


def main(argv=None):
    p = argparse.ArgumentParser(prog="hotload-deploy.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mission", default=".", metavar="DIR")
    p.add_argument("--update", action="store_true")
    try:
        args = p.parse_args(argv)
    except SystemExit as e:
        return OK if e.code == 0 else USAGE
    return deploy(Path(args.mission), args.update)


if __name__ == "__main__":
    sys.exit(main())
