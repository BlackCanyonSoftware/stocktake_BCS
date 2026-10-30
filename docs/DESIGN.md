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
| 2 | the registries could not be reached. Not a judgement about the project. |

Three codes, each with one meaning. A caller can branch on them without parsing output.

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
- **Policy problems.** Above everything else, because a report whose policy has expired is not trustworthy until that is settled.
- **Unread manifest.** Named, with what it would take to read it.
- **No dependencies found at all.** Said explicitly, because silence looks like success. A project where the scanner found nothing is much more likely to be misconfigured than genuinely dependency-free.

## Report formats
- **`text`** (default) — for a person at a terminal. The layout below.
- **`json`** — one object, every field, stable keys. For another program, including the author's own project dashboards.
- **`sarif`** — SARIF 2.1.0, one result per finding with a physical location of file and line, so GitHub code scanning and editors can place them. (M4)
- **`summary`** — one line, for a status bar or a CI step name. (M4)

### The text layout
```
Dependency check 2026-10-29: 71 checked, 4 vulnerable, 0 withdrawn, 13 outdated, 5 unpinned

POLICY: hold_back: webauthn was accepted until 2026-10-01 and is due for a decision again (3.x is a major release)

VULNERABLE (fix these)
  docker/dev/Dockerfile:12     pillow 12.3.0  41 advisories (5 critical, 36 moderate); upgrade to 13.0.0 or newer
      GHSA-xxxx-xxxx-xxxx CRITICAL: Buffer overflow in the ICO decoder
      ... and 36 more (stocktake --only vulnerable --all-advisories)

OUTDATED
  pyproject.toml               pytest 8.3.1 -> 8.4.2 (minor)

UNPINNED
  docker/dev/Dockerfile:6      ruff (none)  no version is pinned: whatever is newest when the image is built

CURRENT: 48 up to date
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
          [--policy PATH] [--refresh] [--all-advisories]
stocktake init [PATH]      write a test file and a starter .stocktake.toml
stocktake vendor PATH      write the single-file copy
```
Defaults chosen so the bare command is the useful one: current directory, text, everything, cache honoured, worst five advisories per package. Every flag has a long form; short forms are not provided, because this is read in scripts more often than typed.

`--help` is the documentation most people will read, so each flag's help text says what it is for, not what it is.

## Terminal accessibility
- Information is never carried by colour alone; in fact no colour is emitted at all.
- Output is plain ASCII, so it survives screen readers, Windows consoles, CI log viewers and pipes without re-encoding.
- Nothing depends on terminal width: lines are allowed to be long rather than reflowed, so that piping to `grep` gives whole findings.
- No cursor control, no in-place updating, no clearing the screen. The transcript of a run stays complete and readable after the fact.
