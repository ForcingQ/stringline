# Fixture: lines that are not items

<!-- done-list cap=3 timeout=10 -->
1. **POINTABLE** — a good line · check: `true`
- a bullet
2) **POINTABLE** — a bracket after the number · check: `true`
 3. **POINTABLE** — a leading space · check: `true`
Prose, written where an item should be.
4. **MAYBE** — a tag that is not one of the five
5. **POINTABLE** — a POINTABLE with no command
1. **UNSORTED** — a repeated item number
6. **POINTABLE** - a hyphen where the dash goes · check: `true`
<!-- /done-list -->
