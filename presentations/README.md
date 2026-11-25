# Browser walkthroughs

Open [index.html](index.html) directly in Chrome, Firefox or Safari.
No server, installation or internet connection is required to present.
GitHub sources need network access and may require repository access.

## Share online

The GitHub Pages workflow publishes only the three generated HTML files:

- [Launcher](https://brocksinet.github.io/shopware-db-independent/)
- [Architecture](https://brocksinet.github.io/shopware-db-independent/architecture.html)
- [Code and core findings](https://brocksinet.github.io/shopware-db-independent/core-findings.html)

Pushing changes to these files on `main` republishes the site. The workflow can also be run manually from GitHub Actions. No Python build runs during deployment: rebuild locally and commit the generated HTML with source changes.

- [Story and architecture](architecture.html): 15 slides, about 20–25 minutes. Starts where the video ended, explains reads at 150,000 products, then database boundaries and core decisions.
- [Code and core findings](core-findings.html): 25 slides. A reference organized by OpenSearch (2–8), DAL performance and write semantics (9–16), then PostgreSQL and cross-engine correctness (17–25). Choose a chapter for a live review.

The architecture deck carries the motivation, headline comparisons and measurement method. The engineering deck carries the implementation, reproductions and detailed fixes. Related slides link between decks.

Each deck embeds its styles, navigation and excerpts, so either HTML file can be copied on its own. Keep the launcher and both decks together for cross-deck links.

## Controls

| Key | Action |
| --- | --- |
| Right arrow, Space, Page Down | Next slide |
| Left arrow, Page Up | Previous slide |
| H | Cycle code highlights |
| N | Toggle notes and elapsed timer |
| S | Toggle the current slide’s source links |
| O | Toggle slide picker |
| 1 | Return to slide 1, including from the picker |
| F | Toggle fullscreen |
| Home, End | First or last slide |
| ? | Keyboard help |
| Escape | Close panels |

Click the bar below a code excerpt to cycle its highlights. Both covers have clickable chapter agendas. The footer separates Decks (launcher), Start (slide 1) and Slides (picker). Named links such as `core-findings.html#batch-tests` remain stable when slides move. Earlier named links to merged slides are retained as aliases; benchmark and method links now lead into the architecture deck.

Browser printing includes every slide and removes code dimming. Speaker notes appear in the same window, so close them before sharing the whole window.

## Rehearsal

1. Start with the architecture deck’s bridge after the video.
2. Pick one engineering chapter and rehearse its source and highlight steps.
3. Open S on a code slide to check repository access before sharing.
4. Return with 1 to choose another chapter.

The source-hydration prototype keeps existing OpenSearch queries and hydrates product documents from `_source`, with counted SQL fallback. It is behind a feature flag. Cache visibility, write guards and payload budgets remain production work.

Current headline comparisons use the paired timing research: 10 alternating rounds and 95% bootstrap intervals on one host. Projection’s 5k listing result uses the later paired 10.82-to-4.77 ms comparison. Batching uses the post-review final-code rerun: 27 statements on MySQL, MariaDB and SQLite; 29 on PostgreSQL. Its 7 tests / 19 assertions passed on each engine. That recorded rerun is a separate protocol from the paired confidence intervals.

Large source-size estimates remain labeled as subset extrapolations. PostgreSQL suite progress is not an all-green or supported-release claim. Issue URLs reflect recorded status; the read-store epic remains a draft.

## Sources and rebuilding

Edit content in `build.py`, styles in `deck.css` and controls in `deck.js`, then run:

```sh
python3 presentations/build.py
```

The builder needs only Python’s standard library and Git, with the research repository and `instance/` source commits available. It assembles milestone evidence and selects the two topic-based narratives in `present_by_topic()`. The launcher is hand-authored.

`sources.json` records the displayed excerpts, line ranges, focus groups and per-slide links. The documentation snapshot is `ce36f6c` (25 November 2026). Source hydration uses `0ed724decae`, standalone-store examples use `91b22d0abbb`, and earlier DAL excerpts retain `c8c6866ac19`. The final batching tests use `46a47f1a7c9`, which includes the repeated-unchanged-key guard. Switching branches does not silently change excerpts.

[REVIEW.md](REVIEW.md) retains the original review and a resolution map to the revised decks. Current browser previews are in `previews/`.
