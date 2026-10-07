# stringline

A public build, being founded. Nothing here can be installed yet.

## What it is

Three things, in one repository:

- **A tool.** Small instruments recreated from my own way of working with AI agents, starting with one that checks every quote of a person's own words against what that person actually typed, and says exact, corrected, absent or can't check. Pulling the typed messages out of an AI session's record comes after it. Where a tool checks what an agent said, it says what it looked at, and says "can't tell" rather than "clean" when it cannot see.
- **A build, told through its sessions and its code.** Built in public from the first commit: intent before anything, direction before code, work done by agents under written instructions, every spec reviewed by a separate reviewer (another AI agent, or a person) that did not write it, and a dated log of each decision and each wrong turn caught.
- **A manual you walk.** A clean, structured surface: one card per released tool, a walk through the record, and how the work runs. It comes later, built from one source that also writes this README.

The full intent, in my words, is [INTENT.md](INTENT.md). Where any file here disagrees with it, the intent governs.

## Where it stands

Founded on 7 October 2026. So far it holds the intent, the files that say how the work runs, three entries of the build log, the map of what depends on what ([MAP.md](MAP.md)), and the specification of what is built next ([SPEC.md](SPEC.md) and its five parts). No tool exists yet; the first one, a checker for quotes of a person's own words, is specified and is built in the next session. [WORDS.txt](WORDS.txt) already holds the owner's typed lines that the intent quotes, so the checker has real work from its first run.

## Read in this order

1. [INTENT.md](INTENT.md): what this is, why, and where it is going.
2. [BUILD-LOG.md](BUILD-LOG.md): what each session did, decided and got wrong, dated.
3. [LEARNED.md](LEARNED.md): what I learned, in my own words, each session.
4. [DECISIONS.md](DECISIONS.md): each decision and its reason.
5. [MAP.md](MAP.md) and [SPEC.md](SPEC.md): the order of the work, and what is built next.
6. [OPEN-PROTOCOL.md](OPEN-PROTOCOL.md): how a working session opens and closes, and what waits for my word.
7. [CLAUDE.md](CLAUDE.md): the instructions any AI agent working in this repository follows.

## Who builds it

I'm Chad Wallace, and I direct it; the other files call me "the owner". Claude Code, Anthropic's AI coding tool, writes the implementation under my direction and review, and the record says which is which. Each session names the Claude model it ran on.

## What stays out

The working notes live in a private folder beside this one (`../stringline-private`). Nothing moves from there into this repository without being rewritten for a reader here. No client, no other person and no private project is named, and before anything is pushed, a check refuses any push that carries a word from a private list.
