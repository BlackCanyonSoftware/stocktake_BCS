# Outside feedback on StockTake

This folder holds written feedback from outside test sessions: people or AI
sessions that used StockTake the way a stranger who found it on the package
index would, then wrote down what happened.

- One file per session, named `YYYY-MM-DD-<session-or-source>.md`.
- Every file starts with the same header block (Source, Date, StockTake version
  / commit tested, Platforms, Ecosystems exercised, Verdict in one sentence).
- Every file then uses the same 13 sections, in the same order, so several
  reports can be read side by side:
  1 Summary, 2 Method, 3 Install and first run, 4 Results per feature,
  5 Accuracy, 6 Output formats and exit codes, 7 Performance, 8 Error handling,
  9 Documentation review, 10 Suggestions (P0/P1/P2), 11 Adopting StockTake in
  Can-AI, 12 Questions not answered, 13 Reproduction.
- `examples/` holds the small test projects a report used (manifests as plain
  text, plus a one-line `EXPECTED.md` per project stating the ground truth
  decided before the run). No virtual environments, caches, lock files that
  can be regenerated, or binaries. `mkex.py` regenerates the whole set,
  including the two projects whose files are not plain text.

How to read a report: trust the numbers and the commands, treat the
suggestions as one outsider's view, and compare the same finding across
reports before acting on it. Nothing in this folder changes StockTake itself.

A report is committed unchanged, before anything is done about it, so that the
input and the response stay separable and a later reader can judge both. What
was done about one lives in [../ROADMAP.md](../ROADMAP.md) — a milestone for
what was acted on, and a line under "Tech debt and known gaps" for every
suggestion deliberately not taken, with the reason.

- `2026-10-30-claude-code-session.md` (Can-AI, CLI only) is answered by M5.1 and
  [ADR 0009](../adr/0009-an-unread-file-makes-the-run-incomplete.md).
- `2026-10-30-claude-code-windows-readme-cold-trial.md` (Pixel Galaxy Studio, all
  five README routes on Windows) is answered by M5.2 and
  [ADR 0010](../adr/0010-a-run-that-checked-nothing-is-not-a-pass.md).

What the second report shows about the first is worth noticing: it found no P0s,
because the first report's P0s had been fixed, and every one of its own findings
is in a route the first trial never ran. Asking the next one to cover what the
last one could not is most of the value of doing this more than once.
