# ADR 0012: Container base images, and why a tag is not a version

- **Date:** 2026-11-05
- **Status:** accepted
- **Builds on:** [ADR 0008](0008-a-tag-its-publisher-moves-is-a-range.md)

## Context
`FROM python:3.12-slim` is a dependency by every definition this project uses: somebody chose a version, it goes stale, and the choice is invisible to a hosted dependency bot. StockTake has read Dockerfiles since the first milestone — for their `pip install` lines and the binaries they download — and passed over the `FROM` line without a word.

That is worse than it sounds, and worse than the gaps the two outside trials found. An **unread file** has always been named in the report ([ADR 0010](0010-a-run-that-checked-nothing-is-not-a-pass.md) now makes a project of nothing but unread files exit 2). This was a silent gap *inside a file that is read*: the report said `docker/Dockerfile` had been checked, and it had, for two of the three kinds of pin in it. Nothing anywhere said the third kind existed.

A census of the author's own repositories put the size of it at nine Dockerfiles across five projects, every one of them on a base image nobody was watching.

Three things make this harder than matching `FROM`:

1. **A stage is not an image.** `FROM builder` in a multi-stage build refers to an earlier `FROM ... AS builder`. Asking a registry about a package called `builder` produces a confident `unknown` about something that was never a dependency.
2. **A registry is not Docker Hub.** The roadmap assumed it was. The real `FROM` lines span three: Docker Hub, `ghcr.io` and `mcr.microsoft.com`.
3. **A tag is not a version.** This is the hard one, below.

## The tag problem

Four real tags, from four real Dockerfiles:

| tag | what it is |
| --- | --- |
| `python:3.12-slim` | a version **and a variant** |
| `debian:bookworm-slim` | a Debian release name; no version at all |
| `ghcr.io/jamezrin/lurkloot-cli:1.17.0` | an ordinary pin |
| `mcr.microsoft.com/playwright/python:v1.47.0-jammy` | a version and a variant, `v`-prefixed |

`python`'s tag listing has **4117 entries**. The newest is some `3.15.0a3`, and the newest plain release is `3.15.2`. Both are the wrong answer for somebody on `3.12-slim`: the first is an alpha, and the second is not slim. Telling a project running a slim image to move to one that is not slim is not an upgrade, it is a different image.

## Options considered

**A. Compare against the newest tag of the image.** What a naive reader does, and wrong for every suffixed tag in the table above.

**B. Treat any tag with a suffix as uncomparable.** No false advice, and no findings for most real Dockerfiles, since `-slim`, `-alpine` and `-jammy` are how base images are actually pinned.

**C. Carry the variant as part of what is being asked about, and compare only within it.** `python:3.12-slim` asks "what is the newest `N-slim` of `python`", and is answered `3.15.2` — a tag that exists, that is slim, and that a person can paste into the file.

**D. Resolve the digest behind each tag and compare those.** Exact, and answers a different question: it says whether the tag has moved, not whether a newer release line exists. It also doubles the requests.

## Decision
Option C, with everything that cannot be ordered said plainly rather than guessed at.

- The variant is part of the dependency's **name**: `python:3.12-slim` is the dependency `python:slim` at version `3.12`. Two Dockerfiles on different variants of one image are then two different things to ask about, which is what they are. The report reads `python:slim 3.12 -> 3.15.2 (minor)`.
- The client lists a repository's tags, keeps only those that **are** a version with the **same** variant, and answers with the newest. `3.15.0a3-slim` is not a version by that grammar and is skipped, so a prerelease is never recommended.
- `container_tag` — the grammar of "is this tag a version, and what variant is it" — lives in `versions.py`, because the reader needs it to read a `FROM` line and the client needs it to read a tag listing, and [ADR 0003](0003-readers-and-registry-clients-as-separate-interfaces.md) forbids either importing the other.
- **A tag that names no version is reported, with the reason, and never compared.** `debian:bookworm-slim` is `unpinned` with "the tag `bookworm-slim` names a release channel rather than a version". It keeps its tag in its name, because `debian (none)` does not say which line to go and look at. The same for `latest`, for a digest pin, and for a build argument the file never defines.
- **Moving tags are [ADR 0008](0008-a-tag-its-publisher-moves-is-a-range.md)'s rule, unchanged.** `python:3.12` already points at the newest 3.12.x, so the comparison is made to the precision written: `3.12` → `3.15.2` is an update, `3.12` → `3.12.8` is not. A tag with a digest beside it is not moving.
- **One client for every registry, through the registry's own handshake.** Ask for the tag listing; if the answer is "not without a token", get one from the conventional endpoint and ask again. Docker Hub and `ghcr.io` both need one for a *public* image; `mcr.microsoft.com` does not and is never asked. That is why this is a handshake rather than a table of hosts: it covers registries nobody here has tried.
- **No advisory check**, exactly as GitHub release downloads have none. OSV has no ecosystem for a container image, so the report says only whether a newer tag exists. What is *inside* the image — its distro packages — is a different question this does not answer either, and the docs say so rather than letting a clean row imply it.

## Consequences
- **Good.** The gap is closed, and it was real: four outdated base images in one of the author's repositories, a `python:3.12` three release lines behind in two others.
- **Good.** The handshake made `ghcr.io` and `mcr.microsoft.com` work without either being planned for, which is the test of doing it the registry's way.
- **Good.** It forced two things that were wrong anyway into the open. `groups()` returned registration order, which the single-file copy did not share, so package and copy disagreed about something a caller can see; it is sorted now. And `evaluate` asked a registry about names that nothing pins, whose answers `_judge` discards before reading — invisible waste until a tag listing made it 67 KB of cache per unpinned image.
- **Cost.** A tag listing is big. `python` is 89 KB and `debian` 67 KB, against about 2 KB for a small `ghcr.io` image. The existing roadmap item about shrinking the cache (first raised when it reached 60–82 MB) now matters more, and the fix is the same one for every client: store what is read, not what was returned.
- **Cost.** The variant-in-the-name convention is a small abuse of a field that elsewhere holds a package name. It is the least bad of the options — the alternative is widening the `Client` protocol so a lookup can carry the current version, which every other ecosystem would then have to ignore.
- **Cost.** Only the first `FROM` of a build stage is a dependency in any useful sense, and all of them are reported. A multi-stage build that uses one base image twice produces two rows at two lines. Correct, and noisier than it needs to be.
- **Cost.** `docker-compose.yml` and `compose.yaml` name images too, in YAML, and are not read. They remain on the unread list, which is the honest place for them until the YAML question in M6 is settled.
