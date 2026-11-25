"""pickup — "where was I?" for all your repos in one command.

Scans local git repos and prints one resume line each:
branch, last commit, uncommitted changes, unpushed commits, open PRs.

Zero dependencies. Python 3.11+ (uses stdlib tomllib).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore

__version__ = "0.1.0"

# Release codenames: Jharkhand, one city per minor release.
# Patch releases keep their minor release's city; major releases
# get a landmark. See VERSIONING.md.
RELEASE_CODENAMES: dict[tuple[int, int], str] = {
    (0, 1): "Ranchi",
    (0, 2): "Jamshedpur",
    (0, 3): "Dhanbad",
    (0, 4): "Bokaro",
    (0, 5): "Hazaribagh",
    (0, 6): "Deoghar",
    (0, 7): "Dumka",
    (0, 8): "Giridih",
    (0, 9): "Chaibasa",
    (1, 0): "Netarhat",
}


def codename_for(version: str) -> str:
    """Codename for a version string like '0.1.0' ('' if unassigned)."""
    try:
        major, minor, *_ = (int(p) for p in version.split("."))
    except ValueError:
        return ""
    return RELEASE_CODENAMES.get((major, minor), "")


CODENAME = codename_for(__version__)

GIT_TIMEOUT = 10
GH_TIMEOUT = 10


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class RepoState:
    name: str
    path: str
    branch: str = "-"
    last_commit_ts: int = 0
    last_commit_msg: str = ""
    last_commit_rel: str = "-"
    dirty: int = 0          # modified/staged/deleted (tracked)
    untracked: int = 0
    unpushed: int | None = None   # None = no upstream / unknown
    stashes: int = 0
    open_prs: int | None = None   # None = not checked / unavailable
    draft_prs: int = 0
    error: str = ""

    @property
    def needs_attention(self) -> bool:
        return bool(self.dirty or self.untracked or self.unpushed or self.draft_prs)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _run(cmd: list[str], cwd: str | None = None, timeout: int = GIT_TIMEOUT) -> str | None:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def rel_time(ts: int, now: int | None = None) -> str:
    if not ts:
        return "-"
    now = now or int(time.time())
    d = max(0, now - ts)
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{d // 60}m ago"
    if d < 86400:
        return f"{d // 3600}h ago"
    if d < 7 * 86400:
        return f"{d // 86400}d ago"
    if d < 30 * 86400:
        return f"{d // (7 * 86400)}w ago"
    if d < 365 * 86400:
        return f"{d // (30 * 86400)}mo ago"
    return f"{d // (365 * 86400)}y ago"


def _is_repo(p: Path) -> bool:
    return (p / ".git").exists()


# --------------------------------------------------------------------------
# Discovery & config
# --------------------------------------------------------------------------

def load_config() -> dict:
    """Config lookup: $PICKUP_CONFIG, ~/.config/pickup/config.toml, ./.pickup.toml"""
    candidates: list[Path] = []
    if os.environ.get("PICKUP_CONFIG"):
        candidates.append(Path(os.environ["PICKUP_CONFIG"]).expanduser())
    candidates.append(Path.home() / ".config" / "pickup" / "config.toml")
    candidates.append(Path.cwd() / ".pickup.toml")
    for c in candidates:
        if c.is_file() and tomllib is not None:
            try:
                with open(c, "rb") as f:
                    return tomllib.load(f)
            except Exception:
                continue
    return {}


def discover_repos(roots: list[Path], explicit: list[Path], ignore: set[str], max_depth: int = 2) -> list[Path]:
    found: dict[str, Path] = {}

    for p in explicit:
        p = p.expanduser().resolve()
        if _is_repo(p):
            found[str(p)] = p

    for root in roots:
        root = root.expanduser()
        if not root.is_dir():
            continue
        if _is_repo(root):
            found[str(root.resolve())] = root.resolve()
            continue
        # walk up to max_depth looking for .git
        for dirpath, dirnames, _ in os.walk(root):
            depth = len(Path(dirpath).relative_to(root).parts)
            if depth >= max_depth:
                dirnames[:] = []
            # prune noise + the repos themselves (don't descend into a repo)
            dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "__pycache__"}]
            p = Path(dirpath)
            if p.name in ignore:
                dirnames[:] = []
                continue
            if _is_repo(p):
                found[str(p.resolve())] = p.resolve()
                dirnames[:] = []  # nested repos inside a repo are rare; skip

    return sorted((p for p in found.values() if p.name not in ignore), key=lambda p: p.name.lower())


# --------------------------------------------------------------------------
# Per-repo scan
# --------------------------------------------------------------------------

def scan_repo(path: Path) -> RepoState:
    st = RepoState(name=path.name, path=str(path))
    cwd = str(path)

    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch is None:
        st.error = "not a git repo?"
        return st
    if branch == "HEAD":
        sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd) or ""
        st.branch = f"(detached {sha})"
    else:
        st.branch = branch

    log = _run(["git", "log", "-1", "--format=%ct%x1f%s"], cwd)
    if log:
        ts, _, msg = log.partition("\x1f")
        try:
            st.last_commit_ts = int(ts)
        except ValueError:
            st.last_commit_ts = 0
        st.last_commit_msg = msg.strip()
        st.last_commit_rel = rel_time(st.last_commit_ts)

    status = _run(["git", "status", "--porcelain"], cwd)
    if status is not None and status != "":
        for line in status.splitlines():
            if line.startswith("??"):
                st.untracked += 1
            elif line.strip():
                st.dirty += 1

    # unpushed: commits on HEAD not on its upstream
    upstream = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd)
    if upstream:
        count = _run(["git", "rev-list", "--count", "@{u}..HEAD"], cwd)
        if count is not None:
            try:
                st.unpushed = int(count)
            except ValueError:
                st.unpushed = None

    stash = _run(["git", "stash", "list"], cwd)
    if stash:
        st.stashes = len(stash.splitlines())

    return st


_GH_REMOTE_RE = re.compile(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$")


def fetch_prs(path: Path) -> tuple[int, int] | None:
    """Return (open_prs, draft_prs) authored by the current gh user, or None."""
    url = _run(["git", "remote", "get-url", "origin"], str(path))
    if not url:
        return None
    m = _GH_REMOTE_RE.search(url.strip())
    if not m:
        return None
    repo = f"{m.group(1)}/{m.group(2)}"
    out = _run(
        ["gh", "pr", "list", "--repo", repo, "--author", "@me", "--state", "open",
         "--json", "isDraft", "--limit", "50"],
        timeout=GH_TIMEOUT,
    )
    if out is None:
        return None
    try:
        prs = json.loads(out)
    except json.JSONDecodeError:
        return None
    drafts = sum(1 for p in prs if p.get("isDraft"))
    return (len(prs), drafts)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _changes_cell(st: RepoState) -> str:
    parts = []
    if st.dirty:
        parts.append(f"{st.dirty} changed")
    if st.untracked:
        parts.append(f"{st.untracked} untracked")
    if st.unpushed:
        parts.append(f"{st.unpushed} unpushed")
    if st.stashes:
        parts.append(f"{st.stashes} stash" + ("es" if st.stashes > 1 else ""))
    return ", ".join(parts) if parts else "clean"


def _prs_cell(st: RepoState) -> str:
    if st.open_prs is None:
        return "-"
    if st.open_prs == 0:
        return "none"
    if st.draft_prs:
        return f"{st.open_prs} open ({st.draft_prs} draft)"
    return f"{st.open_prs} open"


def render_table(states: list[RepoState]) -> str:
    if not states:
        return "No git repos found. Point pickup at a folder:  pickup ~/code"
    headers = ["REPO", "BRANCH", "LAST COMMIT", "CHANGES", "PRS"]
    rows = []
    for st in states:
        if st.error:
            rows.append([st.name, "!", st.error, "", ""])
            continue
        commit = f"{st.last_commit_rel} · {st.last_commit_msg}" if st.last_commit_msg else "-"
        if len(commit) > 52:
            commit = commit[:49] + "..."
        rows.append([st.name, st.branch, commit, _changes_cell(st), _prs_cell(st)])

    widths = [max(len(headers[i]), *(len(r[i]) for r in rows)) for i in range(len(headers))]
    def fmt(cells: list[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells)).rstrip()

    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines += [fmt(r) for r in rows]

    dirty_repos = sum(1 for s in states if s.needs_attention)
    lines.append("")
    lines.append(f"{len(states)} repos · {dirty_repos} with work in progress")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pickup",
        description='pickup — "where was I?" for all your repos in one command.',
    )
    p.add_argument("paths", nargs="*", help="repo folders or parent folders to scan (default: config roots, else current folder)")
    p.add_argument("--no-prs", action="store_true", help="skip GitHub PR checks (faster, offline)")
    p.add_argument("--depth", type=int, default=2, help="how deep to search parent folders for repos (default 2)")
    p.add_argument("--json", action="store_true", help="output JSON instead of a table")
    p.add_argument("--dirty", action="store_true", help="only show repos with work in progress")
    version_str = f"pickup {__version__}" + (f' "{CODENAME}"' if CODENAME else "")
    p.add_argument("--version", action="version", version=version_str)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()

    explicit: list[Path] = []
    roots: list[Path] = []
    if args.paths:
        for raw in args.paths:
            p = Path(raw)
            (explicit if _is_repo(p) else roots).append(p)
    else:
        for raw in cfg.get("repos", []):
            explicit.append(Path(raw))
        for raw in cfg.get("roots", []):
            roots.append(Path(raw))
        if not explicit and not roots:
            roots = [Path.cwd()]

    ignore = set(cfg.get("ignore", []))
    repo_paths = discover_repos(roots, explicit, ignore, max_depth=args.depth)
    states = [scan_repo(p) for p in repo_paths]

    if not args.no_prs and states:
        ok = [s for s in states if not s.error]
        with ThreadPoolExecutor(max_workers=8) as ex:
            for st, result in zip(ok, ex.map(lambda s: fetch_prs(Path(s.path)), ok)):
                if result is not None:
                    st.open_prs, st.draft_prs = result

    # most recently active first — that's the "where was I" order
    states.sort(key=lambda s: s.last_commit_ts, reverse=True)
    if args.dirty:
        states = [s for s in states if s.needs_attention]

    if args.json:
        print(json.dumps([asdict(s) for s in states], indent=2))
    else:
        print(render_table(states))
    return 0


if __name__ == "__main__":
    sys.exit(main())
