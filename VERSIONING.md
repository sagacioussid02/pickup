# Versioning

`pickup` uses strict [semantic versioning](https://semver.org) for the
numbers — tooling (pip, package indexes) depends on them — and a
**Jharkhand city codename** for humans.

## The rules

- **Patch** (`0.1.0` → `0.1.1`) — bug fixes only. Keeps the same city.
- **Minor** (`0.1.x` → `0.2.0`) — new features. Gets the **next city**.
- **Major** (`0.x` → `1.0.0`) — breaking changes. Gets a **landmark**
  instead of a city.

## The tour

Releases travel across Jharkhand, starting from the capital:

| Version | Codename   |
|---------|------------|
| 0.1.x   | Ranchi     |
| 0.2.x   | Jamshedpur |
| 0.3.x   | Dhanbad    |
| 0.4.x   | Bokaro     |
| 0.5.x   | Hazaribagh |
| 0.6.x   | Deoghar    |
| 0.7.x   | Dumka      |
| 0.8.x   | Giridih    |
| 0.9.x   | Chaibasa   |
| 1.0.x   | Netarhat (landmark) |

```bash
$ pickup --version
pickup 0.1.0 "Ranchi"
```

GitHub releases are titled with both: `0.2.0 — Jamshedpur`.
There are 24 districts on the map — plenty of road ahead.
