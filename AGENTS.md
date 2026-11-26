# Instructions for coding agents

Sovereign Realms is an Unreal Engine 5.8 game developed by one person on two machines, a Mac and a Windows PC.
`README.md` describes the project, the setup and the *Development workflow*. This file turns that workflow into
procedures an agent follows when the owner says something short like "push to dev".

## Branches

| Branch | Who uses it |
| --- | --- |
| `mac` | the Mac only. It is the Mac's working branch, local (a backup copy on GitHub is optional) |
| `windows` | the Windows PC only. It is the PC's working branch, local (a backup copy on GitHub is optional) |
| `dev` | both machines. It is the shared integration branch on GitHub |
| `main` | production. It is updated only by *Promote to main* below |

### Which machine am I on?

Work this out before any git operation. Never guess from a branch name.

- `uname -s` prints `Darwin`: this is the Mac, and the working branch is **`mac`**.
- `uname -s` prints something starting with `MINGW`, `MSYS` or `CYGWIN`, or `$env:OS` / `%OS%` is `Windows_NT`: this
  is the PC, and the working branch is **`windows`**.
- Anything else: stop and ask the owner.

### Hard rules

- **Never touch the other machine's branch.** On the Mac, do not check out, commit to, merge from, merge into, rebase,
  push, delete or reset `windows`. On the PC, the same applies to `mac`. The other machine's work reaches you only
  through `dev`.
- Commit only on this machine's working branch. Never commit directly on `dev` or `main`: they move only by merging.
- Never force-push, and never rewrite history that has been pushed (no `--force`, `reset --hard` to an older commit of
  a pushed branch, or rebase of `dev` or `main`).
- Never update `main` unless the owner explicitly asks for it (see *Promote to main*).
- Push the working branch only when the owner asks for a backup.
- If this machine's working branch does not exist yet, create it from the latest `dev`:
  `git fetch origin && git checkout -b <mine> origin/dev`. If `origin/<mine>` exists (an earlier backup), use
  `git checkout -b <mine> origin/<mine>` instead, then sync it with *Sync with dev*.

`<mine>` below means `mac` or `windows`, whichever this machine is.

## "Sync with dev" / "pull dev" / "get the latest"

Bring the other machine's work into this machine's branch. Do this without being asked at the start of a work session
and as the first part of *Push to dev*.

1. Find `<mine>`, then run `git checkout <mine>`.
2. Uncommitted changes: if they are the work in progress, commit them on `<mine>` first, or stash them and restore them
   after step 4. If it is unclear what they are, ask.
3. Run `git fetch origin`, then check whether `dev` has anything new: `git log --oneline <mine>..origin/dev`.
   - If nothing is listed, the branch is already up to date. Say so and stop here.
   - If commits are listed, tell the owner what came in (the commits, and the main files touched:
     `git diff --stat <mine>...origin/dev`).
4. Merge `origin/dev` into `<mine>`: `git merge origin/dev`.
   - Conflicts in text files (code, config, docs): resolve them so both sides' intent survives, build, and explain
     what was resolved.
   - Conflicts in binary files (`.uasset`, `.umap`, images, sounds): they cannot be merged. Stop and ask the owner
     which side to keep.
5. Also move the local `dev` up to date: `git branch -f dev origin/dev`. This is only safe when the local `dev` has
   nothing that `origin/dev` lacks, so first check that `git log --oneline origin/dev..dev` is empty. If it is not
   empty, stop and report.
6. If the merge brought in changes to `Source/`, `Config/` or `*.uproject`, compile the editor target before carrying
   on. On the Mac: `sh Tools/mac/editor.sh build` (the editor must be closed). If the editor is open, do not quit it. Copy
   `Source/`, `Config/` and `SovereignRealms.uproject` into a temporary folder and run the engine's
   `Engine/Build/BatchFiles/Mac/Build.sh SovereignRealmsEditor Mac Development -Project=<copy>/SovereignRealms.uproject`
   on the copy, then delete the copy. On Windows: `Build.bat SovereignRealmsEditor Win64 Development
   -Project="<path>\SovereignRealms.uproject"` from the engine's `Engine\Build\BatchFiles`.

## "Push to dev"

Integrate this machine's work into `dev` and publish it so the other machine can pull it. The owner does not need to
say anything about pulling first. Always check for new work on `dev` yourself.

1. Run *Sync with dev* steps 1 to 6 above. These commit any pending work on `<mine>` and merge any new `dev` commits
   into `<mine>`.
2. If `git log --oneline origin/dev..<mine>` lists nothing, there is nothing to push. Say so and stop.
3. Make sure it builds. If anything under `Source/`, `Config/` or `*.uproject` changed since `origin/dev`, the compile
   from step 6 of *Sync* must have passed. Do not push a branch that does not compile.
4. Update `dev` with a fast-forward only. `<mine>` already contains `origin/dev`, so this cannot create a merge commit:

   ```sh
   git checkout dev
   git merge --ff-only origin/dev
   git merge --ff-only <mine>
   ```

   If either `--ff-only` refuses, something moved meanwhile. Go back to `<mine>` and run *Sync with dev* again. Do not
   fall back to an ordinary merge on `dev`.
5. Push: `git push origin dev`. This also uploads the Git LFS files and can take a long time for big asset changes.
   - If it is rejected as non-fast-forward, someone pushed meanwhile. Run `git checkout <mine>`, then *Sync with dev*,
     then repeat from step 4.
   - If the connection drops during the LFS upload, run `git lfs push origin dev` (it skips what is already there),
     then `git push origin dev` again.
   - If it fails on the LFS quota, stop and tell the owner. Never move LFS files into ordinary git to get around it.
6. Run `git checkout <mine>` and report:
   - what came in from `dev` (if anything);
   - what went out: the commits;
   - the new `dev` commit (`git rev-parse --short dev`), which the other machine will get at its next sync.

## "Promote to main" / "push to main"

Only when the owner asks for it explicitly. `main` must end up on a `dev` commit that was tested on both macOS and
Windows.

1. Run `git fetch origin` and confirm `origin/dev` is the commit the owner tested on both machines. Show
   `git rev-parse --short origin/dev` and ask if that has not been said. If anything was merged into `dev` after the
   tests, it has to be tested again on both machines first.
2. Update `main` with a fast-forward only, to exactly that commit:

   ```sh
   git checkout main
   git merge --ff-only origin/main
   git merge --ff-only origin/dev
   git push origin main
   git checkout <mine>
   ```

   If the `--ff-only` refuses, `main` has commits that `dev` lacks. Stop and report. The fix is to merge `main` into
   `dev` through a working branch and test that commit on both machines again.

## Everything else

How to build, package, test and make art is in `README.md`.
