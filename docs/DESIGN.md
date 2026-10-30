# StockTake: output design

StockTake has no graphical interface. Its interface is a terminal report, an exit code and a JSON document, so this is where the usual `DESIGN.md` content goes: audience and tone, the tokens (here: statuses, severities, exit codes), the inventory of output states, and the writing rules. The web-app parts of the house standard — light/dark toggle, info buttons, brand assets, WCAG layout work — do not apply to a CLI tool and are deliberately absent. Accessibility is addressed below as terminal accessibility, which is a real concern and a different one.

## Audience and tone
Read by someone who is in the middle of something else and wants to know whether they have to care. Tone: a colleague reporting what they found, not a scanner shouting. Never alarmist, never reassuring beyond the evidence. "No known advisories" is sayable; "safe" is not.

The first line of every report answers the only question most runs have: is there anything to do.

## Tokens

### Statuses, in report order
| Status | Means | Severity | Build |
|---|---|---|---|
| `vulnerable` | an advisory affects the version in use | `fail` | **fails** |
| `yanked` | the author withdrew this release | `fail` | **fails** |
| `outdated` | a newer release exists | `warn` | warning in the summary, never a failure |
| `held` | outdated on purpose, per policy, until a date | `info` | listed |
| `unpinned` | no version fixed; what installs depends on when | `info` | listed |
| `unknown` | not found, or that one answer could not be had | `info` | listed |
| `current` | newest release, no known advisories | `ok` | counted only |

Order is fixed and is the design: what must be fixed is first, what is merely interesting is last, and `current` collapses to a count so a long clean list never buries a short dirty one.

### Advisory severities
`CRITICAL` > `HIGH` > `MODERATE`/`MEDIUM` > `LOW` > unrated. Taken from the advisory database, never invented. Unrated advisories sort last and print as `unrated`, not as `LOW`.

### Exit codes
| Code | Means |
|---|---|
| 0 | nothing unsafe. Outdated dependencies do not change this. |
| 1 | a vulnerable or withdrawn release, or a policy entry past its date. |
| 2 | the check could not be completed: the registries could not be reached, or the configuration could not be read. Not a judgement about the project. |

Three codes, each with one meaning. A caller can branch on them without parsing output. Code 2 covers both ways of not knowing, because the useful distinction for a caller is "the check reached a verdict" versus "it did not" — and a config file that cannot be parsed must never quietly fall back to defaults, which would mean the project's policy silently stopped applying.

### Update sizes
`major`, `minor`, `patch`, from the first position where the versions differ. Named rather than numbered because the useful question is "how scared should I be of this bump".

## Output states
Every one of these is a state the report must handle, and each has a test:

- **Nothing to report.** One line: counts, all zero where they should be. No empty section headings.
- **Everything current.** `CURRENT: 48 up to date` and nothing else.
- **One vulnerable package.** The worst case made small: source, name, version, the advisory count by severity, and the one version that clears them all.
- **A package with many advisories.** The worst five, then `... and 36 more` with the flag that shows them. (A real package returned 90. Printing 90 is the same as printing none.)
- **Advisories with no named fix.** `no fixed version named`, never a blank or a guess.
- **Partly offline.** Those names are `unknown` with the reason; the rest of the report is normal; exit code unchanged.
- **Fully offline.** The header carries the reason in brackets, every finding is `unknown`, exit 2, and nothing claims to be clean.
- **Rate limited.** Distinguished from offline in the note, because the fix is different (set `GITHUB_TOKEN`, or wait).
- **Notes.** Above everything else, along with policy problems: anything that changes how much of the report can be trusted. The one that exists today is "no Python environment was found", which means every declared range went unresolved — and it names the flag that fixes it, because a note that only states a problem is half a note.
- **Policy problems.** Above the findings, because a report whose policy has expired is not trustworthy until that is settled.
- **Unread manifest.** Named, with what it would take to read it. One the project has accepted in its config is not printed, but still appears in the JSON report: an unchecked surface may stop nagging, never become invisible.
- **No dependencies found at all.** Said explicitly, because silence looks like success. A project where the scanner found nothing is much more likely to be misconfigured than genuinely dependency-free.

