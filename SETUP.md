# Setup and Windows/Mac handoff

## Current starting point

This is a documentation-only handoff. Read [PLAN.md](PLAN.md) in full before implementation. Its design, scope, animation, lighting, interface, and review requirements remain authoritative. The prepared plan is preserved verbatim, including its original Mac-first setup sequence; the current handoff allows implementation to begin on Windows while the new Mac is pending. Keep the same visual review gates and validate on the actual Mac early.

There is no `.uproject`, game source, engine installation, or configured MCP server here yet. Create the real project through the chosen Unreal workflow. Choose a practical architecture, C++/Blueprint balance, character pipeline, and directory layout after inspecting the actual tools. Do not manufacture empty engine folders or separate Windows/Mac source copies.

## 1. Clone with Git LFS

Install [Git](https://git-scm.com/downloads) and [Git LFS](https://git-lfs.com/) on each machine first. Push access requires signing in to GitHub with an account authorized for this repository; never place credentials in the clone URL or repository files.

Run these commands from the parent folder where you want the checkout. They work in Windows PowerShell/Git Bash and macOS Terminal once Git and Git LFS are installed:

```sh
git --version
git lfs version
git lfs install
git clone https://github.com/KyleAnthonyHay/Sovereign-Realms.git
cd Sovereign-Realms
git lfs install --local
git lfs pull
git remote -v
git status --short --branch
git lfs ls-files
git lfs fsck
```

Confirm `origin` identifies `KyleAnthonyHay/Sovereign-Realms` and the current branch is `main`. The HTTPS clone URL is verified. An existing authorized SSH remote for the same repository is also acceptable. The three documentation reference PNGs are ordinary Git files and should be real images immediately after cloning. This initial skeleton has no LFS objects, so `git lfs ls-files` is initially empty. For future LFS assets, a `*` means a full local object is present; a `-` means a pointer remains. Fix authentication, network, or LFS storage/download errors before continuing; a Git commit alone does not prove all binary objects are available.

**Known hosting limitation, November 12, 2026:** GitHub rejected the initial reference-image LFS upload because the repository owner's account exceeded its LFS budget. A narrow exception stores only `references/*.png` in ordinary Git, allowing this documentation handoff to be cloned. LFS rules remain configured for future game assets; the account's LFS budget/access must be restored before those assets can be uploaded and downloaded. Do not bypass their LFS rules or commit game binaries into ordinary Git to conceal the blocker.

For an existing clean checkout, use `git pull --ff-only` followed by `git lfs pull` rather than cloning over it. If there is local work, save it in a commit or recoverable backup before changing branches or updating. Do not discard it to make a pull succeed.

## 2. Choose and record the shared toolchain

Use the **same exact stable Unreal release, including patch version**, on Windows and Mac. Do not choose a preview merely because it is newest. Check both operating systems, the intended Apple Silicon target, rendering support, compiler/SDK requirements, and every required plugin before selecting the release. Unreal and plugin compatibility depend on the release: use the version selector in Epic's documentation.

The new Mac's specifications are not yet known. A small Windows prototype can start after documenting the expected Mac compatibility; mark that assessment as documentation-based until tested on the actual machine. Do not equate a Windows editor session with Mac support or silently upgrade the project when switching machines.

Record the selected values here when they are known:

| Shared decision | Current state |
| --- | --- |
| Unreal exact release / installation distribution | Not selected |
| Real `.uproject` relative path | Not created |
| Windows OS, compiler, and SDK versions | Not verified |
| Apple Silicon model, memory, macOS, and Xcode versions | New Mac pending |
| Blender version and export workflow | Not selected |
| Unreal MCP repository, pinned release/commit, and dependencies | Not selected |
| Required plugins, versions, licenses, and both-platform support | Not selected |
| Validated local generation/build/package commands | Add after the real project exists |

For a source-built engine, also record the exact engine commit and shared installation procedure. Keep the engine itself outside this game repository. Record changes to the toolchain deliberately and update both machines together.

### Windows prerequisites

Install Epic Games Launcher and the selected stable Unreal version, with the components needed for Windows development. Install a Visual Studio release, C++ workloads/toolset, and Windows SDK compatible with that Unreal release; include Game development with C++ and follow Epic's release-specific requirements. Check available storage for the engine, project, asset sources, shader caches, and packaged builds. See [Epic's Visual Studio setup guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-visual-studio-development-environment-for-cplusplus-projects-in-unreal-engine).

