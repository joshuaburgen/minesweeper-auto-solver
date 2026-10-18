# Publishing notes

The public README is ready for review. These notes describe concrete issues observed in this checkout; they are not a claim that the repository has already been cleaned or published.

## Tracked environment and runtime files

At the documentation review, Git tracked **3,340 files under `.venv/`**, as well as local screenshots, calibration data, Arbiter configuration, and debug output. Adding `.gitignore` does not untrack files already in Git.

Inspect the proposed removal from version control before committing. The following commands remove local artifacts from the **Git index only** and preserve working files:

```powershell
git rm -r --cached --ignore-unmatch -- .venv arbiter_diagnostic
git rm --cached --ignore-unmatch -- arbiter_calibration.json web_result.png diagnostics
git rm --cached --ignore-unmatch -- arbiter/arbiter.dat arbiter/diagnostics arbiter/_debug_protocol_last.txt arbiter/textstats.csv arbiter/INDEX.GID
git rm --cached --ignore-unmatch -- chromedriver
git diff --cached --stat
```

The legacy `chromedriver` is not used automatically by the current implementation. New replays and statistics are excluded by `.gitignore`. Existing commits will still contain previously tracked files; these commands do not rewrite history.

The documentation update has not run these index-changing commands, committed changes, or pushed anything.

## Attribution and licensing

The source history and demo originate from [h0rban/minesweeper-online-solver](https://github.com/h0rban/minesweeper-online-solver). Keep that attribution. [MIT](../LICENSE) now covers Joshua Gax Burgen's original contributions. It does not relicense upstream material. Applicable upstream permission remains unresolved, so do not present the entire combined repository as cleared for MIT redistribution. See [third-party notices](../THIRD_PARTY_NOTICES.md).

Arbiter and ChromeDriver are third-party binaries. Establish their redistribution terms before publishing them as part of a release. An external Arbiter installation works with the solver; the executable does not need to live in the repository.

## GitHub presentation

Suggested repository description:

> Python Minesweeper solver for Chrome and Windows Arbiter, with fast input, smooth per-click pacing, and bounded retries.

Suggested topics:

`minesweeper` `minesweeper-solver` `python` `selenium` `automation` `computer-vision` `windows`

Use `README.md` as the English landing page and `README.zh-CN.md` for Chinese readers. The existing GIF is an attributed upstream demonstration. A new short recording of the current version would show the paced and desktop features more accurately; label its mode, command, and whether it is real time.

## Verify before a release

```powershell
.\.venv\Scripts\python.exe Runner.py --help
.\.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py" -v
git diff --check -- README.md README.zh-CN.md .gitignore docs/PUBLISHING.md
```

Do not publish the old single-run speed observations as a general performance guarantee. A reproducible benchmark should include versions, hardware, mode, command, number of games, win rate, and the definition of the measured duration. The current documentation distinguishes prior live observations from automated tests and unverified behavior.
