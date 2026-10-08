# Fixture: a nested backtick in a command

<!-- done-list cap=3 timeout=10 -->
1. **POINTABLE** — nested · check: `echo `date``
2. **POINTABLE** — nesting written the way the spec allows · check: `test -n "$(echo x)"`
<!-- /done-list -->
