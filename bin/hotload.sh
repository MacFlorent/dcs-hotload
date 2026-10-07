#!/usr/bin/env bash
# hotload.sh -- drive a running DCS mission through dcs-hotload's mailbox, in one call.
#
#   bash hotload.sh run   [--root DIR] [--name NAME] [--timeout S] [--keep] (-e 'LUA' | FILE.lua)
#   bash hotload.sh log   [--log FILE] [PATTERN]     HOTLOAD lines since the last "ready"
#   bash hotload.sh check [--miz FILE] SCRIPT SRC    is SCRIPT embedded in the running mission == SRC?
#
# run: writes user-inbox/NAME.lua atomically, waits for user-outbox/NAME.lua to leave "started",
#      prints it, deletes both files (unless --keep). Exit 0 done, 1 fail/refused/stopped,
#      2 timeout (files left so a later call or a look can pick the result up), 3 usage/setup.
# Root defaults to $HOTLOAD_ROOT, then ./dcs-hotload. Timeout defaults to 600 s.
set -u

die() { echo "hotload.sh: $*" >&2; exit 3; }

default_log() { echo "${USERPROFILE:-$HOME}/Saved Games/DCS/Logs/dcs.log"; }

cmd_run() {
  local root="${HOTLOAD_ROOT:-./dcs-hotload}" name timeout=600 keep=0 code="" file=""
  name="c$(date +%s)$$"
  while [ $# -gt 0 ]; do
    case "$1" in
      --root) root="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      --timeout) timeout="$2"; shift 2 ;;
      --keep) keep=1; shift ;;
      -e) code="$2"; shift 2 ;;
      *) file="$1"; shift ;;
    esac
  done
  [ -d "$root/user-inbox" ] && [ -d "$root/user-outbox" ] || die "no user-inbox/ and user-outbox/ under $root (mailbox off?)"
  [ -n "$code" ] || [ -n "$file" ] || die "give -e 'LUA' or a .lua file"
  local inbox="$root/user-inbox/$name.lua" outbox="$root/user-outbox/$name.lua"
  [ -e "$inbox" ] || [ -e "$outbox" ] && die "$name already in the mailbox; pick another --name or delete it"

  # Atomic: hotload only picks up *.lua, so it never sees a half-written command.
  if [ -n "$code" ]; then printf '%s\n' "$code" > "$inbox.tmp"; else cp "$file" "$inbox.tmp" || die "cannot read $file"; fi
  mv "$inbox.tmp" "$inbox"

  local waited=0 status=""
  while [ "$waited" -lt $((timeout * 2)) ]; do
    if [ -f "$outbox" ]; then
      status=$(sed -n 's/^  \["status"\] = "\([a-z]*\)",$/\1/p' "$outbox")
      [ -n "$status" ] && [ "$status" != "started" ] && break
    fi
    sleep 0.5; waited=$((waited + 1))
  done
  if [ -z "$status" ] || [ "$status" = "started" ]; then
    echo "hotload.sh: no final result after ${timeout}s (status: ${status:-not picked up}); files kept: $inbox" >&2
    exit 2
  fi
  cat "$outbox"
  [ "$keep" -eq 1 ] || rm -f "$inbox" "$outbox"
  [ "$status" = "done" ] && exit 0 || exit 1
}

cmd_log() {
  local log pattern=""
  log="$(default_log)"
  while [ $# -gt 0 ]; do
    case "$1" in
      --log) log="$2"; shift 2 ;;
      *) pattern="$1"; shift ;;
    esac
  done
  [ -f "$log" ] || die "no log at $log"
  local start
  start=$(grep -n "HOTLOAD: ready" "$log" | tail -1 | cut -d: -f1)
  [ -n "$start" ] || die "no 'HOTLOAD: ready' in $log (hotload not loaded this session?)"
  echo "# dcs.log times are UTC" >&2
  tail -n +"$start" "$log" | grep "HOTLOAD" | grep -- "${pattern}" | sed 's/ INFO    SCRIPTING (Main): HOTLOAD://'
}

cmd_check() {
  local miz="${TEMP:-/tmp}/DCS/tempMission.miz"
  while [ $# -gt 0 ]; do
    case "$1" in
      --miz) miz="$2"; shift 2 ;;
      *) break ;;
    esac
  done
  [ $# -eq 2 ] || die "check needs SCRIPT (name inside the .miz, e.g. mt-m4.lua) and SRC (file on disk)"
  [ -f "$miz" ] || die "no running-mission copy at $miz"
  local running ondisk
  running=$(unzip -p "$miz" "l10n/DEFAULT/$1" 2>/dev/null | md5sum | cut -d' ' -f1)
  ondisk=$(md5sum < "$2" | cut -d' ' -f1)
  if [ "$running" = "d41d8cd98f00b204e9800998ecf8427e" ]; then
    echo "NOT EMBEDDED: $1 is not in the running mission ($miz, written $(date -r "$miz" '+%F %T'))"; exit 1
  elif [ "$running" = "$ondisk" ]; then
    echo "MATCH: the running mission embeds $2 as it is on disk"; exit 0
  else
    echo "DIFFERENT: the running mission ($miz, written $(date -r "$miz" '+%F %T')) embeds another version of $1 -- re-open the rebuilt .miz from the Mission menu (Restart replays the old copy)"; exit 1
  fi
}

case "${1:-}" in
  run) shift; cmd_run "$@" ;;
  log) shift; cmd_log "$@" ;;
  check) shift; cmd_check "$@" ;;
  *) die "usage: bash hotload.sh run|log|check ...  (see the header of this file)" ;;
esac
