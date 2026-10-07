# SPEC · what will be built, precisely enough to build it unaided

A specification here answers one question: could someone who was not in the room build this from the page alone? Each part says what exists now, what is in and out, each decision with its reason, how it connects, what must not change, and what "done" means in a way that can be tested. The order the parts are built in is [MAP.md](MAP.md). Drafted at the third session (7 October 2026), stress-tested by two readers in two rounds, and approved by the owner the same day (the map's placement section as placement only); his words are in the build log's third entry. A later change to any part waits for his word again.

## The five parts

1. [SPEC-corpus.md](SPEC-corpus.md): one source, held as data, read by the manual site, the README and the agent instructions.
2. [SPEC-card.md](SPEC-card.md): one card per tool: what it is, the first thing to do, the one gotcha, what it has caught.
3. [SPEC-run-log.md](SPEC-run-log.md): one file per run, every row saying whether the run was planted or real.
4. [SPEC-guard.md](SPEC-guard.md): five checks that run on every change and say red, green or can't tell.
5. [SPEC-your-words.md](SPEC-your-words.md): the first tool, a checker for quotes of a person's own typed words.

## Decisions that bind every part

- **Runtime: Python 3.11 or later, standard library only, plus git**, for tools, checks and the renderer. *Why:* a stranger must install a tool on a clean machine and have it work; the owner's instruments are Python, the earlier manuals' checks are rewritten in it, and one runtime beats two. Git is needed because the stamps and the run log name commits.
- **Language: English**, one text per field. *Why:* the reader is a stranger, addressed in one language; the schema leaves room for a second without a rewrite.
- **One screen per file: 60 source lines**, for every page of prose and every record. *Why 60:* a convention carried from the owner's earlier work; the unit is source lines so the check reads the same on every machine. Code is not bound by it (a tool split to fit a screen is worse code); the check says what it does not read.
- **Three states, always.** Every check and every tool reports red, green or can't tell (or its own named outcomes), and says what it looked at and what it compared against. Nothing reads "clean" because it could not look. A crash or an empty answer is can't tell, never green.
- **Every check and tool says, in its own header, how it is fired and the failure that earned it.** *Why:* a correct check nothing runs is the most repeated gap in the originals; the failure that earned a check is how the owner's instruments explain themselves, and the manual's card carries it onward.
- **One workflow fires everything** (`.github/workflows/checks.yml`, on every push and pull request, full history fetched): the five checks, every self-test with `--no-log`, and the quote checker as a report with `--no-log`. The same commands run by hand. Workflow runs write nothing back to the repository, and every self-test and tool honours `--no-log`.
- **Every planted fault is a committed fixture**, under `tests/` beside the thing it tests, run by its self-test; a self-test prints fixture text only, never the material a real run reads. **A blind twin on every check**: a trigger that matches nothing is red, not green.
- **Planted or real is decided by who invokes a run, never by where a file sits.** A self-test is planted; a person's plant says so with a flag and a note; everything else a person runs is real. *Why:* a fault planted where it would really arrive sits among real files, as the intent asks, and must still never count as a catch.
- **The corpus is the registry.** The list of tools lives nowhere but the corpus; cards and check scope derive from it. `runs/` and `site/` are committed: the log and the rendered manual are part of the public record.
- **Merges never rewrite history** (no squash, no rebase onto main). *Why:* every stamp and every run row names a commit; a rewritten history orphans them all.
- **Reports, not stops, except the push check.** The owner's ruling: the private-word check refuses a push, as it does now; every other check reports, and the quote checker's four outcomes never stop work on "can't check". Whether a given tool may stop the work is decided per tool, once its run log shows what it catches.
- **Nothing private.** No code, text, name, look or commit from the owner's earlier work; each part is written fresh from the pattern. The manual says on its face that the originals are not shown and that fidelity is the owner's claim.

## Out of scope for this spec

The look of the manual (session 5, the owner's word) · any assistant · a second language · release acts, each in [MAP.md](MAP.md) under "Deferred" with its reason · and the four parts the owner placed on 7 October (the extractor, the public push scanner, the workflow over every test, the done-list checker as a hook), specified at a further session, S3b, and listed in [MAP.md](MAP.md).

## How a lane uses it

A lane reads its part and the binding decisions, states its plan as ordered steps before building, builds only what the part says, and escalates anything that would change *what* is built or *why*. A discovery that changes only *how* is the lane's to decide and record. Each lane's finished list is written before it opens.
