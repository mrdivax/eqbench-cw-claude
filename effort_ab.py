"""EQ-Bench Creative Writing v3: Opus 5.5 at medium (API default) vs high vs xhigh.

Everything runs through the claude CLI on the subscription (no OpenRouter, no API key).
  writer : claude-opus-5-5 at --effort medium | high | xhigh, no system prompt content, no tools
  rubric : claude-opus-5 at --effort low, the repo's judging prompt + 22 criteria (site: GLM 5.3 low)
  pairs  : claude-opus-5, the repo's pairwise prompt, both orders, 4,000-char truncation (site: Opus 5)

Resume-safe: every call is one JSON file under runs/; rerun the same command to continue.
  python effort_ab.py smoke          one story per level + judge calls, to check the pipeline
  python effort_ab.py all            generate -> rubric -> pairwise -> report
  python effort_ab.py report         rebuild report.md from what exists
"""
import json, math, os, random, re, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core.scoring import parse_judge_scores_creative  # noqa: E402

RUNS = ROOT / "runs"
WRITER = "claude-opus-5-5"
# arm name -> (writer model, effort). The plain names are Opus 5.5; added arms keep their own model.
ARMS = {"medium": (WRITER, "medium"), "high": (WRITER, "high"), "xhigh": (WRITER, "xhigh"),
        "fable-xhigh": ("claude-fable-5-1", "xhigh"),
        "argon-high": ("gemini-4-argon-high", "acp")}  # effort "acp" = Antigravity ACP (T3's Gemini provider)
LEVELS = list(ARMS)
JUDGE = "claude-opus-5"
ITERATIONS = 3
WORKERS = int(os.environ.get("AB_WORKERS", "4"))
TRUNC = 4000
SITE_ELO_MEDIUM = 2050.9  # claude-opus-5-5 on the board (API default effort = medium)

CLAUDE = shutil.which("claude") or "claude"
BASE = [CLAUDE, "-p", "--no-session-persistence", "--tools", "", "--setting-sources", "",
        "--strict-mcp-config", "--disable-slash-commands", "--output-format", "json"]

