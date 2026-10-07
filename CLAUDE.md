# Instructions for an AI agent working in this repository

Read [INTENT.md](INTENT.md) first. Where anything disagrees with it, the intent governs. How a session opens and closes is in [OPEN-PROTOCOL.md](OPEN-PROTOCOL.md).

## Write for a stranger

Everything in this repository is read by people who were never in the room. Use plain words. Do not use private shorthand, internal ids, or names of the owner's other projects. No client or person is named except the owner, Chad Wallace. No file path points into anyone's machine. If a sentence only makes sense to someone who was there, rewrite it or leave it out.

## Two folders

- **This repository** is public-bound. Everything in it is written for a stranger.
- **`../stringline-private`**, beside it, holds the owner's words, the working notes, review reports and the private close of each session. It is never inside this repository. Nothing moves from it into this one without being rewritten for a stranger. Name it only as `../stringline-private`. If you are working on the owner's machine, read `../stringline-private/OPEN-LOCAL.md` when a session opens. It holds the local setup this repository cannot.

## Before every push

- Scan every changed file and every commit message against the private word list in `../stringline-private` (`python3 ../stringline-private/guard/scan.py --files <files>`, and `--stdin` for a message).
- The local pre-push hook runs the same scan over everything being pushed and refuses the push on any hit. It is local, never committed, so a fresh clone does not have it. Do not push from a clone without it, and never skip it.
- Never change this repository's visibility. Making it public is the owner's act.

## How to work

- Stage and commit by path, in one motion. Never commit everything.
- Say what you looked at and what you compared against. When you cannot see something, say "can't tell", never "clean".
- A check is not trusted until it has been shown to fire on the fault it guards against.
- The record says who did what: the owner directs and reviews; the agent writes the implementation.
- Every page of the manual, and every file here, fits on one screen.