Keep the working copy on a local Windows filesystem outside live cloud-sync folders. Native Windows Claude Code is a practical starting point for controlling a native Windows Unreal editor; if using WSL, verify filesystem paths, process access, and MCP connectivity across that boundary before making it the workflow.

### Mac prerequisites

Install the identical Unreal release and an Xcode/macOS/SDK combination supported by that release. Check [Epic's macOS development requirements](https://dev.epicgames.com/documentation/en-us/unreal-engine/macos-development-requirements-for-unreal-engine), including the rendering-feature matrix for the actual Apple Silicon model. Verify free storage and memory on arrival. Compile project code and source plugins locally; confirm all precompiled plugin dependencies include compatible Mac/ARM64 support. Validate rendering choices and a standalone native Apple Silicon build early.

### Blender and portable assets

Install Blender separately on each machine. Record its version and the import/export settings used once the asset workflow is chosen. Keep editable originals and required exports in version control under a sensible layout chosen during implementation. Use relative paths and pack required external textures into `.blend` files or store them at tracked relative paths; a texture linked only from one person's drive will break the handoff. Check scale, axes, material imports, skeletons, animation names, and reimport behavior with a small sample before producing a large asset set.

## 3. Configure the local implementation assistant

Install and authenticate local Claude Code using [Anthropic's setup documentation](https://code.claude.com/docs/en/setup). The user's intended implementation model is **Opus 5.5**; confirm the actual model name and availability in that account before selecting it. Do not invent a model identifier or substitute one silently.

Choose an Unreal MCP implementation only after checking its own maintained setup instructions, license, engine version, supported operating systems, and required editor plugins/runtimes. There is no selected server or verified install command in this repo. Use [Claude Code's MCP documentation](https://code.claude.com/docs/en/mcp) to register the chosen server in local/user scope on each machine. Keep machine-specific executable paths, tokens, ports, and personal configuration outside tracked files. Record the chosen server and version in the table above, plus a portable setup explanation without credentials.

Start the Unreal editor and establish connectivity with a harmless read operation supported by that server, such as inspecting the current project or listing actors. Confirm the result refers to this project before permitting editor changes. Check the connection again on the other operating system. Blender automation is a separate integration to select and verify if needed; an Unreal MCP connection does not configure it.

## 4. Create the real project and first review sample

After the shared engine decision, create a genuine Unreal project within this repository and record its relative path. Root versus a subdirectory is an implementation choice. Commit its `.uproject`, source if used, shared configuration, required content, and plugin descriptors/source. Regenerate IDE files and local build products on each machine. Once the real paths are known, add only build/generation commands actually tested with that toolchain; none are claimed as verified yet.

Read all three images in [PLAN.md](PLAN.md). The first sample should establish terrain, a tower, mine/farm examples, both troop types, camera scale, detailed materials, and mystical golden-hour lighting. Aim beyond the screenshots in clarity and dimensional detail. Core troop states are spawn/enter, idle, walk, attack, hit, and death, with responsive transitions and damage timing matched to presentation. Do not require coarse pixels, ray tracing, or any one costly rendering feature.

Show a HUD concept and original main-menu composition using reference C's approved dark-panel, gold-detail, icon, and faction-accent direction. Its screenshot shows a HUD, but the main-menu style reference is already supplied. Review the proposed layout and the environment sample before expanding.

Then complete the limited loop: one map; two recruitable troop types with multiple soldiers each; one buildable tower type; automatic gold and food from mines and farms; construction, selection, movement, combat, and animation. No workers. Recruitment location, exact troop identities, and victory rules remain decisions to resolve without expanding scope. Test a minimal opposing force before proposing strategic AI or large armies. Use the acceptance checks in PLAN.md and review motion, not just screenshots.

## 5. Source control and binary assets

The checked-in `.gitattributes` configures LFS **before** Unreal, Blender, art, and audio assets are added. It covers `.uasset`, `.umap`, `.blend`, and common interchange/texture/audio/video formats. Only the documentation PNGs under `references/` have an explicit ordinary-Git exception because of the hosting limitation above. `.uproject`, `.uplugin`, source, shared `.ini` configuration, and documentation remain normal text in Git. Review additional binary formats and vendor dependencies before adding them; extend LFS patterns first where appropriate. LFS does not grant redistribution rights.

The `.gitignore` excludes generated `Intermediate`, `Saved`, `DerivedDataCache`, ordinary `Binaries`, IDE caches, Blender backup files, designated package folders, secrets, and local assistant configuration. It intentionally allows plugin `Binaries` directories because some licensed vendor plugins cannot be rebuilt from source. Review those files individually: ignore regenerated binaries for source plugins with narrow rules; preserve required redistributable vendor binaries and dependencies under suitable LFS rules or document their licensed installation on both machines. Never blanket-delete plugin binaries or globally ignore every `.dll`, `.lib`, `.a`, or `.dylib`.

Keep meaningful Unreal `Build` resources (such as icons and packaging settings), shared `Config`, asset sources, and required plugin content. Do not ignore the entire `Build` directory. Verify any new project layout with `git check-ignore -v` before its first commit.

Use portable relative imports and consistent filename case in code, assets, and references. Perform case-only renames through an intermediate Git name so Windows and typical Mac filesystems receive the change. Avoid personal absolute paths in shared configs. Keep secrets in local credentials/environment storage. Include only content that may be committed to a public repository; licensed marketplace assets may need a documented separate installation.

Assign ownership before editing binary maps, Blueprints, Blender files, or other non-mergeable assets. Avoid simultaneous edits to the same binary on different machines or branches. Use supported LFS locks if the team adopts them, but branches alone do not make binary changes safely mergeable. Resolve asset moves and redirectors in Unreal and commit the related changes together.

## 6. Switch machines cleanly

On the source machine, save all assets and close Unreal and Blender so no unsaved changes remain. Review the files and stage only intended shared source, content, configuration, and documentation. Before committing, inspect:

```sh
git status --short
git diff --check
git diff --cached --check
git diff --cached --stat
git lfs status
```

Commit the staged work with a descriptive message. Then run:

```sh
git lfs fsck
git push origin main
git lfs push --dry-run origin main
git status --short --branch
git rev-parse HEAD
```

These commands assume `main` is the intended handoff branch. Use the agreed branch if development moves to reviewed feature branches. The LFS pre-push hook installed by `git lfs install` uploads referenced binary objects. A failed Git or LFS upload is an incomplete handoff: resolve it and verify the destination can download the assets. After a successful upload, the dry run should report no outstanding objects for this branch. Keep a note of the commit hash to compare on the destination.

On the destination, start from a clean working copy with the same engine and compatible local tools installed. Close the editor before updating, then run:

```sh
git lfs install --local
git pull --ff-only
git lfs pull
git lfs fsck
git rev-parse HEAD
git status --short --branch
```

The commit hash must match the handoff commit before testing it. For a new machine, use the clone sequence above instead. Regenerate local project/IDE files as needed, compile locally, open the project with the pinned engine, and smoke-test the map and assets. Do not copy `Binaries`, shader caches, `Saved`, or IDE files between operating systems. Each engine installation creates its own local outputs.

## 7. Native packages and performance evidence

Build the Windows package on Windows and the Mac package on Mac from the **same commit or release tag**. Keep the source portable; platform configuration can live within the single Unreal project where necessary. Choose a package output location outside the source checkout, and distribute artifacts through releases or another artifact store rather than source history. Ignore rules include fallback package directories but do not replace checking staged scope. See [Epic's packaging guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/packaging-your-project).

Test each package outside the editor on its target OS. Check launch, input, menu/settings, map loading, resource production, construction, repeated recruitment of both troop types, selection, movement, combat, animation, audio, and exit. Validate on the Mac as soon as it is available, before building a large content library or depending on Windows-only plugins.

Record the commit, exact engine/toolchain, hardware and OS, resolution, quality preset, troop counts, map/scenario, and measured frame times/FPS. Target smooth 60 FPS, with a troop-count budget established through measurement on the actual hardware. Lighting and effects should retain the agreed atmosphere while keeping troops, commands, and construction previews readable. Record Windows and Mac results separately; do not promise equivalent performance from shared source alone.