PROMPTS = json.loads((ROOT / "data/creative_writing_prompts_v3.json").read_text(encoding="utf-8"))
JUDGE_TPL = (ROOT / "data/creative_writing_judging_prompt.txt").read_text(encoding="utf-8")
CRITERIA = [l.strip() for l in (ROOT / "data/creative_writing_criteria.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
NEGATIVE = [l.strip() for l in (ROOT / "data/negative_criteria.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
PAIR_TPL = (ROOT / "data/pairwise_prompt.txt").read_text(encoding="utf-8")
# Opus 5's safeguards refuse a request for its "chain of thought reasoning"; same field, neutral name.
PAIR_TPL = PAIR_TPL.replace('"chain_of_thought_reasoning": "detailed chain of thought reasoning about the coming scoring decisions"',
                            '"analysis": "detailed critical analysis supporting the scoring decisions"')
assert '"analysis"' in PAIR_TPL
PAIR_KEYS = ["character_authenticity_insight", "interesting_original", "writing_quality", "coherence",
             "instruction_following", "world_and_atmosphere", "avoids_cliches", "avoids_verbosity",
             "avoids_poetic_overload"]


def items():
    for pid, p in PROMPTS.items():
        for i in range(1, ITERATIONS + 1):
            seed = p["seed_modifiers"][(i - 1) % len(p["seed_modifiers"])]
            yield pid, i, p["writing_prompt"].replace("<SEED>", seed)


def call(model, effort, system, prompt, timeout=1800):
    if effort == "acp":
        import acp_writer
        return acp_writer.write(model, prompt)
    cmd = BASE + ["--model", model, "--effort", effort, "--system-prompt", system]
    t = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        d = json.loads(p.stdout)
    except Exception:
        raise RuntimeError(f"bad CLI output rc={p.returncode}: {p.stdout[-400:]} {p.stderr[-400:]}")
    if d.get("is_error") or not d.get("result"):
        raise RuntimeError(f"CLI error: {str(d)[:400]}")
    return {"text": d["result"], "secs": round(time.time() - t, 1), "usage": d.get("usage"),
            "modelUsage": d.get("modelUsage"), "cost_equiv_usd": d.get("total_cost_usd")}


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ---------- jobs ----------
WRITER_SYSTEM = "You are Claude."  # the site sends none; the CLI needs a non-blank one, so it is minimal


def gen_job(level, pid, i, prompt):
    out = RUNS / "gen" / level / f"{pid}_{i}.json"
    if out.exists():
        return None
    for attempt in range(3):
        r = call(ARMS[level][0], ARMS[level][1], WRITER_SYSTEM, prompt)
        if len(r["text"].strip()) >= 500:  # the repo retries short answers too
            break
    r.update(level=level, model=ARMS[level][0], effort=ARMS[level][1], pid=pid, iter=i, prompt=prompt)
    save(out, r)
    return f"gen {level} {pid}_{i} {len(r['text'])}ch {r['secs']}s"


def rubric_job(level, pid, i, prompt):
    out = RUNS / "rubric" / level / f"{pid}_{i}.json"
    g = load(RUNS / "gen" / level / f"{pid}_{i}.json")
    if out.exists() or not g:
        return None
    jp = (JUDGE_TPL.replace("{writing_prompt}", prompt).replace("{test_model_response}", g["text"])
          .replace("{lower_is_better_criteria}", ", ".join(NEGATIVE))
          .replace("{creative_writing_criteria}", "\n".join(CRITERIA)))
    for attempt in range(3):
        r = call(JUDGE, "low", "You are an expert creative writing judge.", jp)
        scores = {k: v for k, v in parse_judge_scores_creative(r["text"]).items() if k in CRITERIA}
        if len(scores) >= 15:
            break
    save(out, {"scores": scores, "raw": r["text"], "secs": r["secs"]})
    return f"rubric {level} {pid}_{i} {len(scores)} scores"


def parse_pair(text):
    m = re.search(r"\{.*\}", text, re.S)
    d = json.loads(m.group(0))
    res = {}
    for k in PAIR_KEYS:
        v = str(d.get(k, ""))
        w = re.search(r"A0(493|488)\s*(\++)", v)
        if w:
            res[k] = ("A" if w.group(1) == "493" else "B", len(w.group(2)))
    return res


def pair_job(la, lb, pid, i, prompt):
    """la written as writer A0493, lb as A0488."""
    out = RUNS / "pairs" / f"{la}__{lb}" / f"{pid}_{i}.json"
    ga, gb = load(RUNS / "gen" / la / f"{pid}_{i}.json"), load(RUNS / "gen" / lb / f"{pid}_{i}.json")
    if out.exists() or not ga or not gb:
        return None
    jp = (PAIR_TPL.replace("{writing_prompt}", prompt).replace("{model_a_analysis}", ga["text"][:TRUNC])
          .replace("{model_b_analysis}", gb["text"][:TRUNC]))
    for attempt in range(3):
        r = call(JUDGE, "high", "You are an expert creative writing judge.", jp)
        try:
            res = parse_pair(r["text"])
            if len(res) >= 7:
                break
        except Exception:
            res = {}
    save(out, {"a": la, "b": lb, "result": res, "raw": r["text"], "secs": r["secs"]})
    return f"pair {la} vs {lb} {pid}_{i} {len(res)} crit"


def run_pool(jobs, label):
    jobs = list(jobs)
    print(f"== {label}: {len(jobs)} jobs, {WORKERS} workers", flush=True)
    done = fail = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = {ex.submit(f, *a): a for f, a in jobs}
        for fu in as_completed(futs):
            try:
                msg = fu.result()
                done += 1
                if msg:
                    print(f"[{done}/{len(jobs)}] {msg}", flush=True)
            except Exception as e:
                fail += 1
                print(f"FAIL {futs[fu][:3]}: {e}", flush=True)
    print(f"== {label} finished, {fail} failed (rerun to retry)", flush=True)


def phase_jobs(sel):
    its = list(sel)
    gen = [(gen_job, (lv, pid, i, pr)) for pid, i, pr in its for lv in LEVELS]
    rub = [(rubric_job, (lv, pid, i, pr)) for pid, i, pr in its for lv in LEVELS]
    pairs = [(pair_job, (a, b, pid, i, pr)) for pid, i, pr in its
             for x, y in combinations(LEVELS, 2) for a, b in ((x, y), (y, x))]
    return gen, rub, pairs


# ---------- report ----------
def piece_score(scores):
    vals = [(20 - v if k in NEGATIVE else v) for k, v in scores.items()]
    return sum(vals) / len(vals) if vals else None


def report():
    from core.metrics import calculate_slop_index_new
    lines = ["# Opus 5.5 effort A/B (+ Fable 5.1 xhigh) on EQ-Bench Creative Writing v3", ""]
    rows = []
    for lv in LEVELS:
        gens = [load(p) for p in sorted((RUNS / "gen" / lv).glob("*.json"))]
        rubs = [load(p) for p in sorted((RUNS / "rubric" / lv).glob("*.json"))]
        ps = [s for s in (piece_score(r["scores"]) for r in rubs) if s is not None]
        text = "\n\n".join(g["text"] for g in gens)
        try:
            slop = calculate_slop_index_new(text, debug=False) if text else None
        except Exception:
            slop = None
        rows.append(dict(level=lv, n=len(gens), rubric=(sum(ps) / len(ps) if ps else None), nr=len(ps),
                         chars=(sum(len(g["text"]) for g in gens) / len(gens) if gens else None),
                         secs=(sum(g["secs"] for g in gens) / len(gens) if gens else None),
                         out_tok=(sum((g.get("usage") or {}).get("output_tokens", 0) for g in gens) / len(gens) if gens else None),
                         slop=slop))
    # pairwise: per level pair, share of criteria won and margin-weighted share
    wins = {}
    for d in (RUNS / "pairs").glob("*__*"):
        for p in d.glob("*.json"):
            j = load(p)
            for k, (w, m) in j["result"].items():
                winner, loser = (j["a"], j["b"]) if w == "A" else (j["b"], j["a"])
                wins.setdefault(frozenset((j["a"], j["b"])), []).append((winner, m))
    # Bradley-Terry on margin-weighted wins (each "+" counts as one win, like the site's margin weighting)
    W = {(x, y): 0.0 for x in LEVELS for y in LEVELS if x != y}
    for pair, lst in wins.items():
        x, y = tuple(pair)
        for winner, m in lst:
            loser = y if winner == x else x
            W[(winner, loser)] += m
    strength = {lv: 1.0 for lv in LEVELS}
    for _ in range(500):
        for lv in LEVELS:
            num = sum(W[(lv, o)] for o in LEVELS if o != lv)
            den = sum((W[(lv, o)] + W[(o, lv)]) / (strength[lv] + strength[o]) for o in LEVELS if o != lv)
            if den > 0 and num > 0:
                strength[lv] = num / den
        g = math.exp(sum(math.log(s) for s in strength.values()) / len(strength))
        strength = {k: v / g for k, v in strength.items()}
    elo = {lv: SITE_ELO_MEDIUM + 400 * math.log10(strength[lv] / strength["medium"]) for lv in LEVELS}

    lines += ["| effort | stories | rubric 0-20 (Opus 5 judge) | est. board Elo | avg length | avg output tokens | avg secs | slop |",
              "|---|---|---|---|---|---|---|---|"]
    f = lambda v, d=2: "-" if v is None else f"{v:.{d}f}"
    for r in rows:
        lines.append(f"| {r['level']} | {r['n']} | {f(r['rubric'])} ({r['nr']}) | {f(elo[r['level']],0)} | {f(r['chars'],0)} ch | "
                     f"{f(r['out_tok'],0)} | {f(r['secs'],0)} | {f(r['slop'])} |")
    lines += ["", "## Head to head (both orders, 9 criteria each, margins 1-5)", "",
              "| pair | criteria won | margin-weighted share |", "|---|---|---|"]
    for x, y in combinations(LEVELS, 2):
        lst = wins.get(frozenset((x, y)), [])
        if not lst:
            continue
        nx = sum(1 for w, _ in lst if w == x)
        mx = sum(m for w, m in lst if w == x)
        mt = sum(m for _, m in lst)
        lines.append(f"| {x} vs {y} | {x} {nx}/{len(lst)} ({100*nx/len(lst):.0f}%) | {x} {100*mx/mt:.0f}% |")
    lines += ["", f"Est. board Elo anchors medium at {SITE_ELO_MEDIUM} (Opus 5.5's board score, run at the API default "
              "effort, medium) and places high/xhigh by their head-to-head against it. The rubric judge differs from "
              "the site's (Opus 5 low instead of GLM 5.3 low), so compare the rubric column between rows, not with the board.",
              "", "Board reference (eqbench.com, run at each model's API default effort): claude-opus-5-5 2050.9 (medium), "
              "claude-fable-5-1 2155.3 (high), top entry gpt-6-astra 2176.9."]
    (ROOT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    json.dump({"rows": rows, "elo": elo}, open(ROOT / "report.json", "w"), indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "smoke":
        RUNS = ROOT / "runs_smoke"
        sel = [next(items())]
        g, r, p = phase_jobs(sel)
        run_pool(g, "generate"); run_pool(r, "rubric"); run_pool(p[:2], "pairwise")
        for lv in LEVELS:
            d = load(RUNS / "gen" / lv / f"{sel[0][0]}_{sel[0][1]}.json")
            if d:
                print(lv, len(d["text"]), "chars", d["secs"], "s", d.get("usage"), "\n", d["text"][:300].replace("\n", " "), "\n")
        for p_ in (RUNS / "rubric").rglob("*.json"):
            print(p_, load(p_)["scores"])
        for p_ in (RUNS / "pairs").rglob("*.json"):
            print(p_, load(p_)["result"])
    elif cmd == "report":
        report()
    else:
        g, r, p = phase_jobs(items())
        run_pool(g, "generate"); run_pool(r, "rubric"); run_pool(p, "pairwise")
        report()
