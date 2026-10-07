# How a working session runs

Every change to this repository is made in a working session: one AI agent session (Claude Code), with me present or having handed it a written brief. This page says how a session opens, works and closes, and which acts wait for my word.

## Opening

1. **Measure, never remember.** The session reads the state of both folders (this repository and its private sibling, `../stringline-private`) and the latest build-log entry, and confirms the push check still fires on a planted word before trusting it.
2. **Say who is working.** The first reply names the AI model running the session.
3. **Write down what "finished" means.** Before any work starts, the session writes a numbered list of what will be true when it is done. Each line says how it is proven: by a command, by my words, or by someone other than the session looking. I approve the list or change it. A later change is recorded as a change, never as a silent edit.

## Working

- Work runs in **lanes**: separate agent sessions, each with one aim and its own finished list.
- Anything found that is not on the list gets a home outside the lane and is not pursued in the session that found it.
- Agents called in to read or review are told which AI model to use, given exact file paths, and must open their report with DONE, INCOMPLETE or HANDBACK.
- A reviewer writes its rules before it reads the builder's account, and plants its own faults rather than running the builder's tests.

## Closing

1. The session writes its entry in [BUILD-LOG.md](BUILD-LOG.md), for a reader who was not there: every decision with its reason, every wrong turn caught.
2. A reader that did not do the work checks the session's record before it is relied on. It also checks the public log against the private notes, both ways: everything decided or corrected there has a line here, and nothing here lacks a source there.
3. What that reader finds is added to both records as a dated correction, below the text it corrects. The text above is never edited.
4. Every clock time in the record is either read from a clock or marked as an estimate.
5. Files and commit messages are scanned for private words, then committed and pushed.

## What waits for my word

The intent · which tools come next · each spec · every merge · the look of the manual · making this repository public · anything sent to any person.

A session may continue inside its own list, and re-brief a lane within that lane's aim, and tell me after. Reading, reviewing, scanning, testing, auditing and closing never wait for me.
