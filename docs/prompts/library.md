# Everyday prompt library

Reusable prompts for any week. Paste, then fill the angle brackets.

## Start of day
```text
Read CLAUDE.md, git log for the last 2 days, and docs/prompts/week-<n>.md. Tell me which prompts from this
week are done (based on code and tests present), which are in progress, and what to do next. Do not write code.
```

## Before starting a prompt
```text
Before planning <prompt id>, list the files you need to read, the existing code you will reuse, and any
conflict with CLAUDE.md or earlier decisions in docs/adr/. Ask me anything ambiguous.
```

## Write tests first
```text
For <feature>, write only the tests first: unit tests for the logic and an integration test against
testcontainers. Make them fail for the right reason. Show me before implementing.
```

## Code review of your own change
```text
/review <area or prompt id>
```

## Understand unfamiliar code
```text
Explain <file or module> as if I will maintain it alone: what it does, the data it reads and writes, the
failure modes, and the 3 places a bug is most likely. Point to file:line.
```

## Refactor safely
```text
Refactor <target> for <reason>. Keep behaviour identical: run the full test suite before and after, no public
API changes, and show the diff in small steps.
```

## Performance problem
```text
<endpoint or task> is slow (<numbers>). Profile it (py-spy or cProfile for Python, explain() for MongoDB
queries), show the top 3 costs with evidence, and propose fixes ranked by impact and risk. No changes yet.
```

## Database query or index
```text
Write the MongoDB query/aggregation for <need>, tenant-scoped through the repo, with the index it needs added
to indexes.py. Show explain() output on test data and a test proving tenant isolation.
```

## UI from the design
```text
Build <component/page> matching docs/design/<file>.png and docs/design/source/<file>.dc.html, using only the
components in apps/web/src/design and labels from useLabels(). List any visual differences you could not match.
```

## Write an ADR
```text
Write docs/adr/<NNNN>-<title>.md for the decision <decision>: context, options considered, decision,
consequences, how to revisit. Under 1 page.
```

## End of day
```text
Summarise today's changes from git diff/log into docs/changelog.md (date, prompt ids, what changed, what is
left), and list tomorrow's first task.
```

## When Claude Code is going in circles
```text
Stop. Summarise what you tried, what failed and the exact error. Propose 2 different approaches with trade-offs.
Wait for me to choose.
```
