# ADR 0009: A file StockTake could not read makes the whole run incomplete

- **Date:** 2026-10-30
- **Status:** accepted

## Context
Another project of the author's — [Can-AI](../feedback/2026-10-30-claude-code-session.md) — put StockTake through a deliberate trial: ground truth written down before the run, ~30 purpose-built fixture projects, both platforms, a logging proxy to check what actually left the machine. It found no false positives anywhere, and exact agreement with OSV and `npm audit` on every project it could read. Then it found this:

```
$ stocktake --root e08c-bad-packagejson --format summary
stocktake: nothing found to check
$ echo $?
0
```

The project's `package.json` was truncated mid-object. The reader called `json.loads`, caught `ValueError`, and returned. Nothing in the report said a file had been skipped, and the exit code said everything was fine.

It was not one bug but one shape of bug, in three places:

- **A truncated or malformed manifest.** Every structured reader — `package.json`, `package-lock.json`, `pyproject.toml`, `Pipfile`, the TOML locks — caught its parse error and returned nothing, each with a comment to the effect that a damaged file is the project's own problem to notice.
- **A manifest that is not UTF-8.** `scan` read every file with `errors="replace"`, which never fails. A `requirements.txt` saved as UTF-16 — what PowerShell's `>` writes, so a common accident — came back as a NUL between every character, matched no requirement, and was reported as a project with no dependencies. The file was perfectly good; the reading was wrong.
- **A manifest that is not text at all.** The same path turned a JPEG named `requirements.txt` into replacement characters and read nothing from it.

The trial's verdict was that StockTake "is not yet safe to rely on unattended", and this was the first reason given. It is the right verdict. [ADR 0004](0004-only-unsafe-findings-fail-the-build.md) is built on the premise that a passing run means something; the whole argument for *not* failing on an outdated release is that the failures StockTake does report are worth acting on. A run that silently skipped half the project and exited 0 takes that premise away.

Worth naming precisely: this is not the same as an **unread** manifest. `go.mod` is unread — no reader exists for that ecosystem yet — and that is a known, bounded gap which the report has always named and which exits 0. Unreadable is different. A reader claimed the file, said it understood this kind, and then failed. What is in it is unknown, and nothing bounds what was missed.

## Options considered

**A. Report it as a finding.** Cheap, and wrong in kind. Findings are statements about dependencies; this is a statement about the run. It would also land in `counts` and in `--only vulnerable`, where a narrowed report could hide it.

**B. Warn.** What an unread manifest effectively does today. For a file a reader claimed, a warning is how this became invisible in the first place: warnings in CI logs and pytest summaries are skimmed, and the exit code — the one thing automation reads — would still say 0.

**C. Fail the build, as `exit 1`.** Overstates it. `1` means "I checked and found something unsafe", and a consumer that treats 1 as "there is a vulnerability" would be told a lie. It also collides with ADR 0004, which reserves failure for unsafe findings.

**D. Exit 2, the code that already means "the check could not be completed".** That code exists for an unreachable registry, which is the same statement about a different cause: part of the project went unchecked, so do not read a verdict into this run. An unreadable manifest is that statement exactly.

## Decision
Option D, with completeness made explicit rather than left implicit in the exit code.

- `Report.unreadable` carries `(path, reason)` for every manifest a reader claimed and failed on. `UnreadableManifest` is raised by the reader, not swallowed, and `scan` collects it.
- `Report.complete` is `offline is None and not unreadable` — one property for both ways a run can fail to cover the project, because to anyone consuming the result they are the same fact.
- The command exits **2** when a run is incomplete, **and it does so even when it also found something unsafe**. Incomplete outranks unsafe: the findings of a partial run are a floor, not an answer. They are still printed in full.
- `read_manifest` decodes by byte-order mark, so a UTF-16 or UTF-32 manifest is read properly rather than refused. Undecodable bytes, and text holding NUL (UTF-16 saved without a mark), are unreadable.
- Every output says so: the text headline and an `UNREADABLE` section, the JSON `complete` field, SARIF's `executionSuccessful: false` plus an `unreadable` error-level rule. `--only` narrows findings and **never** narrows this away — a part of the project that was never looked at is not something a filter may hide.
- The pytest item **fails** rather than skipping. A suite has no exit code to carry the distinction, so a skip would turn a project that is not being checked into a green run that mentions it in small print. This is not an exception to ADR 0004: ADR 0004 is about which *findings* fail, and this is the check not having happened.
- The one-line summary leads with it, and no longer says "nothing unsafe" about dependencies it never resolved. `nothing unsafe, 0 outdated (5 checked)` for five unpinned dependencies is now `nothing could be checked (0 of 5 checked, 5 unpinned)`.
- A project that has a file named like a manifest and knows it is not one `exclude`s it. Deliberately not `accept_unread`, which would hide it while still walking it: the right statement is "this is not one of my dependency files", not "I accept that you cannot read my dependency file".

## Consequences
- **Good.** The three trial fixtures that reported `nothing found to check` with exit 0 now report, respectively, the UTF-16 file's contents (it is readable after all), and exit 2 naming the file and the reason for the other two.
- **Good.** A clean run means something again, which is what the rest of the design rests on.
- **Good.** The reason is specific enough to act on: `package.json is not valid JSON (Expecting property name enclosed in double quotes: line 1 column 32)`.
- **Cost.** A project with a damaged manifest that was previously green now fails. That is the point, but it is a behaviour change for anyone already running StockTake, and it is why this is an ADR rather than a bug fix. `exclude` is the escape hatch, and the message names it.
- **Cost.** Any new structured reader must raise rather than return on a parse failure, and nothing enforces that automatically. A reader that forgets re-creates this exact bug for its own file type. The convention is in `AGENTS.md` under "Adding an ecosystem", beside the guard test for the same reason.
- **Cost.** Half-read files are reported twice over: the dependencies a reader managed to yield are kept *and* the file is named as unreadable. That is deliberate — both are true — but it means a count of findings and a count of files do not reconcile.
- **Cost.** The NUL check is a heuristic. A manifest format that legitimately contains NUL would be refused. None of the formats StockTake reads is binary, and `bun.lockb` — which is — has no reader and is reported as unread.
