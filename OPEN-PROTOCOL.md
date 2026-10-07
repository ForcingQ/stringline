# How a working session runs

Every change to this repository is made in a working session: one AI agent session (Claude Code), with me present or having handed it a written brief. This page says how a session opens, works and closes, and which acts wait for my word.

## Opening

1. **Measure, never remember.** The session reads the actual state, rather than trusting what an earlier session said about it: both folders (this repository and its private sibling, `../stringline-private`) and the latest build-log entry, and confirms the push check still fires on a planted word before trusting it.
2. **Say who is working.** The first reply names the AI model running the session.
3. **Write down what "finished" means.** Before any work starts, the session writes a numbered list of what will be true when it is done. Each line says how it is proven: by a command, by my words, or by someone other than the session looking. I approve the list or change it. A later change is recorded as a change, never as a silent edit.

## Working

- Work runs in **lanes**: separate agent sessions, each with one aim and its own finished list.
- Anything found that is not on the list gets a home outside the lane and is not pursued in the session that found it.
- Agents called in to read or review are told which AI model to use, given exact file paths, and must open their report with DONE (finished), INCOMPLETE (stopped short, and says what is missing) or HANDBACK (blocked, and says by what).
- A reviewer writes its rules before it reads the builder's account, and plants its own faults rather than running the builder's tests.

## Closing

1. A separate AI agent, given only this repository, reads it cold and reports what it cannot follow. The session fixes what it can before closing.
2. The session asks me what I learned, and records my words exactly in [LEARNED.md](LEARNED.md). The close does not finish without my words, or my saying there is nothing this time.
3. The session writes its entry in the build log ([BUILD-LOG.md](BUILD-LOG.md) lists every entry), for a reader who was not there: every decision about the build with its reason, every wrong turn caught.
4. A reader that did not do the work (a separate AI agent, briefed only to check) checks the session's record before it is relied on. It also checks the public log against the private notes, both ways: every decision or wrong turn about the build itself has a line here, and nothing here lacks a source there. Upkeep of the owner's other work (keeping shared notes tidy, the state of other work, the lists and logs he keeps for himself) is kept private, and the entry counts it in one line: how many items, and why. The reader checks that every private item is either in the log or in that count.
5. What that reader finds is added to both records as a dated correction, below the text it corrects. The text above is never edited.
6. Every clock time in the record is either read from a clock or marked as an estimate.
7. Files and commit messages are scanned for private words, then committed and pushed.

## What waits for my word

The intent · which tools come next · each spec · every merge · the look of the manual · making this repository public · anything sent to any person · taking any word off the private word list.

Each of these comes to me as one line: what the session recommends, why, and what it will do on my yes. Everything else the session decides, records with its reason, and tells me after. A question the session can answer by reading or measuring is not a question for me.

A session may continue inside its own list, and re-brief a lane within that lane's aim, and tell me after. Reading, reviewing, scanning, testing, auditing and closing never wait for me.