## Report formats
- **`text`** (default) — for a person at a terminal. The layout below.
- **`json`** — one object, every field, stable keys. For another program, including the author's own project dashboards.
- **`sarif`** — SARIF 2.1.0, one result per finding with a physical location of file and line, so GitHub code scanning and editors can place them. What becomes a result is a judgement, not a translation: failures are `error`, informational findings are `note`, a dependency with nothing wrong with it is not a result at all, and a `held` dependency is a decision the project already recorded and does not need shown back. Anything about the *run* rather than a dependency goes in the invocation's notifications, where SARIF puts that.
- **`summary`** — one line, verdict first, because that is the part that survives being truncated into a status bar.

`--only` narrows every one of them identically; the mapping lives in one place (`report/choices.py`) so it cannot mean different things in different formats.

### The text layout
From a real run, abridged:

```
Dependency check 2026-10-30: 5 checked, 2 vulnerable, 0 withdrawn, 1 outdated, 1 unpinned

POLICY: hold_back: webauthn was accepted until 2026-10-01 and is due for a decision again (3.x is a major release)

VULNERABLE (fix these)
  Dockerfile:3    pillow 9.0.0  52 advisories (6 critical, 32 high, 12 moderate, 2 unrated); upgrade to 13.0.0 or newer
      GHSA-332p-7hrc-92wf CRITICAL: Pillow: Heap buffer overflow in _tiffWriteProc when saving TIFF to BytesIO
      ... and 47 more (stocktake --only vulnerable --all-advisories)

OUTDATED
  Dockerfile:9    mostlygeek/llama-swap 262 -> 268 (major)

UNPINNED
  Dockerfile:3    ruff (none)  no version is pinned: whatever is newest when the image is built

CURRENT: 1 up to date
```

Rules the layout follows:
- **The source location comes first on every row,** in a fixed-width column. It is what you act on, and it makes the output greppable and clickable in most terminals.
- **One finding per line,** with its evidence indented beneath it. Never a wrapped paragraph.
- **No colour, no Unicode box drawing, no spinners, no progress bars.** The output goes into pytest summaries, CI logs and pipes, where all of that becomes noise or mojibake. Severity is carried by the word, the section and the order — never by colour alone, which is also the accessibility answer.
- **Counts in the header are absolute,** so a diff between two runs is readable.
- **Every "there is more" has the exact command that shows it.** The report tells you how to get the rest of itself.

## Writing rules for the report text
- Say what was found and what to do, in that order. `pillow 12.3.0 -> 13.0.0 (major)`, not `Vulnerability detected in dependency`.
- Name the file and the line. Never "in your project".
- A reason always accompanies a refusal to judge: `offline: no route to host`, `rate limited: api.github.com answered 429`, `not found on the registry`.
- Advisory summaries come from the database, truncated to 160 characters, never rewritten.
- No exclamation marks, no emoji, no "⚠", no capitalised shouting beyond the section headings and the severity words.
- Second person for instructions (`upgrade to 13.0.0 or newer`), no first person anywhere.
- Dates are ISO (`2026-10-29`). Versions are printed exactly as the registry gives them.

## CLI shape
```
stocktake [--root PATH] [--format text|json|sarif|summary] [--only all|outdated|vulnerable]
          [--config PATH] [--environment PATH] [--refresh] [--all-advisories] [--version]
stocktake init   [PATH] [--tests PATH] [--force]
stocktake vendor [PATH]
```

`init` never overwrites without `--force`, because the file it writes becomes the project's own. `vendor` always overwrites, because the file it writes is generated and refreshing it is the whole point — and the file itself says not to edit it.

Inside a test suite the same rules reach the reader as pytest's own vocabulary rather than as a report: a **failure** carries the narrowed report as its message, a newer release is a **warning** in the summary, and an unreachable registry is a **skip** with its reason. That mapping is the whole of the plugin; the rules themselves are shared with this command (`stocktake.check`).

The flag is `--config`, not `--policy`: the file holds the excludes and the enabled ecosystems as well as the policy, so naming it after one of its tables would be wrong.
Defaults chosen so the bare command is the useful one: current directory, text, everything, cache honoured, worst five advisories per package. Every flag has a long form; short forms are not provided, because this is read in scripts more often than typed.

`--help` is the documentation most people will read, so each flag's help text says what it is for, not what it is.

## Terminal accessibility
- Information is never carried by colour alone; in fact no colour is emitted at all.
- Output is plain ASCII, so it survives screen readers, Windows consoles, CI log viewers and pipes without re-encoding.
- Nothing depends on terminal width: lines are allowed to be long rather than reflowed, so that piping to `grep` gives whole findings.
- No cursor control, no in-place updating, no clearing the screen. The transcript of a run stays complete and readable after the fact.
