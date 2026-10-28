# Releasing

How to cut a release, link to it, and take one back. The machinery is
[`.github/workflows/release.yml`](../.github/workflows/release.yml); this is the
routine around it.

## Cut a release

1. **Bump the version** in [`fingerino/__init__.py`](../fingerino/__init__.py),
   e.g. `__version__ = "0.1.1"`. It is the only place the version lives.
2. **Merge that to `main`** through a PR like any other change.
3. **Tag the merge commit and push the tag:**

   ```powershell
   git switch main
   git pull
   git tag v0.1.1
   git push origin v0.1.1
   ```

The tag starts the workflow. About 10 minutes later the release is at
<https://github.com/cky-gitHub/fingerino/releases>.

If the tag and `__version__` disagree, the first step of every build job fails
with a message saying so, and nothing is published. Fix it by deleting the tag
(see below), bumping the version, and tagging again.

### Test a build without releasing

Actions → **Release** → **Run workflow** → pick a branch. It builds and selftests
everything and puts the files under **Artifacts** on the run page, but the
publish job only runs for tags, so nothing goes public.

## What a release contains

| File | For |
| --- | --- |
| `Fingerino-<ver>-windows-x64-Setup.exe` | Windows installer |
| `Fingerino-<ver>-windows-x64.zip` | Windows, portable — unzip and run |
| `Fingerino-<ver>-macos-arm64.dmg` | Apple Silicon Mac |
| `Fingerino-windows-x64-Setup.exe`, `Fingerino-windows-x64.zip`, `Fingerino-macos-arm64.dmg` | The same files again without the version, for stable links |

The release notes include SHA-256 digests of each file.

## Linking from a website

These always point at the newest release, so they never need updating:

```
https://github.com/cky-gitHub/fingerino/releases/latest/download/Fingerino-windows-x64-Setup.exe
https://github.com/cky-gitHub/fingerino/releases/latest/download/Fingerino-macos-arm64.dmg
https://github.com/cky-gitHub/fingerino/releases/latest
```

The first two start the download directly; the third opens the release page
with the notes, checksums and every file. The direct links only exist from the
first release cut after `release.yml` gained the stable-named copies.

Pre-releases and drafts are skipped by `/latest`. A tag like `v0.2.0-beta` is
still published as a normal release by this workflow, so it would become
"latest" — only tag what you want strangers to get.

## Undo a release

1. **Delete the release** on GitHub: Releases → the release → **Delete** (trash
   icon, top right). This removes the page and its files.
2. **Delete the tag**, on GitHub and locally:

   ```powershell
   git push origin --delete v0.1.1
   git tag -d v0.1.1
   ```

`/releases/latest` falls back to the previous release as soon as step 1 is
done, so website links keep working.

Anyone who already downloaded the bad build keeps it. Prefer fixing forward
with a new version (`v0.1.2`) over reusing a number: two different files that
both claim to be 0.1.1 make bug reports ambiguous.

To fix just the notes or a file without retracting anything, use **Edit** on the
release page instead.
