# ADR 0010: A run that checked nothing is not a pass

- **Date:** 2026-10-30
- **Status:** accepted
- **Refines:** [ADR 0009](0009-an-unread-file-makes-the-run-incomplete.md)

## Context
The second outside trial — a session on the Pixel Galaxy Studio project, asked to work from the README alone and [write down what happened](../feedback/2026-10-30-claude-code-windows-readme-cold-trial.md) — found no P0s. The honesty work in ADR 0009 held: a truncated `package.json` exited 2, a UTF-16 `requirements.txt` was read, an unknown config key was refused. Then it built a fixture that nobody had thought to build:

```
$ stocktake --root w04-only-unread-manifests; echo $?
Dependency check 2026-10-30: 0 checked, 0 vulnerable, ...
UNREAD (StockTake has no reader for these yet, so nothing in them was checked)
  go.mod
  pnpm-lock.yaml
0
```

A Go project. Both of its dependency files are kinds StockTake has no reader for, so it checked nothing and exited 0. The README's own definition of exit 0 is "nothing unsafe, and the whole project was checked", which is false here, and the report named the consequence exactly: for a CI gate on a Go or pnpm project this is a permanently green step over a project nobody has looked at.

ADR 0009 drew the line between **unread** (a kind nothing supports yet — a known, bounded gap, named in the report, exit 0) and **unreadable** (a reader claimed the file and failed, so what was missed is unbounded, exit 2). That line is still right, and it is not what this is about. This is about a third thing neither category anticipated: the case where the bounded gap turns out to be the whole project.

The report's own framing of the fix is the one worth keeping: "the README's own rationale for exit 2 (*nothing is claimed either way*) applies unchanged".

## Options considered

**A. Leave it at 0 and fix the README's wording instead.** Honest, and cheap, and wrong. The sentence is not the problem; a green gate over an unchecked project is. Weakening the definition of 0 to match the behaviour would give up the thing that makes 0 worth anything.

**B. Make any unread manifest make the run incomplete.** Simple and consistent — part of the project went unchecked, so exit 2 — and intolerable in practice. Every polyglot repository with a `go.mod` beside its Python would exit 2 forever, and the response would be to list everything in `accept_unread` without reading it, which converts a considered escape hatch into a reflex. It also throws away a true and useful report: two hundred Python pins checked is worth having.

**C. Exit 2 only when nothing at all was checked and at least one manifest went unread.** Zero coverage is a different claim from partial coverage. "I checked 200 of 201 things" is a report with a named gap; "I checked 0 of 1" is not a report. The existing `accept_unread` is exactly the statement a Go project needs to make — "this is all you will find here, I know" — and listing a file there already moves it out of `unread_manifests`, so the escape hatch works with no new configuration.

**D. A `--fail-on unread` flag.** Already deferred once, for the reason recorded in the roadmap: it is a second strictness axis, and the question is whether the *default* is honest, not whether a flag can be bolted on. A flag here would leave the default dishonest.

## Decision
Option C. `Report.nothing_was_checked` is true when there are no findings and `unread_manifests` is non-empty, and `Report.complete` takes it into account alongside `offline` and `unreadable`, so every format and the exit code get it without a second rule being written anywhere.

- The command exits **2**, and says what it means: *"StockTake checked nothing in this project. The only 2 dependency files it found (go.mod, pnpm-lock.yaml) are of a kind it has no reader for yet, so this run says nothing about the project either way."*
- The message names the escape hatch, because an exit code that cannot be satisfied is an exit code people route around.
- `accept_unread` restores exit 0, and it reads as the right sentence: the project has stated that these are the files, and that it knows they are not checked.
- An **empty** project — no dependency files at all — still exits 0. There is nothing to point at, and a project with genuinely no dependencies is a project with nothing unsafe in it. The report asked for `checked == 0 and unread non-empty` specifically, and that is the condition implemented; the existing "if that is a surprise, look at the excludes" line covers the rest.
- A project whose only manifest it `exclude`s also still exits 0. Excluding a file is a deliberate statement about that file, unlike having no reader for it.

## Consequences
- **Good.** The README's definition of exit 0 is true again, which is the point. A Go or pnpm project gets told StockTake cannot check it instead of being handed a green tick.
- **Good.** It gives `accept_unread` a job it did not quite have before. It existed to stop the nagging; now it is also the one way to say "checked nothing, and that is expected", which is a sentence worth having to write down.
- **Good.** No new rule and no new flag: one derived property, and `complete` already fans out to the text headline, the summary line, the JSON field, SARIF's `executionSuccessful` and the exit code.
- **Cost.** A behaviour change on top of ADR 0009's, in the same release, for a narrow case. Anyone who had pointed StockTake at a project it has no readers for was getting a meaningless 0 and is now getting a 2 — which is the correction, but it will look like a regression to whoever meets it first. The message carries the reason and the fix, which is the most that can be done about that.
- **Cost.** The boundary is a judgement, not a principle: 0 of 1 fails and 200 of 201 passes, and nothing says where between those it should turn over. Zero is the only defensible place to draw it without a new flag, because zero is the only count about which there is no report at all — but a project at 1 of 201 is in much the same position and will pass.
- **Cost.** `nothing_was_checked` reads oddly beside a report that also says `0 checked`; two names for one fact. The property is on `Report` rather than in `check.py` because it is derivable from the report alone, which keeps every format consistent for free, but it does put a rule-shaped thing in the vocabulary module.
