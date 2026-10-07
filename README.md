# stringline

A public build, being founded. Nothing here can be installed yet.

## What it is

Three things, in one repository:

- **A tool.** Small instruments recreated from my own way of working with AI agents, starting with one that pulls a person's own typed messages out of an AI session's record, exactly as typed and with their times, and checks every quote of them against the original. Where a tool checks what an agent said, it says what it looked at, and says "can't tell" rather than "clean" when it cannot see.
- **A build, told through its sessions and its code.** Built in public from the first commit: intent before anything, direction before code, work done by agents under written instructions, every spec reviewed by a separate reviewer (another AI agent, or a person) that did not write it, and a dated log of each decision and each wrong turn caught.
- **A manual you walk.** A clean, structured surface: one card per released tool, a walk through the record, and how the work runs. It comes later, built from one source that also writes this README.

The full intent, in my words, is [INTENT.md](INTENT.md). Where any file here disagrees with it, the intent governs.

## Where it stands

Founded on 7 October 2026. So far it holds the intent, the files that say how the work runs, and two entries of the build log. No tool exists yet; the first one has been chosen (a checker for quotes of a person's own words) and is planned next. The order of what comes next is in the build log.

## Read in this order

1. [INTENT.md](INTENT.md): what this is, why, and where it is going.
2. [BUILD-LOG.md](BUILD-LOG.md): what each session did, decided and got wrong, dated.
3. [LEARNED.md](LEARNED.md): what I learned, in my own words, each session.
4. [DECISIONS.md](DECISIONS.md): each decision and its reason.
5. [OPEN-PROTOCOL.md](OPEN-PROTOCOL.md): how a working session opens and closes, and what waits for my word.
6. [CLAUDE.md](CLAUDE.md): the instructions any AI agent working in this repository follows.

## Who builds it

I'm Chad Wallace, and I direct it; the other files call me "the owner". Claude Code, Anthropic's AI coding tool, writes the implementation under my direction and review, and the record says which is which. Each session names the Claude model it ran on.

## What stays out

The working notes live in a private folder beside this one (`../stringline-private`). Nothing moves from there into this repository without being rewritten for a reader here. No client, no other person and no private project is named, and before anything is pushed, a check refuses any push that carries a word from a private list.
