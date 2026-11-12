# Security

StockTake reads other people's dependency files and talks to public registries, so it is worth being precise about what it does, what it
cannot do, and how to tell us when it does something it should not.

## Reporting a vulnerability

Use GitHub's private reporting: **[Report a vulnerability](https://github.com/BlackCanyonSoftware/stocktake_BCS/security/advisories/new)**.
It is private until we publish it, and it is the only channel we watch for this. Please do not open a public issue for a security problem.

Tell us what you did, what happened, and what you expected. A file that triggers it is worth more than a description of one. You will get an
acknowledgement, and we will tell you what we find and when it is fixed. This is a small project maintained in spare time: expect days, not
hours.

## What StockTake does, exactly

The design is small on purpose, and several of these are enforced by tests rather than by intention:

- **It never executes anything it finds.** No importing a scanned package, no running a lock file's scripts, no shelling out to a package
  manager. A dependency file is read as text and nothing in it is ever run.
- **It never edits a file in your project.** `--format propose` prints the change it would make and does not make it. The only files it
  writes are the ones you explicitly ask for: `stocktake init` and `stocktake vendor`.
- **Only package names and versions leave your machine**, to `pypi.org`, `registry.npmjs.org`, `api.github.com`, `api.osv.dev` and — for a
  base image — the container registry that image names. No paths, no file contents, no telemetry, no account.
- **It has no runtime dependencies**, which is the point: a tool for watching your supply chain is a poor advertisement for itself if
  adopting it widens that supply chain.
- **A registry it cannot reach is `unknown`, never clean.** It will tell you it does not know; it will not guess.

## What it is not

- **It is not a scanner of your code**, only of what your project declares. It cannot tell you whether a vulnerable function is reachable.
- **It does not check what is inside a container image.** For a `FROM` line it reports whether a newer tag exists and nothing more; the
  distro packages in that image are a different question and want a different tool.
- **It does not check a GitHub release binary for advisories.** OSV has no key that identifies one, so claiming to have checked it would be
  dishonest. You get "is there a newer tag".
- **Its findings are OSV's findings.** StockTake merges, ranks and reports them; it does not discover vulnerabilities, and an advisory that
  OSV does not carry is one StockTake will not mention.

## What counts as a vulnerability in StockTake

Most valuable, in rough order:

1. **Anything that makes it report a project as clean when it is not.** A manifest silently skipped, a finding dropped, an exit code that
   says "nothing unsafe" about a run that did not look. This is the failure the whole design is arranged against, and it is the one we most
   want to hear about.
2. **Anything executed that should not be.** A crafted dependency file that gets code to run, in any reader.
3. **Anything leaving the machine that is not a package name or version.**
4. **A crash on a hostile input.** Less serious — it is loud, and a loud failure is the safe kind — but still a bug.

A malformed file that StockTake *refuses* with a clear message is working as designed, not a vulnerability: an unreadable manifest makes the
run incomplete and exits 2 on purpose.

## Supported versions

Pre-1.0. Fixes go to the default branch and into the next release; there are no backports.

| Version | Supported |
|---|---|
| the default branch and the newest release | yes |
| anything older | no |
