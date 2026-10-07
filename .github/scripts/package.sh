#!/usr/bin/env bash
# package.sh -- build the release package of dcs-hotload.
#
#   bash .github/scripts/package.sh [VERSION]      VERSION defaults to Hotload.version
#
# Stages dist/dcs-hotload/ from the allowlist below, zips it as dist/dcs-hotload-VERSION.zip
# (skipped when zip is not installed, as in Git Bash), and writes the body of CHANGELOG.md's
# "## [VERSION]" section to dist/notes.md when there is one. CONTRIBUTING.md says how a release
# is made.
set -euo pipefail

cd "$(dirname "$0")/../.."

# What a mission gets. An allowlist, so a new file ships only once it is named here. LICENSE.md
# because the license requires a copy in every redistribution.
shipped=(dcs-hotload.lua README.md LICENSE.md bin examples skills)

die() { echo "package: $*" >&2; exit 1; }

version="${1:-$(sed -n 's/^Hotload\.version = "\([^"]*\)".*/\1/p' dcs-hotload.lua)}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "version '$version' is not x.y.z"

for path in "${shipped[@]}"; do
  [ -e "$path" ] || die "$path is missing"
done

rm -rf dist
mkdir -p dist/dcs-hotload
cp -R "${shipped[@]}" dist/dcs-hotload/
# Git for Windows records every file as non-executable; the package does not depend on it.
chmod +x dist/dcs-hotload/bin/hotload.sh
echo "package: staged dist/dcs-hotload/"

# Release notes: the lines between "## [VERSION]" and the next "## [" heading. index() rather
# than a regex, so the dots of the version are literal.
awk -v head="## [$version]" '
  index($0, "## [") == 1 { if (inside) exit; inside = (index($0, head) == 1); next }
  inside { print }
' CHANGELOG.md > dist/notes.md
if grep -q '[^[:space:]]' dist/notes.md; then
  echo "package: release notes in dist/notes.md"
else
  rm dist/notes.md
  echo "package: no CHANGELOG.md section for $version, no release notes"
fi

if command -v zip > /dev/null; then
  (cd dist && zip -qr "dcs-hotload-$version.zip" dcs-hotload)
  echo "package: dist/dcs-hotload-$version.zip"
else
  echo "package: zip is not installed, only dist/dcs-hotload/ was built"
fi
