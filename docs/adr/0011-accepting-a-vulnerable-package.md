# ADR 0011: Accepting a vulnerable package, in one entry

- **Date:** 2026-10-30
- **Status:** accepted
- **Refines:** [ADR 0004](0004-only-unsafe-findings-fail-the-build.md)

## Context
Before this, there were two ways to record a decision in a project's config, and neither covered the case that actually arises:

- `ignore_advisories` accepts **one advisory**, by id or alias.
- `hold_back` accepts **being out of date**, and deliberately does not suppress a vulnerability. The second trial confirmed that behaviour and agreed with it.

So the only way to accept a known advisory is one entry per advisory id. The [Windows README-first trial](../feedback/2026-10-30-claude-code-windows-readme-cold-trial.md) put the cost of that in numbers, from the project it was reporting on:

> If wired into `npm run check` [...] no policy line available today makes it pass honestly: `extract-zip` has no fix; `electron` is nine majors away; `hold_back` does not cover vulnerabilities. The route would be 58 `ignore_advisories` entries (46 + 12) with a reason and a date each.

Fifty-eight entries, each needing its own reason and expiry, to describe one decision: *we are carrying this version of Electron this quarter*. Nobody writes that file. The report's own conclusion was to use the SARIF route in CI, "where findings are visible but do not block merges", and not the failing-test route at all.

That is the outcome worth avoiding. The argument for ADR 0004 — that StockTake fails only on things worth acting on, so a failure means something — depends on the check being switched **on**. A policy that cannot express a real decision does not make projects safer; it makes them turn the gate off, and a gate that is off reports nothing at all. The friction was protecting the wrong thing.

The counter-argument is real and is why this was not done the first time it came up: per-advisory friction is exactly what stops a policy file becoming a blanket. `ignore_package = "electron"` is a much bigger statement than `ignore_advisories = ["GHSA-..."]`, and it will be used where the narrow form would have been enough.

## Options considered

**A. Leave it.** Defensible on paper: the narrow form is safer, and a project carrying 46 advisories arguably *should* find it painful. In practice the pain is not felt as "upgrade Electron", it is felt as "do not gate on StockTake", and then the 47th advisory arrives unnoticed. Rejected because the observed behaviour of a real project is better evidence than the intent of the design.

**B. `ignore_package` accepting a package outright, any version.** One entry, and it keeps applying after the next upgrade — which is precisely wrong. `electron 33.4.11` being accepted says nothing about `electron 34`, and an acceptance that silently followed the package forward would hide advisories in a version nobody had looked at. That is the one failure a policy file must not have.

**C. `ignore_package` with a `version`, a reason and an `until`, accepting every advisory against that exact version.** The decision a person actually makes, written once. Any-version remains available by leaving `version` out, so the broad statement exists but is never what a reader has to infer from a file that is silent.

**D. A severity threshold — "accept anything below HIGH".** Worse than all of the above. It is a standing rule rather than a decision about a known risk, it has no expiry attached to anything in particular, and it would silently accept a future advisory nobody has read.

## Decision
Option C, with the acceptance made loud rather than silent.

- `[[policy.ignore_package]]` takes `package`, `reason`, `until` and an optional `version`. Same shape, same requirements and same expiry behaviour as the other two kinds: an entry past its date stops suppressing **and** fails the run.
- Matching is on the exact version by default. No `version` means any version, which a config file has to say by omission deliberately.
- A matched finding gets a new status, **`accepted`**, with severity `info`. It does not fail the build.
- **The advisories are kept, not dropped.** An acceptance is a decision to carry a known risk, and a report that stopped showing the risk would make the decision impossible to review — which is the entire argument for requiring a date on it. The row lists its advisories exactly as a `vulnerable` row does.
- `accepted` sits third in report order, directly under the two statuses that fail and above `outdated`. It is the most serious thing in the report that is not a failure.
- It is in the headline (`6 vulnerable (2 packages), 1 accepted`), in the one-line summary, and in JSON's `counts`. The summary says "nothing unsafe **beyond what is accepted**" rather than "nothing unsafe", because the shorter phrase would be a lie with a carried vulnerability in hand.
- SARIF reports it as a **warning**: more than a note, because it is a live vulnerability; less than an error, because it fails nothing. It stays in the code-scanning view so the decision can be reviewed there.
- `--only vulnerable` and `--only outdated` both include it. Narrowing is for hiding what needs no action, never for hiding risk.
- A withdrawn release can be accepted the same way, since `yanked` fails for the same reason `vulnerable` does.
- Separately, and for the same reason as `excludes`: a **misspelt policy kind is now refused**. `[[policy.ignore_packages]]` used to be read as no policy at all, which in this file is the worst place for a silent nothing.

## Consequences
- **Good.** The decision a project actually makes can be written down in one entry, with a reason and a date, so the gate can stay on. One entry replaced 46 in a test built from the trial's own numbers.
- **Good.** It closes part of a gap left open by the first trial: "a suppressed advisory leaves no audit trail in the report". An accepted one now has a status, a section, a count in four formats and a dated entry, which is a better trail than an ignored advisory id has.
- **Good.** The expiry does the work the friction was doing. The decision has to be renewed on a date, in the open, which is a better control than making the file tedious enough that nobody writes it.
- **Cost.** It is a broader instrument, and it will be reached for where `ignore_advisories` would have been the honest answer. Nothing prevents that, and nothing should: the project owner is the one making the call. The report keeps it visible, the date forces a review, and that is the whole defence.
- **Cost.** A fourth status, and `STATUSES` is now eight long. Every format had to learn it, and a ninth would be worth resisting.
- **Cost.** A stale entry — one that matches nothing, because the package was upgraded — is not reported as stale. It simply stops applying, silently, until its date comes round. Noted in the roadmap; the fix is to report unused policy entries, which wants doing for all three kinds at once.
- **Cost.** `accepted` findings count toward the `N checked` total and sit in `counts`, so a project comparing headline numbers across a config change will see `vulnerable` drop and `accepted` rise. That is the intent, and it does mean the single `vulnerable` figure is no longer the whole risk picture on its own.
