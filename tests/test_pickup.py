import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pickup.cli import codename_for, discover_repos, rel_time, scan_repo, render_table, main


def test_codenames():
    assert codename_for("0.1.0") == "Ranchi"
    assert codename_for("0.1.3") == "Ranchi"  # patches keep the city
    assert codename_for("0.2.0") == "Jamshedpur"
    assert codename_for("1.0.0") == "Netarhat"
    assert codename_for("9.9.9") == ""
    assert codename_for("junk") == ""


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.email=t@t.t", "-c", "user.name=t", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(base: Path, name: str, dirty=False, untracked=False) -> Path:
    repo = base / name
    repo.mkdir()
    git(repo, "init", "-b", "main")
    (repo / "a.txt").write_text("hello\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "initial commit")
    if dirty:
        (repo / "a.txt").write_text("changed\n")
    if untracked:
        (repo / "new.txt").write_text("new\n")
    return repo


def test_rel_time():
    now = int(time.time())
    assert rel_time(now, now) == "just now"
    assert rel_time(now - 300, now) == "5m ago"
    assert rel_time(now - 7200, now) == "2h ago"
    assert rel_time(now - 3 * 86400, now) == "3d ago"
    assert rel_time(0, now) == "-"


def test_scan_clean_repo(tmp_path):
    repo = make_repo(tmp_path, "clean-one")
    st = scan_repo(repo)
    assert st.branch == "main"
    assert st.last_commit_msg == "initial commit"
    assert st.dirty == 0 and st.untracked == 0
    assert st.unpushed is None  # no upstream configured
    assert st.error == ""


def test_scan_dirty_repo(tmp_path):
    repo = make_repo(tmp_path, "wip-one", dirty=True, untracked=True)
    st = scan_repo(repo)
    assert st.dirty == 1
    assert st.untracked == 1
    assert st.needs_attention


def test_scan_unpushed(tmp_path):
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "--bare", str(make_repo(tmp_path, "seed")), str(bare))
    work = tmp_path / "work"
    git(tmp_path, "clone", str(bare), str(work))
    (work / "b.txt").write_text("x\n")
    git(work, "add", ".")
    git(work, "commit", "-m", "unpushed work")
    st = scan_repo(work)
    assert st.unpushed == 1


def test_discover_finds_nested_repos(tmp_path):
    make_repo(tmp_path, "one")
    sub = tmp_path / "group"
    sub.mkdir()
    make_repo(sub, "two")
    found = discover_repos([tmp_path], [], set(), max_depth=2)
    assert {p.name for p in found} == {"one", "two"}


def test_render_table(tmp_path):
    repo = make_repo(tmp_path, "demo", dirty=True)
    out = render_table([scan_repo(repo)])
    assert "demo" in out and "main" in out and "1 changed" in out
    assert "repos" in out


def test_main_json_no_prs(tmp_path, capsys):
    make_repo(tmp_path, "json-one")
    rc = main(["--no-prs", "--json", str(tmp_path)])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert data[0]["name"] == "json-one"
    assert data[0]["branch"] == "main"


def test_main_dirty_filter(tmp_path, capsys):
    make_repo(tmp_path, "clean-a")
    make_repo(tmp_path, "dirty-b", dirty=True)
    main(["--no-prs", "--dirty", str(tmp_path)])
    out = capsys.readouterr().out
    assert "dirty-b" in out and "clean-a" not in out
