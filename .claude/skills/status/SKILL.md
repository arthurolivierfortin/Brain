---
name: status
description: Show project progress — current phase, open issues, recent PRs.
user-invocable: true
---

# Status

Show the current state of the Brain project.

## Instructions

### Step 1: Read STATUS.md

```bash
cat docs/STATUS.md
```

### Step 2: Current phase progress

Pick `R:phase-<N>` value from STATUS.md, then:

```bash
gh issue list --repo arthurolivierfortin/Brain --label "R:phase-<N>" --state open --json number,title,labels
gh issue list --repo arthurolivierfortin/Brain --label "R:phase-<N>" --state closed --json number
```

### Step 3: Recent activity

```bash
gh pr list --repo arthurolivierfortin/Brain --state all --limit 5 --json number,title,state,mergedAt
git log --oneline -10
```

### Step 4: Display summary

```
## Brain — Status

### Phase <N>: <title>
Progress: [====------] X/Y issues done

### Open Issues
- #N: <title> (todo/in-progress/in-review)

### Recent PRs
- #N: <title> (merged/open/closed)

### Next Steps
- <from STATUS.md>
```

## Rules

- Read-only — never modifies STATUS.md or any other file
- If `docs/STATUS.md` is missing or empty, point the user to the README roadmap
