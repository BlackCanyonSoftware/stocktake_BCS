# ADR 0008: A tag its publisher moves is a range, not a version

- **Date:** 2026-10-30
- **Status:** accepted

## Context
The workflows reader was finished, pointed at this repository's own CI file, and immediately reported:

```
2 dependencies have a newer release: actions/checkout 7->7.0.1, actions/setup-python 7->7.1.0
```

Both were wrong in the only way that matters: there was nothing for anybody to do. `uses: actions/checkout@v7` does not mean "version 7.0.0". GitHub advances the `v7` tag to each new v7 release, so a workflow pinned to `@v7` is *already running* 7.0.1 and will pick up 7.0.2 by itself. Reporting it as outdated is reporting an update that has happened.

This is the failure mode [ADR 0004](0004-only-unsafe-findings-fail-the-build.md) exists to prevent, in its most insidious form. It would not have failed anybody's build — `outdated` only warns — but it would have put two permanent, unfixable lines in the warning summary of every run. A warning that cannot be acted on teaches people to ignore the warning summary, and then the real findings go with it.

The same shape appears elsewhere. A Docker `FROM python:3.12` tag moves to each new 3.12.x. An npm `^1.2.3` moves within the 1.x line. The difference is that npm's version of this *looks* like a range and is already handled as one; GitHub's looks exactly like a pinned version and is not.

## Options considered

**A. Compare only to the precision the ref actually names.** `@v7` names one number, so only a change in that number is an update: `v7` → `v8` is, `v7` → `7.0.1` is not. `@v7.1` compares two numbers. `@v7.1.0` names all three and is compared in full, like any pin.

**B. Treat a major-only tag as unpinned.** Honest about reproducibility — `@v7` really does not fix what runs — and it is what the tool already does for a `pyproject.toml` range. But it throws away the finding that matters most: `actions/checkout@v4` is three major versions behind, and that *is* work somebody has to do. Verification found exactly that case in the author's brand-kit repository.

**C. Resolve the tag to the release it currently points at**, with a second request per action. Precise, and makes `@v7` a pin at whatever 7.x it resolves to today. Rejected: it doubles the requests to a service with a 60-an-hour anonymous limit, and it answers the wrong question. The project did not pin 7.0.1; it asked for "the v7 line", and that is what should be judged.

**D. Say nothing about moving tags at all.** No false positives and no findings. The one option guaranteed not to help.

## Decision
Option A, as a property of the dependency rather than of the ecosystem.

`Dep.moving` says the version in hand is a tag its publisher advances. `is_newer(..., moving=True)` then compares only to the precision written down:

```python
if moving:
    depth = len(release_tuple(current))
    return bool(depth) and release_tuple(latest)[:depth] > release_tuple(current)[:depth]
```

The workflows reader sets it for `@v7` and `@v7.1`, and not for `@v7.1.0` — a full version tag is one nobody moves by convention. The flag collapses to an ordinary comparison once all three numbers are named, which is what makes it safe to set from a reader that cannot always be sure.

It is a field on `Dep` rather than a per-ecosystem rule because it is a property of how *this* dependency was written, not of the ecosystem it belongs to: two lines in the same workflow, `@v7` and `@v7.1.0`, need different treatment. The containers reader will set the same flag for a `FROM python:3.12` tag, so this is the second use of the idea rather than a speculative generalisation.

## Consequences
- **Good.** `@v7` on the newest v7 is reported as current, which is the truth. This repository's own warning summary went from two permanent unfixable lines to none.
- **Good.** A real major gap is still reported, and loudly. The brand-kit repository's `actions/checkout@v4` → `7.0.1 (major)` and `actions/setup-python@v5` → `7.1.0 (major)` are three majors behind and genuinely want doing.
- **Good.** It matches what a reader of the file would expect, and what Dependabot does with the same line.
- **Cost.** The reproducibility problem goes unreported: `@v7` is a moving target, and a compromised tag is a real supply-chain risk that SHA pinning exists to address. StockTake now says nothing about it. That is a deliberate omission rather than an oversight, and the right home for it is a separate "pinned too loosely" finding that a project can opt into — noted in the roadmap rather than bolted onto this.
- **Cost.** `moving` is a third field on `Dep` that only some readers set, and a reader that forgets to set it produces exactly the false positive this record is about. The workflows reader has a test asserting which refs are marked and which are not.
- **Cost.** The precision rule is a heuristic about publisher behaviour, not a guarantee. A publisher who moves a full `v7.1.0` tag, or who never moves `v7`, would be judged wrongly. Both are rare enough, and against convention, that following the convention is the better default.
