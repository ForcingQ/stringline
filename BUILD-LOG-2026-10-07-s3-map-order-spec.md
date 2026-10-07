## 2026-10-07 · map, order, spec (the third session) · 15:04 to about 18:45 *(start read; end estimated)*

AI model: Claude Fable 5.1, leading. The owner, Chad Wallace, was present and ruled throughout.

**What it did**
- Recorded the owner's four rulings before anything else. Two answered questions the second session had left open: one public file holds his typed lines that the intent quotes ([WORDS.txt](WORDS.txt)), and the private-word check stops a push while every other check reports ([DECISIONS.md](DECISIONS.md) #18, #19). One gave plain words for the two intent phrases a cold reader could not follow, applied in one commit (#17); he reworded one line, and the same commit was amended before any push. One kept a class of his private upkeep out of this log (#28).
- Measured both folders and the push check, read the whole public state and the private record, then wrote a finished list of 33 items and ran its checker before any work. His typed lines were in no file the session could read, so he pasted them; he also said yes to the same file holding the lines LEARNED.md quotes.
- Drew the map ([MAP.md](MAP.md)): three tracks, five tiers, three foundations (the manual's source schema, the run log, the typed lines), the arrows that cross tracks, three parts that are new here and not recreated, what is deferred and why, and a checkpoint between tiers.
- Wrote the specification: a front page ([SPEC.md](SPEC.md)) with the decisions that bind every part, and five parts, each one screen.
- Two reviewers, two rounds each, both on a stronger model than the readers of the second session. A reader briefed to disagree read the map, the spec and the lane briefs against what the second session measured, and reported where a builder who was not present would have to guess. A dry-run reviewer executed every self-test design on fixtures, with throwaway code, before anything was built: in round 1 five of the eight designs were broken as written and three underspecified; in round 2 one was broken again, the rest underspecified or sound. Every finding was taken in place or declined with its reason in the private record. The dry-run reviewer also ran the spec's own rule over the owner's eight quotes: three exact, five corrected, none absent.
- Wrote the three briefs for the next session's build lanes, each with its own finished list, each lane in its own copy of the repository, with the order merges must take.
- The owner approved the map and the spec, with one line for the record: the map's section placing four later additions arrived after both review rounds, so it is approved as placement only and the next session's rounds review it. He also ruled that setting a tool's card to released waits for his word, and placed the four additions (#33).

**Smaller decisions**
- The spec is a front page and five part files, and the map is public, because every file here fits on one screen and both are about the build. The lane briefs stay private: they carry paths into the owner's machine.
- No separate package is specified for the pattern this build recreates (#26). The public copy of the private-word check is a check, not a tool (#31). Code files are not bound by the one-screen rule (#27). Merges never rewrite history (#30).
- Every close now appends the owner's typed learning to WORDS.txt after LEARNED.md is written, so the quote checker tests each session's transcription of his words (#32). This close did it first.
- Whether the repository's automated workflow is enabled was measured, not asked: it is.

**Wrong turns, caught**
1. The spec's own rule for finding quotes read two lines of the spec itself as quotes, one as a catch and one as unreadable. Both reviewers found it; the lead measured ten quotes without the fix and eight with it. Quotes inside code are now excluded.
2. The first rule for a "corrected" quote let a misquote through three ways: an omission mark skipping a single word, a flipped negation, a changed first or last word. The dry-run reviewer built each. Fixed, and the record then called one of them closed when it was not: in round 2 the same splice, skipping three words that included "not", still read exact. Fixed again: a skipped or changed negation is always a catch, and an added word is never a correction.
3. Before any code existed, the dry-run reviewer showed a self-test design that could write a real run, a currency stamp that would stay green forever, a renderer that erased a hand edit and read green, and a word check red on its own list. Each is fixed in the spec.
4. The lead's brief told a read-only reviewer to write its report to a file. It could not, and sent the report as a message; the lead landed it unchanged.
5. One line of a lane's finished list passed before any tool existed, because a missing script exits with the same code as "can't check". Tightened to require the words.
6. The private-word scan refused once because the lead's shell passed fourteen file names as one (a slip the second session's private record also carries); and a record line in the private notes claimed a commit before it existed, since new files must be staged first. Both are corrected in the private record, below the lines they correct.
7. The dry-run reviewer's own slip, reported by itself: a fixture copied into an existing system folder, whose modified time changed, and seven temporary folders it made and removed. Nothing in either repository was touched.

**Kept private:** 2 items of upkeep in the owner's other work, not about this build: a row in the log he keeps for the finished-list method, added after this close's review (1); the summary page of his methodology notes, out of date since before the founding and not this build's to fix (1).

**Next:** a short session (S3b) specifies the four placed additions with the same two reviewers; then the build (S4) opens the lanes in the map's merge order.

**Corrections after the closing review · 2026-10-07 18:25:04 *(read)*.** A separate agent checked this entry against the private notes, both ways. Nothing above was edited.
- C1. Wrong turn 6 said both slips were corrected in the private record. The first one's record line, and the line recording the owner's approval, had never been written: both sat in a shell command after a step that failed, and the command stopped before them. Both are now in the record, dated after the review, with their content as first written.
- C2. The owner's ruling placing four later additions on the map had no line of its own in the private record; it has one now.
- C3. The kept-private count was 2 and is 5: the item about the owner's reading limit is counted, as his ruling requires, and two items owed from earlier sessions to his other work are counted again, since an owed item is counted each session it stays owed.
- C4. Missing: a cold reader, given only this repository, read the final text and asked whether the specification alone would let them build the first tool. Mostly yes, with guesses; each guess got its sentence in the specification. It also found words a stranger could not follow, now replaced in every public file, and one gap between two specification parts (two flags one part expected and the other never listed), now closed. Those edits are in this session's closing commit.
- C5. Four design decisions (typed records, English, the run log's shape, plain-text input) carry their reasons in the specification parts and had no line of their own in the private record; they have one now.
