# Opus 5.5 effort A/B (+ Fable 5.1 xhigh) on EQ-Bench Creative Writing v3

| effort | stories | rubric 0-20 (Opus 5 judge) | est. board Elo | avg length | avg output tokens | avg secs | slop |
|---|---|---|---|---|---|---|---|
| medium | 96 | 15.60 (96) | 2051 | 6090 ch | 3089 | 43 | 10.68 |
| high | 96 | 15.81 (96) | 2092 | 5994 ch | 4303 | 55 | 9.68 |
| xhigh | 96 | 16.24 (96) | 2263 | 5790 ch | 8770 | 97 | 9.34 |
| fable-xhigh | 96 | 16.34 (96) | 2293 | 5663 ch | 7179 | 109 | 7.58 |

## Head to head (both orders, 9 criteria each, margins 1-5)

| pair | criteria won | margin-weighted share |
|---|---|---|
| medium vs high | medium 747/1728 (43%) | medium 43% |
| medium vs xhigh | medium 455/1728 (26%) | medium 23% |
| medium vs fable-xhigh | medium 454/1728 (26%) | medium 22% |
| high vs xhigh | high 537/1728 (31%) | high 27% |
| high vs fable-xhigh | high 444/1728 (26%) | high 22% |
| xhigh vs fable-xhigh | xhigh 797/1728 (46%) | xhigh 45% |

Est. board Elo anchors medium at 2050.9 (Opus 5.5's board score, run at the API default effort, medium) and places high/xhigh by their head-to-head against it. The rubric judge differs from the site's (Opus 5 low instead of GLM 5.3 low), so compare the rubric column between rows, not with the board.

Board reference (eqbench.com, run at each model's API default effort): claude-opus-5-5 2050.9 (medium), claude-fable-5-1 2155.3 (high), top entry gpt-6-astra 2176.9.