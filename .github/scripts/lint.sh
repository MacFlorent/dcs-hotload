#!/usr/bin/env bash
#
# Runs luacheck over the repository, with .luacheckrc, locally and in CI (.github/workflows/ci.yml
# runs this script), from any working directory.
#
# Nothing has to be installed first. On Windows under Git Bash and on Linux x86-64, the script
# downloads a pinned release binary of luacheck into .tools/ (git-ignored), checks it against the
# SHA-256 below, and reuses it on later runs. The version lives here and nowhere else: bumping it
# means changing the version and the hashes of its assets. On any other platform -- macOS, for
# which luacheck publishes no binary -- luacheck is taken from PATH.
#
# Usage:  bash .github/scripts/lint.sh

set -euo pipefail

cd "$(dirname "$0")/../.."
readonly ROOT="$PWD"

readonly LUACHECK_VERSION=1.2.0

fail() {
	echo "lint.sh: $*" >&2
	exit 1
}

# --- tools ------------------------------------------------------------------------------------

platform() {
	case "$(uname -s)" in
	MINGW* | MSYS* | CYGWIN*) echo windows ;;
	Linux) [ "$(uname -m)" = x86_64 ] && echo linux || echo other ;;
	*) echo other ;;
	esac
}

# The release asset of a tool for a platform, and its SHA-256. Each platform gets only its own
# build: Git Bash resolves an extensionless `luacheck` before `luacheck.exe` in the same folder.
asset() {
	case "$1-$2" in
	luacheck-windows) echo "luacheck.exe 0f1c69c4d09f1ebb4d8df14c215e4553e2e639bd4cb7bf3c639b0daa6198317b" ;;
	luacheck-linux) echo "luacheck d68da17fca0697d9e2fb04201f3884abd259fa558b3a449bccaed47f1390defc" ;;
	*) return 1 ;;
	esac
}

release_url() {
	case "$1" in
	luacheck) echo "https://github.com/lunarmodules/luacheck/releases/download/v$LUACHECK_VERSION/$2" ;;
	esac
}

# Prints the path of the tool's executable, downloading it first if it is not cached yet. The cache
# directory carries the version, so a bump fetches the new binary instead of reusing the old one.
tool() {
	local name="$1" platform entry
	platform="$(platform)"
	if ! entry="$(asset "$name" "$platform")"; then
		command -v "$name" >/dev/null 2>&1 || fail "no pinned $name for this platform, and none on PATH"
		command -v "$name"
		return
	fi

	local file="${entry% *}" sha="${entry#* }" version exe
	version="$LUACHECK_VERSION"
	local dir="$ROOT/.tools/$name-$version"
	exe="$dir/$name"
	[ "$platform" = windows ] && exe="$exe.exe"
	if [ -x "$exe" ]; then
		echo "$exe"
		return
	fi

	echo "lint.sh: fetching $name $version into .tools/" >&2
	mkdir -p "$dir"
	local part="$dir/$file.part"
	curl -fsSL -o "$part" "$(release_url "$name" "$file")" || fail "could not download $file"
	local actual
	actual="$(sha256sum "$part" | cut -d ' ' -f 1)"
	if [ "$actual" != "$sha" ]; then
		rm -f "$part"
		fail "$file has SHA-256 $actual, expected $sha"
	fi
	mv "$part" "$exe"
	chmod +x "$exe"
	echo "$exe"
}

# --- entry point ------------------------------------------------------------------------------

luacheck="$(tool luacheck)"
"$luacheck" --codes .
