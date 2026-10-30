# ADR 0004: Only unsafe findings fail the build

- **Date:** 2026-10-29
- **Status:** accepted

## Context
This is the decision the whole product rests on, so it gets an ADR even though it carries over unchanged from `ai-suite`.

A dependency check that runs inside a test suite can fail the suite. The temptation is to fail on anything the check dislikes, because a warning nobody reads protects nobody. The counter-pressure is stronger: a check that fails the build because a dependency is four months behind gets switched off within a week, and then it protects nothing at all. The PRD's success metric is not findings, it is that the check is still enabled three months later.

The first real run of the original found four packages with known advisories, including several rated critical, alongside thirteen merely-outdated pins. If those thirteen had failed the build, the four would never have been looked at.

## Options considered

**A. Fail only on vulnerable, withdrawn, or an expired policy entry.** Outdated warns, in the pytest summary, where it is visible without being fatal. Unpinned and unknown are listed. Being behind is information; being known-vulnerable is a defect.

**B. Fail on anything outdated.** Keeps a project genuinely current. Also fails every Monday for reasons nobody chose, on a schedule set by other people's release habits. This is the option that gets the tool uninstalled.

**C. Fail on nothing; report only.** Never annoying, never noticed. A report that cannot fail is a report nobody runs.

**D. Fail by advisory severity threshold** (critical and high fail, moderate and low warn). Appealing, and rejected for now: severity ratings are inconsistent between databases and frequently absent altogether, so the threshold would be decided by metadata quality rather than by risk. An unrated advisory is not a minor one. Revisit if the fail list proves too noisy in practice.

## Decision
Option A.

| Finding | Build |
|---|---|
| `vulnerable` — an advisory affects the version in use | **fails** |
| `yanked` — the author withdrew this release | **fails** |
| policy entry past its `until` date, or missing a `reason` or `until` | **fails** |
| `outdated` — a newer release exists | warns in the test summary; exit code unaffected |
| `held`, `unpinned`, `unknown` | listed |
| registries unreachable | the test **skips**; the CLI exits 2 |

Three supporting rules make this hold up:

1. **An unreachable registry is `unknown`, never clean.** Treating a timeout as "no advisories found" would turn a network blip into a false all-clear, which is worse than any false positive.
2. **Accepting a risk expires.** A policy entry needs a reason and an `until` date; past that date it stops suppressing anything *and* fails the check. This is what stops "ignore it for now" from becoming permanent through neglect, and it is why the escape hatch can be trusted.
3. **Advisory noise is a reporting problem, not a severity problem.** One package returned 90 OSV entries. Aliases are merged, the worst five are shown with a count of the rest, and the single version that clears them all is named. An unreadable failure is a failure that gets suppressed.

A strictness flag that makes a major-version gap fail is deliberately *not* added now. It is a one-line feature whenever a project asks for it, and adding it before anyone asks invites turning it on by default.

## Consequences
- **Good.** The check can be left on. That is the entire point.
- **Good.** A failure means something specific and actionable every time, which is what keeps people reading failures.
- **Good.** The escape hatch is safe to use, because it cannot quietly become permanent.
- **Cost.** A project can drift a long way behind without the build ever complaining. Accepted: the warning is in every test summary and `stocktake --only outdated` is one command. Drift is a choice made visibly, not an accident.
- **Cost.** A vulnerable dependency with no available fix fails the build with nothing to do about it except write a policy entry. That is the correct amount of friction for knowingly shipping a known vulnerability — it takes a sentence of justification and a date.
- **Cost.** Severity is not used to decide anything, so a low-severity advisory in a dev-only tool fails the build like a critical one in production code. Policy entries are the release valve, and option D is revisited if that proves too blunt.
