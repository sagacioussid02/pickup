# pickup

**"Where was I?" — for all your repos, in one command.**

You context-switch between a bunch of repos. Monday morning (or after lunch)
you stare at a terminal wondering what you were in the middle of yesterday.
`pickup` answers that in seconds:

```
$ pickup ~/code

REPO       BRANCH        LAST COMMIT                  CHANGES              PRS
---------  ------------  ---------------------------  -------------------  --------------
sutra      feat/voice    2h ago · wire up wake word   3 changed, 1 stash   2 open (1 draft)
minions    main          5h ago · fix crew loop       1 unpushed           none
qxplore    quantum-track 1d ago · lesson 9: qft       clean                1 open
prelaunch  main          3d ago · stripe webhook      clean                none

4 repos · 2 with work in progress
```

Sorted by most recent activity first, because that's the order your brain
wants it in.

## What each line shows

- **Branch** — current branch (or detached HEAD)
- **Last commit** — how long ago + the commit subject
- **Changes** — modified files, untracked files, unpushed commits, stashes
- **PRs** — your open PRs on GitHub for that repo, drafts called out
  (needs the [`gh`](https://cli.github.com) CLI, signed in; skip with `--no-prs`)

## Install

```bash
pipx install pickup-cli     # or: pip install pickup-cli
# from source:
pip install .
```

Requires Python 3.11+ and `git`. No other dependencies.

## Usage

```bash
pickup                 # scan config roots, else the current folder
pickup ~/code          # scan a parent folder (finds repos up to 2 levels deep)
pickup ~/code/sutra    # a single repo works too
pickup --no-prs        # skip GitHub checks — fast and offline
pickup --dirty         # only repos with work in progress
pickup --json          # machine-readable output
```

## Config

Optional. Create `~/.config/pickup/config.toml`:

```toml
roots = ["~/code", "~/work"]        # parent folders to scan
repos = ["~/dotfiles"]              # individual repos outside the roots
ignore = ["old-fork", "scratch"]    # repo folder names to skip
```

`$PICKUP_CONFIG` or a `./.pickup.toml` in the current folder also work.

## Versioning

Numbers are strict semver; every minor release is also named for a city in
Jharkhand, touring the state starting from the capital — `0.1.0 "Ranchi"`,
then Jamshedpur, Dhanbad, Bokaro... Patch releases keep their city, major
releases get a landmark. Full scheme: [VERSIONING.md](VERSIONING.md).

## Why

Small, sharp, single-purpose — in the spirit of
[circumflex](https://github.com/bensadeh/circumflex) and
[gh-dash](https://github.com/dlvhdr/gh-dash). No TUI, no server, no config
required. One question, answered well.

## License

MIT
