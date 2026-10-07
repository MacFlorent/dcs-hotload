# Release pipeline

Status: in-progress

## Problem

dcs-hotload is ready for 1.0.0, but a release is only a tag: whoever wants it clones the repository
and copies the right files into a mission by hand, tests, tracker and guidance files included or
picked out one by one. A mission needs a `dcs-hotload/` folder holding only what runs or documents
the tool.

## What to build

Two pull requests:

1. `chore/release-pipeline` — the packaging script, the release workflow, the documentation below.
2. `release/1.0.0` — the version bump, following the new process; its tag `v1.0.0` is the first
   real run of the pipeline.

### The package

`dcs-hotload-<version>.zip`, with a single root folder `dcs-hotload/` holding exactly:

- `dcs-hotload.lua`
- `README.md`
- `LICENSE.md` — Apache 2.0 requires a copy of the license in any redistribution
- `bin/`
- `examples/`
- `skills/`

Extracted into a mission folder, it gives `<mission>/dcs-hotload/`, the path the README and the
skill expect.

### `.github/scripts/package.sh [version]`

Bash, `set -euo pipefail`, ShellCheck-clean. Outside `bin/` because `bin/` is shipped.

1. Version: the argument, or else the `Hotload.version` line of `dcs-hotload.lua`.
2. Empty `dist/`, then copy the allowlist into `dist/dcs-hotload/`. A missing allowlisted path fails
   the script.
3. `chmod +x dist/dcs-hotload/bin/hotload.sh`, whatever mode git recorded.
4. `cd dist && zip -r dcs-hotload-<version>.zip dcs-hotload`. When `zip` is not installed (Git Bash
   does not ship it), say the zip was skipped and exit 0: the staged folder is what a local check
   inspects; the zip comes from CI.
5. Write the body of the `## [<version>]` section of `CHANGELOG.md` to `dist/notes.md` when the
   section exists.

`dist/` is added to `.gitignore`.

### `.github/workflows/release.yml`

Triggers: `push` of a `v*` tag, and `workflow_dispatch` (dry run).

- **`test`** — reuses `ci.yml`, which gains a `workflow_call` trigger.
- **`release`** — needs `test`; `permissions: contents: write` on this job only.
  1. Checkout with full history.
  2. Version: from the tag (`v1.0.0` → `1.0.0`), or `Hotload.version` on a manual run.
  3. Checks. On a tag, each fails the run:
     - the version equals `Hotload.version`;
     - the tagged commit is on `origin/main` (`git merge-base --is-ancestor`);
     - `CHANGELOG.md` has a `## [<version>]` section.

     On a manual run, a missing changelog section is a warning only: the dry run happens before the
     release pull request renames `[Unreleased]`.
  4. `bash .github/scripts/package.sh <version>`.
  5. Upload the zip as a workflow artifact, on both triggers.
  6. On a tag only: `gh release create v<version> dist/dcs-hotload-<version>.zip --title
     "dcs-hotload <version>" --notes-file dist/notes.md`. A tag pushed again fails here, because
     the release exists: a tag is never moved.

### CI

`ci.yml` gains a ShellCheck step over `bin/hotload.sh` and `.github/scripts/package.sh`
(ShellCheck is preinstalled on the runner). A finding in `bin/hotload.sh` is fixed in its own
commit, with a changelog entry if its behaviour changes.

### Documentation

- **`README.md`**
  - Setup gains a first step: download `dcs-hotload-<version>.zip` from the GitHub releases and
    extract it into the mission folder; the `dofile` example points at `<mission>/dcs-hotload/`.
  - No version numbers: the ready line reads `dcs-hotload <version> ready`, so a release never
    edits the README.
  - *Development* names `CONTRIBUTING.md` and `CHANGELOG.md` as plain text, without links or the
    repository URL: links break inside the zip, absolute URLs point at `main` from a branch and
    break when the repository is forked or moved. Someone with the zip who wants to contribute
    finds the repository on their own.
  - The `## License` section is removed: `LICENSE.md` sits next to the README in the repository
    and in the package.
- **`CONTRIBUTING.md`**
  - *Layout* gains `.github/scripts/package.sh` (builds the release package) and `dist/` (its
    output, git-ignored).
  - *Releasing* becomes: an optional dry run (run the *Release* workflow by hand and check the zip
    it attaches; locally, `bash .github/scripts/package.sh` stages `dist/dcs-hotload/`); the
    `release/x.y.z` pull request as today; the `v<x.y.z>` tag on `main`, which checks and publishes.
    It states what the package holds and that `package.sh` is an allowlist, so shipping a new file
    means adding it there.
- **`CLAUDE.md`** — one row in *Before you do these, read*: "cut a release, or change what a
  release ships | `CONTRIBUTING.md`".
- **`CHANGELOG.md`** — no entry: neither `dcs-hotload.lua` nor `bin/hotload.sh` changes.

### The 1.0.0 release

The `release/1.0.0` pull request sets `Hotload.version = "1.0.0"` and turns `[Unreleased]` into
`[1.0.0] — <date>`. Its text, "First version, 0.1.0.", is reworded: 0.1.0 was never tagged, so
1.0.0 is the first release.

## Decisions

- **Triggered by a tag**, which keeps the existing release flow. Turned down: a manual workflow
  that creates the tag itself (the tag stops being the deliberate act); a local script with manual
  upload (no checks, easy to ship a dirty tree).
- **Dry run by manual trigger**, building the zip as a workflow artifact without publishing, so the
  package can be inspected before the first tag.
- **An allowlist in a script.** Turned down: `git archive` with `export-ignore` attributes (a
  denylist: every new top-level file ships unless someone excludes it); everything inline in the
  workflow (cannot be run or checked locally).
- **The README ships**: `skills/piloting-dcs-hotload/SKILL.md` names it as the protocol reference
  inside the mission's `dcs-hotload/`, and a mission folder reopened months later explains itself.
- **The tests are reused** from `ci.yml` through `workflow_call`, not copied.
- **`gh release create`**, already on the runner, rather than a third-party release action.

## Out of scope

- Pre-release handling (`-rc` versions), checksums, signing.
- Other channels (LuaRocks).
- Bumping the version automatically.
- Recording the executable bit of `bin/hotload.sh` in git: the package sets it, but clones still
  lack it; the entry stays in `IDEAS.md`.

## Verification

- `package.sh` run locally: `find dist/dcs-hotload` lists exactly the allowlist; a missing
  allowlisted path fails it.
- The pull request's CI passes, ShellCheck included.
- After merge, a manual run: the artifact zip has one `dcs-hotload/` root, the allowlist, and
  `hotload.sh` at mode 755 (`zipinfo`); the changelog warning shows.
- `v1.0.0`: the GitHub release appears with the zip and the 1.0.0 notes. Extracted into a mission
  and flown (only the maintainer can): the ready line says `1.0.0`.

## Comments
