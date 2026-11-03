# Launch kit

Drafts for the launch. **Nothing is posted, sent, uploaded or made public without John.**

| File | What |
|---|---|
| [hacker-news.md](hacker-news.md) | Title options and the author's first comment |
| [reddit.md](reddit.md) | r/dataisbeautiful (small multiples, [OC]) and r/wikipedia |
| [wikimedia-research.md](wikimedia-research.md) | Optional advance note to Wikimedia Research, the wiki-research-l post, and a Research Showcase pitch |
| [press.md](press.md) | Pitches to Press Gazette, Nieman Lab and Search Engine Land |
| [social.md](social.md) | LinkedIn post, a 6-post Bluesky thread and a 3-post X thread with two charts |
| [reviewer-questions.md](reviewer-questions.md) | 15 likely questions with short answers |

`tests/test_launch.py` checks the platform length limits and that every number in the drafts matches the pipeline.

## Checklist, in order

**A week before**
1. Read the article, the README and these drafts once more, in a browser.
2. Optional: send the advance note to Wikimedia Research ([wikimedia-research.md](wikimedia-research.md)) and allow a few days for corrections.
3. Decide on the dataset: upload `make release` output to Hugging Face (needs your account; the card is [docs/dataset-card.md](../dataset-card.md)), or leave the README pointing at the card. If you upload, add the dataset URL to the README's "Dataset" row.

**Launch day**
4. Check the repository for anything that shouldn't be public (`git log` and a scan for credentials: `WAO_BOT_USER`/`WAO_BOT_PASS` live only in your shell, never in the repo).
5. Make the GitHub repository public: Settings → General → Danger Zone → Change visibility.
6. Turn on Pages: Settings → Pages → Source: **GitHub Actions**. Then run the `pages` workflow (Actions → pages → Run workflow). Check https://johnpospisil.github.io/wikipedia-ai-overviews/. There is no app: P31 was skipped.
7. Post to Hacker News (weekday, 8–10 am US Eastern), then add the first comment.
8. Same day: the Bluesky and X threads, and LinkedIn. Morning of launch day or the next: the three press pitches.
9. Next day or two: wiki-research-l, then r/dataisbeautiful and r/wikipedia (not on the same day as each other).
10. Answer comments for the first day or two; [reviewer-questions.md](reviewer-questions.md) has the short answers.

**After**
11. A week or more later, and only if the Research Showcase has resumed: the Showcase pitch.
12. Log corrections that come in as dated Deviations in PREREGISTRATION.md or notes in DATA.md, never as silent edits.
