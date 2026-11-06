# ADR 0013: A strict YAML subset, rather than a YAML dependency

- **Date:** 2026-11-05
- **Status:** accepted
- **Rests on:** [ADR 0001](0001-python-with-a-standard-library-only-core.md), [ADR 0005](0005-installed-package-plus-a-generated-single-file-copy.md), [ADR 0009](0009-an-unread-file-makes-the-run-incomplete.md)

## Context
Several kinds of dependency file are YAML: `.pre-commit-config.yaml`, `pnpm-lock.yaml`, yarn's berry lock files, and compose files. The roadmap has carried the question since M3 and stated the options as "a vendored minimal parser for the subset these files use, or accepting a dependency and amending [ADR 0001](0001-python-with-a-standard-library-only-core.md)", with one line ruling out a third: regex-scanning is "the *misses things silently* failure the guard tests exist to catch".

The owner asked for the decision to be made.

**The evidence.** Five `.pre-commit-config.yaml` files across the owner's repositories, each pinning three hook repositories. Between them they use: comments, including comments between a key and its value; block mappings; block sequences of mappings; plain scalars containing `/`, `|`, `(` and `#`; quoted scalars; flow sequences (`args: [--fix=lf]`); and — in one — a folded block scalar holding a shell command with quotes and a pipe in it. None uses an anchor, an alias, a tag, a merge key, more than one document, or a tab.

So the subset is real and bounded, and it is not as small as "key: value": a parser that refused block scalars would refuse a file that is perfectly valid and perfectly ordinary.

## Options considered

**A. Take a YAML dependency.** Correct parsing, no maintenance. Rejected, and the reason that settles it is not the one in the roadmap:

> **It would delete adoption route 3.** `stocktake vendor` writes the core as one self-contained file for a project that cannot take a dependency ([ADR 0005](0005-installed-package-plus-a-generated-single-file-copy.md)). The generator concatenates *this package's own modules*; it cannot inline a third-party package. A runtime dependency does not merely weaken the no-dependency promise, it removes a whole route by which StockTake is adopted, and that route exists for exactly the kind of project — a Node repository, a Dockerfile-only one — whose YAML we would be adding the dependency to read.

Beneath that: the promise is enforced by a test and is the project's most distinctive claim ("a tool whose job is watching your supply chain is a poor advertisement for itself if adopting it widens that supply chain"). And a YAML library is a pointed thing to depend on here — PyYAML's `load` was a remote-code-execution hazard for years, and while `safe_load` is the answer, a supply-chain checker parsing untrusted files from other people's repositories is the last place to want that class of footgun.

**B. A general vendored YAML parser.** All of YAML, written here. Rejected as a fantasy: YAML is large, and a 90%-complete implementation nobody audits is worse than either honest option.

**C. A strict subset that refuses what it does not implement.** Taken.

**D. Leave the files unread.** They stay on the UNREAD list, which [ADR 0010](0010-a-run-that-checked-nothing-is-not-a-pass.md) already makes honest. Tenable, and it leaves five real files and fifteen real pins unchecked in the owner's own repositories.

## Decision
Option C. `readers/yamlish.py` reads the subset above and **raises `UnreadableManifest` at the first construct it does not implement**: anchors, aliases, tags, merge keys, a second document, a tab used as indentation, or any structure it cannot finish.

**What makes this different from the thing the roadmap ruled out.** The objection was that a half-parser misses things silently, and that was exactly right when it was written, because there was nowhere for "I could not read this" to go — a reader that failed returned nothing, and nothing looked like an empty file. [ADR 0009](0009-an-unread-file-makes-the-run-incomplete.md) changed that: an unreadable manifest now makes the whole run incomplete and exits 2. A parser that stops at the edge of what it understands is therefore **loud**, not silent, and that is the entire basis on which a subset is defensible. This decision is not available without ADR 0009, and should be revisited if ADR 0009 ever is.

Two further rules keep it small enough to be worth trusting:

- **Structure is parsed; leaf values are kept as text.** A version is a string. Nothing needs to know that `[--fix=lf]` is a list or `'9.0'` a number, so flow collections and block scalars are captured as text rather than interpreted. Not parsing what nothing reads is most of the difference between this and a YAML library.
- **It is a shared grammar, not a reader.** It sits in `readers/` beside `pep508.py` and is listed with it in the guard's `NOT_READERS`, because it registers nothing and runs only when a reader calls it.

**Scope: pre-commit hooks only, for now.** `pnpm-lock.yaml`, yarn and compose files each need more evidence and arguably more of YAML, and yarn v1 is not YAML at all. They stay unread and are roadmap items.

## Consequences
- **Good.** Fifteen hook pins across five of the owner's repositories are checked, and the first run found every one of them behind — `ruff-pre-commit` as far back as 0.6.9 against 0.17.4, and `pre-commit-hooks` a major behind in all five.
- **Good.** It reuses rather than repeats: a pre-commit `rev` is a GitHub ref, so `github_ref` moved out of the workflows reader and both now share one implementation of the moving-tag and commit-SHA rules.
- **Good.** The no-dependency promise and the single-file copy both survive, and the copy carries the parser like any other core module.
- **Cost.** A valid config using an anchor is now *unreadable* and exits 2, where before it was merely unread and exited 0. That is a real regression for such a file, chosen deliberately: a loud refusal on a file we half-understand is the trade this whole approach is built on. None of the five real files is affected, and the message names the construct and the line.
- **Cost.** Maintenance, and a standing temptation. Every future "just add one more construct" is a step toward option B, which was rejected. The test file is written to make the refusals as prominent as the successes so that the boundary stays visible.
- **Cost.** Line numbers and comments come from a second pass over the raw lines, because the parser returns plain data with no positions. Two entries for one repository would both be pointed at the first.
- **Cost.** Only GitHub-hosted hooks are resolved. A hook on GitLab is passed over silently rather than reported as `unknown`, on the grounds that an `unknown` nobody can act on is noise — but it is a gap, and it is the kind this project normally insists on naming.
