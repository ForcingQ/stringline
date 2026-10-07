# MAP · what depends on what, and the order it sets

Written at the third session (7 October 2026) by the method the owner builds with: list every part, ask what each one needs and what needs it, find the foundations (many things depend on them, they depend on little), build those first and build them for reuse, group the rest into tracks, and set a checkpoint between tiers. Every position below is explained by a dependency; the session numbers are the plan's guess, not the rule. A projection of this map drawn before the first session (a private page) had two lines this session does not inherit; see "New here".

**Dependency kinds.** *Data* (hard: B needs a structure A makes) · *pattern* (soft: B should reuse a shape A sets) · *context* (building A makes B's design clear).

## Three tracks, five tiers

| Tier | Surface (the manual) | Guard (runs on every change) | Tools (recreated from the practice) |
|---|---|---|---|
| **Tier 0 · foundations** (the founding; standing) | the intent, the name, the one-screen rule, the record rule | two folders; the push check refusing private words, shown on 16 cases (14 planted, 2 controls); the check that every clock time in the record says whether it was read or estimated; **standing: the scan of every commit's files and messages for private words, re-run whenever the word list grows** | — |
| **Tier 1 · specified** (this session) | the corpus schema and the card ([SPEC-corpus.md](SPEC-corpus.md), [SPEC-card.md](SPEC-card.md)) | the five checks ([SPEC-guard.md](SPEC-guard.md)) | the run log ([SPEC-run-log.md](SPEC-run-log.md)); the quote checker ([SPEC-your-words.md](SPEC-your-words.md)); the owner's typed lines ([WORDS.txt](WORDS.txt)) |
| **Tier 2 · built** (planned: session 4, four lanes) | A: the corpus, the renderer, check 3, the README and agent instructions written from the corpus, the first terms | B: checks 1 to 4, each firing on a committed planted fault; the push scanner as public code (placed, below); the workflow that runs every test and planted fault on every push | C: the run-log module first (merged before A imports it); the first tool's folder and `building` card; the checker, its self-test, its first real run; then the extractor (placed, below). D: the done-list checker as a hook (placed, below) |
| **Tier 3 · surfaced** (planned: session 5) | the look of the manual (the owner's word); the walk of the record; the first card read against its tool and `released` on the owner's word | the guard running green on the manual itself | the first card's "what it has caught", read from the log |
| **Tier 4 · released** (planned: session 6) | a stranger reads the public view cold (the repository as GitHub shows it, and the rendered site) | the pre-release scans: history for private words, a secrets scan, each shown to fire | the clean-machine run: a fresh container with Python 3.11 and git, from a clone |
| *after release* | the owner reads it, makes it public, sends the link: his acts | | the real catch (intent goal 3): the checker run on a project of the owner's, privately; that row stays private, and the build log carries its counts; the card reads only this repository's log |

## Foundations and compound returns (build broad on first use)

- **The corpus schema** (tier 1, Surface). Data dependency for the renderer, the README, the agent instructions, the card, and the scope of checks 1 and 2 (they read the tool list from it). Five consumers: one schema, one record per file, everything else derived; a hand-kept list beside it would be the drift the originals suffered from.
- **The run-log module** (tier 1 specified, first thing built in tier 2). Data dependency for the checker (its writer), the card's "what it has caught" (its reader) and the question "has this caught anything real?", asked on any date by listing `runs/`. Its load-bearing field: every row says *planted* or *real*, set by the invoker. The reader and the card's sentence live in the module so no lane copies them.
- **The typed lines** (WORDS.txt, exists). Data dependency for the checker's first real run. It holds the owner's typed messages that INTENT and LEARNED quote, exactly as typed, so the checker has real work in public from its first run; its first honest card line is *nothing caught yet*, and each later LEARNED entry adds a line it can check.

## Arrows that cross tracks

Lane C's module merges before lanes A and B write against it (data). The guard runs on the manual only once the manual exists (Guard tier 3 needs Surface tier 2). A tool's card is written to the key table in the card spec, so lane C writes its `building` card without waiting for lane A (pattern, not data). Check 2's two-way rule needs lane C's tool folder and card (data). Check 3 is lane A's because it needs the renderer (data). **Merge order, so each lane's list can close:** C's module · A · C's tool · B, the session lead re-rendering and committing on main after each.

## New here, not recreated

Three parts that projection credited to the owner's earlier manuals exist in neither of them, measured at the second session: the README and the agent instructions written from the corpus; the private-word check counted as one of the guard's checks (its shape, a banned-phrase scan over live text, is old; running it on a push is new); and a card field "what it has caught". They are built here as new work and labelled so in the manual.

## Placed by the owner's ruling of 7 October, specified at a further session (S3b) with the same review seats

*This section arrived after both review rounds had returned; the owner approved it as placement only, and S3b's two rounds review it.*

- **The extractor** (Tools, tier 2, lane C after the checker): pulls a person's typed messages, verbatim with times, out of a Claude Code session record, writing the checker's plain-text shape. *Depends on:* the checker's input shape (data); synthetic session records as public fixtures, since the owner's real records stay private (data). *Changes lane C:* a second half after the checker, its own self-test and card line; the checker's "out" line moves to "after it".
- **The push scanner as public code** (Guard, tier 2, lane B): rebuilt from its proven private design with invented plants; the word list stays private. *Depends on:* nothing built here (the design exists at tier 0). *Changes lane B:* check 5 becomes the whole scanner, pre-push hook text included, with its 14-plant, 2-control shape; the owner's private hook keeps guarding this repository.
- **The workflow** (Guard, tier 2, lane B; already placed): runs every test and planted fault, of every track, on every push. *Depends on:* each lane's self-tests existing (data). *Changes lane B:* its workflow item covers the tools' tests, not only the checks'.
- **The done-list checker as a Claude Code hook with its own tests** (Tools, tier 2, a fourth lane, D): the runner-up tool ([DECISIONS.md](DECISIONS.md) #16). *Depends on:* the run-log module (data); the card schema (data). *Adds lane D*, after C's module merges; its card is the second.

## Deferred, with the reason

- **An assistant that answers from the manual.** It would put a model call inside the product; no agent ships yet ([DECISIONS.md](DECISIONS.md) #7).
- **A second language.** The earlier manuals were bilingual for their products' users; this one writes for a stranger in English. The schema keeps one text per field so a second language is a schema change, not a rewrite.
- **Per-session cost logging; which tools come after the second.** Both are "not decided, on purpose" in the intent.
- **Checks writing to the run log.** A workflow cannot commit, so a check's row would never reach the folder. Checks report in the workflow; the log is the tools', written by a person's runs.
- **A check on notes kept inside the manual's source.** The earlier manuals kept dated build notes as comments; here the record is the build log, so there is nothing to strip.

## Checkpoint between tiers

Before the next tier starts: did everything in this tier ship as specified (each spec's "done when" read, not assumed)? Are the next tier's prerequisites actually there (the corpus parses; the run log holds one planted row and one real row; each check fires on its committed plant)? Did this tier show a dependency this map lacks? Were the reusable parts (schema, log module) finished before a second consumer copied them? Two next-tier parts depending on something that shipped differently means this map is updated before work continues.
