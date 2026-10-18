# License scope and third-party notices

## Original contributions in this fork

Joshua Gax Burgen's original contributions to this fork are offered under the
[MIT License](LICENSE), copyright 2026 Joshua Gax Burgen. This grant covers only
rights held by that contributor. It does not relicense pre-existing upstream
material, third-party executables, or dependencies.

## Upstream solver and demonstration

This repository derives from [h0rban/minesweeper-online-solver](https://github.com/h0rban/minesweeper-online-solver)
by Jake Horban. Pre-existing solver code remains present, including within
files modified in this fork. `solver_example.gif` comes from that upstream
project. Attribution is retained in both READMEs and in Git history.

An applicable upstream license or explicit relicensing permission has not
been established in this checkout. Do not describe the entire combined
repository as cleared for MIT redistribution until that is resolved with the
relevant rights holder. The MIT grant for new contributions does not resolve
the upstream licensing status.

GitHub's [repository licensing documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
explains the distinction between publicly accessible code and a license to
reuse it.

## Third-party software

| Component | Scope |
| --- | --- |
| `arbiter/` | Minesweeper Arbiter executable, help, language and related distribution files. Original ownership and applicable terms remain with their rights holders; not relicensed by this fork. |
| `chromedriver` | Legacy third-party driver binary; unused by the default runner and not covered by this fork's MIT grant. |
| Python dependencies | Distributed under their own licenses. Refer to each installed package's license and notices. |

Review applicable distribution terms before including third-party binaries in
a public release. Arbiter can be installed separately; Selenium Manager
locates the browser driver, so these binaries need not be bundled.
