# SPEC · the card: one per tool

**Ground truth.** One earlier manual of the owner's has a typed card with seven fields, among them *what it is*, *the first thing to do* and *the one gotcha*; its fourth field is about money, which belongs to that product. No card anywhere says what its tool has caught. A card there does not wait for its tool to ship. The intent asks for one card per released tool, with the four fields below.

**In.** The card record's shape, its rendering rule, and the derivation of its fourth field. **Out.** The card's look. **Deferred.** A check that a card's words match what the tool does (no original has one; named as a gap, not promised).

## The record: `manual/tools/<id>.toml`

| Key | Type | Meaning |
|---|---|---|
| `id` | string | the file name without `.toml`, and the tool's folder name under `tools/` (lower case, hyphens); the tool's main file is `tools/<id>/<id with underscores>.py`; `fixture-tool` is reserved and red |
| `name` | string | the tool's plain name |
| `status` | `building` or `released` | released once its first real run is logged, the card read against the tool, and the owner's word given |
| `what` | string, one sentence | what it is, for a stranger |
| `first` | string | the first thing to do: one command, runnable as written from the repository root |
| `gotcha` | string, one sentence | the one thing that bites a first user |
| `earned_by` | string, one sentence | the failure that earned the tool; check 2 compares it to what the tool prints for `--earned-by` |
| `files` | array of paths | the tool's own files, the shared `tools/runlog.py` included if it uses it; the currency check watches them, and check 2 compares the list to what the tool prints for `--files` |
| `verified_against` | string, a commit id | the latest commit that touched `files` when the card was last read against the tool; the currency check ([SPEC-guard.md](SPEC-guard.md), check 1) compares it to the commits since |

**Not a key: "what it has caught".** It is derived at render time by `runlog.caught_line(tool)` from this tool's *real* rows, newest first, with each run's date; planted rows are never read for it. No readable real row: *no real run yet*. Real rows with nothing caught: *1 real run, nothing caught yet* or *n real runs, nothing caught yet*. Otherwise the caught lines, at most ten. Whenever a real run could not see everything, or a run file could not be read, the sentence says how many, so a blind read never shows as a clean one. *Why:* a typed field would drift from the log, and a count that included plants would call a plant a catch. The card may read *nothing caught yet* through release; a line that says so is the truth this field exists to tell.

## Rules, with reasons

- **A card exists for every tool folder under `tools/`, and every card has a folder**, at any status; the lane that builds a tool creates the folder, holding the tool's main file with its header (git cannot commit an empty folder), and a `building` card, as its first commit. While `building`, `files` and `verified_against` may be empty and the resolution check does not require them; at `released` both are required. *Why:* the two-way rule holds from the first commit without turning the check red for the whole building phase.
- **The site renders only `released` cards in the tools room**; `building` ones appear in the build room as "in progress", name only. *Why:* the intent says a card per released tool; the reader is not shown a tool they cannot run.
- **`first` is a command**, not advice. *Why:* a stranger installs it and runs it; the first thing to do is the thing that proves it works on their machine.
- **`verified_against` is moved by the session lead after reading the card against the tool, and `released` is set only on the owner's word** (his ruling of 7 October; it is on the list of what waits for his word in [OPEN-PROTOCOL.md](OPEN-PROTOCOL.md)). The card's own commit comes after the tool's and never touches the tool's `files`, so the stamp can name the tool's last commit; a commit that moves a stamp and changes the tool's files together is red by construction. *Why:* the currency check enforces re-reading, not truth; a released card is a public claim about a tool, and that claim is the owner's.
- **A change to the shared `tools/runlog.py` turns every card that lists it red together.** That is accepted and said here: a logging change is a change each card should be re-read against.

## Done when

- A fixture card with every key renders to a page; one with a key outside the list, and a released one whose `files` name a missing path, each make check 2 red naming the card; a `building` one with empty `files` does not.
- `caught_line` on fixture rows gives *no real run yet* (planted rows only), *1 real run, nothing caught yet* (one real row, empty `caught`), and the caught line (one real row with a `caught` entry), and refuses a row with no `kind` as can't tell.
- The first tool's card exists with `status = "building"` in the lane's first commit, and is read against the tool before `released`.
- A `building` card is absent from the rendered tools room and present in the build room.
