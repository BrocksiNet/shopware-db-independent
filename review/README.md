# review

Git worktrees of `../instance`, one folder per branch or pull request that is
compared against the proof-of-concept branch.

```bash
cd ../instance
git fetch origin pull/17858/head:pr-17858
git worktree add ../review/pr-17858 pr-17858
```
