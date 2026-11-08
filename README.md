# Does more thinking make Claude a better writer? EQ-Bench Creative Writing v3 by effort level

An independent rerun of [EQ-Bench Creative Writing v3](https://eqbench.com/creative_writing.html)
([code](https://github.com/EQ-bench/creative-writing-bench)) on **Claude Opus 5.5 at three effort levels**
(medium, high, xhigh) and **Claude Fable 5.1 at xhigh**. It uses the same 32 prompts × 3 seed modifiers = 96 stories
per contender, 384 stories in all, plus every judge output. Run on 2026-11-08.

The public leaderboard runs each model at its API default effort. For Opus 5.5 that default is **medium**, so
the board's `claude-opus-5-5` (Elo 2050.9) is the medium run. Our medium run's slop score (10.68) matches the
board's (10.43).

## Results

| contender | est. board Elo | rubric 0-20 | stories won vs Opus medium | avg output tokens (incl. thinking) | avg secs | slop (lower = better) |
|---|---|---|---|---|---|---|
| Opus 5.5 medium (= board default) | 2051 (anchor) | 15.60 | — | 3,089 | 43 | 10.68 |
| Opus 5.5 high | ~2092 | 15.81 | 58 / 96 | 4,303 | 55 | 9.68 |
| Opus 5.5 xhigh | ~2263 | 16.24 | 79 / 96 | 8,770 | 97 | 9.34 |
| **Fable 5.1 xhigh** | **~2293** | **16.34** | 80 / 96 | 7,179 | 109 | **7.58** |

For reference, on the board (default effort): Fable 5.1 = 2155.3 (its default is high), top entry gpt-6-astra = 2176.9.

Head to head (pairwise judge, both orders, 9 criteria × 1–5 margin):

| pair | share of margin won by the first | 95% CI (bootstrap over stories) | stories won by the second |
|---|---|---|---|
| medium vs high | 43% | 35–50% | 58 / 96 |
| medium vs xhigh | 23% | 18–28% | 79 / 96 |
| high vs xhigh | 27% | 22–32% | 75 / 96 |
| medium vs Fable xhigh | 22% | 18–26% | 80 / 96 |
| high vs Fable xhigh | 22% | 18–27% | 82 / 96 |
| Opus xhigh vs Fable xhigh | 45% | 40–52% | 49 / 96 |

**Takeaways**
- high is only slightly better than medium; the confidence interval nearly touches a tie.
- xhigh is a large, clear step up: about 2.8× the output tokens of medium, and it beats medium on ~4 of 5 stories.
- Fable 5.1 xhigh and Opus 5.5 xhigh are close to even (Fable slightly ahead, CI crosses 50%). Fable writes with clearly less slop.
- "est. board Elo" fixes medium at the board's 2050.9 and places the others by their margin-weighted head-to-head
  (Bradley-Terry, each "+" counted as a win). It is an estimate, not an official score.

## How it was run, and how it differs from the official harness

All calls went through the Claude Code CLI (`claude -p`, no tools, no MCP, no settings) on a Claude subscription:

| | official | this run |
|---|---|---|
| writer | API, temp 0.7, min_p 0.1, no system prompt | `--model claude-opus-5-5` / `claude-fable-5-1`, `--effort medium/high/xhigh`; sampling params can't be set on these models; system prompt `You are Claude.` (the CLI rejects a blank one) |
| rubric judge | GLM 5.3, low reasoning | **Claude Opus 5, effort low**, the repo's own judging prompt and 22 criteria, negative criteria inverted |
| pairwise judge | Claude Opus 5 | Claude Opus 5, effort high, the repo's pairwise prompt, both orders, 4,000-char truncation |
| pairwise prompt | asks for a `chain_of_thought_reasoning` field | the field is renamed `analysis`, because Opus 5's safeguards refused the original wording |
| Elo | Glicko-style vs the whole field | Bradley-Terry among these 4 only, anchored as above |

Because the rubric judge is different, compare the rubric column between rows here, not with the board.

**Known incidents.** Two Opus stories were cut off by Anthropic's safety classifier mid-generation, and the model
replied with a short apology instead (medium, prompt 29 "Biopunk", iteration 1; high, prompt 10 "Hacker Mindset",
iteration 1). They are kept as generated and scored as written. The official harness only retries answers under
500 characters; these were longer. Fable had none.

## Files

- `data/stories.jsonl`: one line per story: `arm, model, effort, prompt_id, iteration, prompt, response, seconds, output_tokens, thinking_tokens`
- `data/rubric.jsonl`: rubric scores per story (`scores` per criterion, `piece_score_0_20`), plus the judge's full analysis
- `data/pairwise.jsonl`: every pairwise judgment (`writer_A0493` / `writer_A0488` = the two arms in that order), per-criterion winner and margin, plus the full judge output
- `report.md` / `report.json`: the summary table
- `effort_ab.py`: the runner. Drop it into a clone of [EQ-bench/creative-writing-bench](https://github.com/EQ-bench/creative-writing-bench) (it uses that repo's `data/` and `core/`) and run `python effort_ab.py all`. It resumes where it stopped.

Prompts and judging prompts are from EQ-Bench Creative Writing v3 by Sam Paech.

## License

Data (`data/`, `report.*`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Code (`effort_ab.py`): MIT.
