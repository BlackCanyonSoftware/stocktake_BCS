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
