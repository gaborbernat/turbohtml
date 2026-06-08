"""
Cut a turbohtml release: build the changelog, commit, tag, and push.

The tag push is what triggers the publish workflow, so this script stops once the
annotated tag is on the upstream ``main``. It mirrors the tox-dev release flow and
is invoked by the "Prepare Release" GitHub Actions workflow via ``tox -e release``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError, check_call, run

from git import Commit, Head, Remote, Repo, TagReference
from packaging.version import Version

_ROOT = Path(__file__).resolve().parents[1]
_UPSTREAM_SLUG = "tox-dev/turbohtml"


@dataclass
class ReleaseProgress:
    """Tracks how far a release got so a failure can be rolled back precisely."""

    original_main_sha: str
    main_pushed: bool = False
    tag_pushed: bool = False
    release_created: bool = False


def main(version_str: str) -> None:
    """Run the release for *version_str*, rolling back on any failure."""
    version = Version(version_str)
    repo = Repo(str(_ROOT))
    if repo.is_dirty():
        msg = "the repository is dirty; commit or stash changes before releasing"
        raise RuntimeError(msg)

    upstream, release_branch = create_release_branch(repo, version)
    progress = ReleaseProgress(original_main_sha=upstream.refs.main.commit.hexsha)
    try:
        perform_release(repo, upstream, release_branch, version, progress)
    except Exception:
        rollback(repo, upstream, release_branch, version, progress)
        raise


def create_release_branch(repo: Repo, version: Version) -> tuple[Remote, Head]:
    """Create and push a release-<version> branch off the upstream main."""
    upstream = next((remote for remote in repo.remotes if any(_UPSTREAM_SLUG in url for url in remote.urls)), None)
    if upstream is None:
        msg = f"could not find the {_UPSTREAM_SLUG} remote"
        raise RuntimeError(msg)
    upstream.fetch()
    branch = repo.create_head(f"release-{version}", upstream.refs.main, force=True)
    upstream.push(refspec=f"{branch}:{branch}", force=True)
    branch.checkout()
    return upstream, branch


def perform_release(
    repo: Repo, upstream: Remote, release_branch: Head, version: Version, progress: ReleaseProgress
) -> None:
    """Build the changelog, commit, tag, push, and open the GitHub release."""
    release_commit = build_changelog(repo, version)
    tag = tag_release(repo, release_commit, version)
    repo.git.push(upstream.name, f"{release_branch}:main", "-f")
    progress.main_pushed = True
    repo.git.push(upstream.name, tag, "-f")
    progress.tag_pushed = True
    create_github_release(version)
    progress.release_created = True
    repo.heads.main.checkout()
    repo.delete_head(release_branch, force=True)
    repo.git.push(upstream.name, f":{release_branch}", "--no-verify")
    upstream.fetch()
    repo.git.reset("--hard", f"{upstream.name}/main")


def build_changelog(repo: Repo, version: Version) -> Commit:
    """Consume the news fragments into the changelog and commit the result."""
    check_call(["towncrier", "build", "--yes", "--version", version.public], cwd=str(_ROOT))
    changelog = _ROOT / "docs" / "changelog.rst"
    # pre-commit reformats the freshly built changelog and exits non-zero; that reformat is the goal.
    run(["pre-commit", "run", "--files", str(changelog)], cwd=str(_ROOT), check=False)
    repo.index.add([str(changelog)])
    return repo.index.commit(f"release {version}")


def tag_release(repo: Repo, release_commit: Commit, version: Version) -> TagReference:
    """Create the annotated tag whose push triggers the publish workflow."""
    if str(version) in {tag.name for tag in repo.tags}:
        repo.delete_tag(str(version))
    return repo.create_tag(str(version), ref=release_commit, force=True)


def create_github_release(version: Version) -> None:
    """Open the GitHub release with auto-generated notes."""
    run(
        ["gh", "release", "create", str(version), "--title", f"v{version}", "--generate-notes"],
        cwd=str(_ROOT),
        check=True,
    )


def rollback(repo: Repo, upstream: Remote, release_branch: Head, version: Version, progress: ReleaseProgress) -> None:
    """Best-effort undo of whatever the release already published."""
    print(f"release failed; rolling back {version}")
    if progress.release_created:
        _best_effort(["gh", "release", "delete", str(version), "--yes"])
    if progress.tag_pushed:
        _best_effort_git(repo, upstream.name, f":refs/tags/{version}", "--no-verify")
    if progress.main_pushed:
        _best_effort_git(repo, upstream.name, f"{progress.original_main_sha}:main", "-f", "--no-verify")
    _best_effort_git(repo, upstream.name, f":{release_branch}", "--no-verify")


def _best_effort(command: list[str]) -> None:
    run(command, cwd=str(_ROOT), check=False)


def _best_effort_git(repo: Repo, *push_args: str) -> None:
    try:
        repo.git.push(*push_args)
    except CalledProcessError as error:
        print(f"rollback step failed: {error}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="release", description=__doc__)
    parser.add_argument("--version", required=True)
    main(parser.parse_args().version)
