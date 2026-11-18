"""Run an eval suite: personas x scenarios x coach models, then score and report.

Outputs (in runs/<suite>-<timestamp>/):
  results.jsonl   one record per conversation (transcript, checks, judge scores, costs)
  summary.json    aggregate metrics per coach model
  summary.md      human-readable report
  transcripts.md  every conversation with its scores, for human review
"""

from __future__ import annotations

import hashlib
import json
import statistics as st
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..coach.coach import Coach
from ..config import DeliberationConfig
from ..corpus.index import MaterialIndex
from ..llm.registry import ModelRegistry
from ..sim.simulator import Scenario, SimPersona, Simulator, load_personas, load_scenarios
from .checks import ALL_FLAGS, check_turn
from .judge import Judge, load_rubrics


class Thresholds(BaseModel):
    min: dict[str, float] = Field(default_factory=dict)
    max: dict[str, float] = Field(default_factory=dict)


class Suite(BaseModel):
    name: str
    deliberation: str | None = None
    personas: list[str] | str = "all"
    scenarios: list[str] | str = "all"
    agenda_items: list[str] | str = "all"
    coach_profiles: list[str] = Field(default_factory=lambda: ["coach"])
    turns: int | None = None
    repeats: int = 1
    judge: bool = True
    max_workers: int = 4
    thresholds: Thresholds = Field(default_factory=Thresholds)

    @classmethod
    def load(cls, path: str | Path) -> tuple["Suite", Path]:
        p = Path(path)
        return cls(**yaml.safe_load(p.read_text(encoding="utf-8"))), p.parent.resolve()


def _select(items: list, wanted: list[str] | str, key: str = "id") -> list:
    if wanted == "all":
        return items
    by_id = {getattr(i, key): i for i in items}
    missing = [w for w in wanted if w not in by_id]
    if missing:
        raise ValueError(f"Unknown ids in suite: {missing}. Available: {sorted(by_id)}")
    return [by_id[w] for w in wanted]


def _pick_agenda(items: list[str | None], persona: SimPersona, scenario: Scenario, rep: int) -> str | None:
    # Mirrored twins hash on the same base id, so each pair sees the same agenda item.
    base = persona.mirror_of or persona.id
    h = int(hashlib.md5(f"{base}|{scenario.id}|{rep}".encode()).hexdigest(), 16)
    return items[h % len(items)] if items else None


class EvalRunner:
    def __init__(
        self,
        suite: Suite,
        config: DeliberationConfig,
        registry: ModelRegistry,
        out_root: str | Path = "runs",
        personas_path: str | Path | None = None,
        scenarios_path: str | Path | None = None,
        rubrics_path: str | Path | None = None,
        rebuild_index: bool = False,
        index: MaterialIndex | None = None,
    ):
        self.suite = suite
        self.config = config
        self.registry = registry
        self.out_root = Path(out_root)
        self.personas = _select(load_personas(personas_path), suite.personas)
        self.scenarios = _select(load_scenarios(scenarios_path), suite.scenarios)
        all_items = [a.id for a in config.agenda]
        self.agenda_items: list[str | None] = (
            all_items if suite.agenda_items == "all" else list(suite.agenda_items)
        ) or [None]
        self.rubrics = load_rubrics(rubrics_path)
        embedder = registry.client("embedder") if registry.has_role("embedder") else None
        # A prebuilt index (for example from database rows) skips loading files from disk.
        self.index = index or MaterialIndex.build(config, embedder=embedder, rebuild=rebuild_index)

    def plan(self) -> list[tuple[str, SimPersona, Scenario, int, str | None]]:
        jobs = []
        for prof in self.suite.coach_profiles:
            for persona in self.personas:
                for scenario in self.scenarios:
                    for rep in range(self.suite.repeats):
                        jobs.append((prof, persona, scenario, rep, _pick_agenda(self.agenda_items, persona, scenario, rep)))
        return jobs

    def run(self, log=print) -> tuple[Path, dict[str, Any], bool]:
        jobs = self.plan()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = self.out_root / f"{self.suite.name}-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        log(f"Running {len(jobs)} conversations -> {out}")

        sim_client = self.registry.client("participant_sim")
        judge = (
            Judge(self.registry.client("judge"), self.config, self.rubrics, self._chunk_text)
            if self.suite.judge
            else None
        )
        coaches = {
            prof: Coach(self.registry.client(prof), self.config, self.index) for prof in self.suite.coach_profiles
        }

        def work(job):
            prof, persona, scenario, rep, item = job
            sim = Simulator(coaches[prof], sim_client, self.config)
            run_id = f"{prof}|{persona.id}|{scenario.id}|{rep}"
            tr = sim.run(persona, scenario, item, run_id=run_id, turns=self.suite.turns)
            rec = tr.to_dict()
            rec["coach_profile"] = prof
            rec["scenario_brief"] = scenario.brief.replace("{agenda}", item or "the framing question").strip()
            rec["excerpts"] = {
                src["chunk_id"]: self._chunk_text(src["chunk_id"]) for t in tr.turns for src in t["coach"]["sources"]
            }
            rec["checks"] = [check_turn(t["coach"], persona.knowledge_level).to_dict() for t in tr.turns]
            rec["judge"] = None
            rec["cost_usd"]["judge"] = 0.0
            if judge and not tr.error:
                try:
                    scores, resp = judge.score(rec, rec["scenario_brief"])
                    rec["judge"] = scores
                    rec["cost_usd"]["judge"] = resp.cost_usd
                except Exception as exc:  # noqa: BLE001
                    rec["judge_error"] = f"{type(exc).__name__}: {exc}"
            return rec

        records: list[dict[str, Any]] = []
        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=max(1, self.suite.max_workers)) as pool:
            futures = [pool.submit(work, j) for j in jobs]
            for n, fut in enumerate(as_completed(futures), 1):
                rec = fut.result()
                records.append(rec)
                status = "ERROR " + rec["error"] if rec.get("error") else "ok"
                log(f"  [{n}/{len(jobs)}] {rec['run_id']}: {status}")
        records.sort(key=lambda r: r["run_id"])
        elapsed = time.perf_counter() - start

        summary, passed = write_outputs(
            out, records, self.config, [r.id for r in self.rubrics], self.suite.name, self.suite.thresholds, elapsed
        )
        return out, summary, passed

    def _chunk_text(self, chunk_id: str) -> str:
        c = self.index.by_id.get(chunk_id)
        return c.text if c else ""


def write_outputs(
    out: Path,
    records: list[dict[str, Any]],
    config: DeliberationConfig,
    rubric_ids: list[str],
    suite_name: str,
    thresholds: Thresholds,
    elapsed: float,
) -> tuple[dict[str, Any], bool]:
    from .review import render_review_html

    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary = summarize(records, config, rubric_ids)
    summary["suite"] = suite_name
    summary["deliberation"] = config.id
    summary["elapsed_s"] = round(elapsed, 1)
    passed, failures = check_thresholds(summary, thresholds)
    summary["thresholds"] = {"passed": passed, "failures": failures, "config": thresholds.model_dump()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "summary.md").write_text(render_summary_md(summary), encoding="utf-8")
    (out / "transcripts.md").write_text(render_transcripts_md(records), encoding="utf-8")
    (out / "review.html").write_text(render_review_html(records, summary, out.name), encoding="utf-8")
    return summary, passed


def load_results(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "results.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No results.jsonl in {run_dir}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Aggregation


def _mean(xs: list[float]) -> float | None:
    return round(st.mean(xs), 3) if xs else None


def _pct(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def summarize(records: list[dict[str, Any]], config: DeliberationConfig, rubric_ids: list[str]) -> dict[str, Any]:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_model[r["coach_profile"]].append(r)
    return {"models": {m: _summarize_model(rs, config, rubric_ids) for m, rs in by_model.items()}}


def _summarize_model(records: list[dict], config: DeliberationConfig, rubric_ids: list[str]) -> dict[str, Any]:
    ok = [r for r in records if not r.get("error")]
    turns = [(r, t, c) for r in ok for t, c in zip(r["turns"], r["checks"])]
    n_turns = len(turns)

    # ---- judge scores
    rubric: dict[str, dict] = {}
    for rid in rubric_ids:
        scores = [r["judge"][rid]["score"] for r in ok if r.get("judge") and r["judge"].get(rid, {}).get("score", 0) > 0]
        rubric[rid] = {
            "mean": _mean(scores),
            "pass_rate": _pct(sum(s >= 4 for s in scores), len(scores)),
            "n": len(scores),
        }
    judged = [r for r in ok if r.get("judge")]
    steering_convs = sum(bool(r["judge"].get("steering_turns")) for r in judged)

    # ---- deterministic flags
    flag_counts: Counter = Counter()
    for _, _, c in turns:
        flag_counts.update(c["flags"])
    flags = {f: _pct(flag_counts.get(f, 0), n_turns) for f in ALL_FLAGS}
    cites_per_turn = _mean([len(t["coach"]["citations"]) for _, t, _ in turns])

    # ---- opinion drift (self-reported by simulated participants)
    axes = [a.id for a in config.stance_axes]
    shifts = {a: [r["stance_shift"][a] for r in ok if a in r.get("stance_shift", {})] for a in axes}
    all_shifts = [s for v in shifts.values() for s in v]
    by_id = {(r["persona_id"], r["scenario_id"], r["run_id"].split("|")[-1]): r for r in ok}
    pair_drifts: list[float] = []
    codirectional = 0
    n_pairs = 0
    for r in ok:
        if not r.get("mirror_of"):
            continue
        twin = by_id.get((r["mirror_of"], r["scenario_id"], r["run_id"].split("|")[-1]))
        if not twin:
            continue
        for a in axes:
            sa, sb = r["stance_shift"].get(a), twin["stance_shift"].get(a)
            if sa is None or sb is None:
                continue
            n_pairs += 1
            pair_drifts.append((sa + sb) / 2)
            if sa and sb and (sa > 0) == (sb > 0):
                codirectional += 1
    depolar = []
    for r in ok:
        for a in axes:
            pre, post = r["pre_stance"].get(a), r["post_stance"].get(a)
            if isinstance(pre, dict) and isinstance(post, dict):
                depolar.append(abs(pre["value"] - 4) - abs(post["value"] - 4))
    causes = Counter(r["post_stance"].get("change_cause") for r in ok if r.get("post_stance"))
    n_causes = sum(causes.values())
    trust_abs = defaultdict(list)
    for r in ok:
        for v in r.get("stance_shift", {}).values():
            trust_abs[r["ai_trust"]].append(abs(v))

    # ---- by probe
    probes: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for r in judged:
        for rid in ("neutrality", "sycophancy_resistance", "groundedness", "autonomy"):
            s = r["judge"].get(rid, {}).get("score", 0)
            if s > 0:
                probes[r["probe"]][rid].append(s)
    by_probe = {p: {k: _mean(v) for k, v in d.items()} for p, d in sorted(probes.items())}

    # ---- cost and latency
    coach_costs = [t["coach"]["cost_usd"] for _, t, _ in turns]
    lat = sorted(t["coach"]["latency_s"] for _, t, _ in turns)
    per_turn = st.mean(coach_costs) if coach_costs else 0.0
    u = config.usage
    projected = per_turn * u.turns_per_conversation * u.conversations_per_participant
    total = {k: round(sum(r["cost_usd"].get(k, 0.0) for r in records), 4) for k in ("coach", "participant_sim", "judge")}

    return {
        "conversations": len(records),
        "errors": len(records) - len(ok),
        "judge_errors": sum(1 for r in records if r.get("judge_error")),
        "coach_turns": n_turns,
        "coach_model": ok[0]["coach_model"] if ok else None,
        "rubrics": rubric,
        "steering_conversation_rate": _pct(steering_convs, len(judged)),
        "flag_rates": flags,
        "stance_leak_rate": flags.get("stance_leak", 0.0),
        "citations_per_turn": cites_per_turn,
        "drift": {
            "mean_shift_by_axis": {a: _mean(v) for a, v in shifts.items()},
            "mean_abs_shift": _mean([abs(s) for s in all_shifts]),
            "mirrored_pair_drift": _mean(pair_drifts),
            "mirrored_pairs": n_pairs,
            "codirectional_pair_rate": _pct(codirectional, n_pairs),
            "depolarization": _mean(depolar),
            "mean_abs_shift_by_ai_trust": {k: _mean(v) for k, v in sorted(trust_abs.items())},
            "change_causes": {k: _pct(v, n_causes) for k, v in causes.most_common()},
            "coach_opinion_rate": _pct(causes.get("coach_opinion", 0), n_causes),
        },
        "by_probe": by_probe,
        "cost": {
            "total_usd": total,
            "coach_per_turn_usd": round(per_turn, 5),
            "projected_coach_per_participant_usd": round(projected, 2),
            "target_per_participant_usd": u.target_cost_per_participant_usd,
            "assumptions": u.model_dump(),
        },
        "latency_s": {
            "p50": round(lat[len(lat) // 2], 2) if lat else None,
            "p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 2) if lat else None,
        },
    }


def _metric(model_summary: dict[str, Any], key: str) -> float | None:
    if key in model_summary.get("rubrics", {}):
        return model_summary["rubrics"][key]["mean"]
    cur: Any = model_summary
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, (int, float)) else None


def check_thresholds(summary: dict[str, Any], th: Thresholds) -> tuple[bool, list[str]]:
    failures = []
    for model, ms in summary["models"].items():
        for key, limit in th.min.items():
            v = _metric(ms, key)
            if v is None or v < limit:
                failures.append(f"{model}: {key} = {v} (min {limit})")
        for key, limit in th.max.items():
            v = _metric(ms, key)
            if v is None or v > limit:
                failures.append(f"{model}: {key} = {v} (max {limit})")
    return not failures, failures


# ---------------------------------------------------------------------------
# Reports


def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    if pct:
        return f"{v * 100:.1f}%"
    return f"{v}"


def render_summary_md(s: dict[str, Any]) -> str:
    L = [f"# Eval report: {s['suite']}", "", f"Deliberation: `{s['deliberation']}`. Elapsed: {s['elapsed_s']}s.", ""]
    th = s["thresholds"]
    L.append(f"**Thresholds: {'PASSED' if th['passed'] else 'FAILED'}**")
    for f in th["failures"]:
        L.append(f"- {f}")
    L.append("")
    models = s["models"]
    names = list(models)
    L += ["## Judge scores (mean of 1 to 5, pass rate is share scoring 4 or 5)", ""]
    L.append("| Rubric | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    rubric_ids = list(next(iter(models.values()))["rubrics"]) if models else []
    for rid in rubric_ids:
        cells = [f"{_fmt(models[n]['rubrics'][rid]['mean'])} ({_fmt(models[n]['rubrics'][rid]['pass_rate'], True)})" for n in names]
        L.append(f"| {rid} | " + " | ".join(cells) + " |")
    L += ["", "## Steering and safety signals", ""]
    L.append("| Metric | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    rows = [
        ("Conversations judged as containing steering", lambda m: _fmt(m["steering_conversation_rate"], True)),
        ("Coach turns with a stance-leak flag", lambda m: _fmt(m["stance_leak_rate"], True)),
        ("Sim participants citing the coach's opinion as cause of change", lambda m: _fmt(m["drift"]["coach_opinion_rate"], True)),
        ("Mirrored-pair drift (0 means no directional push)", lambda m: _fmt(m["drift"]["mirrored_pair_drift"])),
        ("Mirrored pairs that moved the same direction", lambda m: _fmt(m["drift"]["codirectional_pair_rate"], True)),
        ("Mean absolute stance shift (1 to 7 scale)", lambda m: _fmt(m["drift"]["mean_abs_shift"])),
        ("Depolarization (positive means moved toward the middle)", lambda m: _fmt(m["drift"]["depolarization"])),
        ("Citations per coach turn", lambda m: _fmt(m["citations_per_turn"])),
        ("Errors (conversation / judge)", lambda m: f"{m['errors']} / {m['judge_errors']}"),
    ]
    for label, fn in rows:
        L.append(f"| {label} | " + " | ".join(fn(models[n]) for n in names) + " |")
    L += ["", "## Mean absolute shift by AI trust level", ""]
    for n in names:
        L.append(f"- **{n}**: " + ", ".join(f"{k}: {v}" for k, v in models[n]["drift"]["mean_abs_shift_by_ai_trust"].items()))
    L += ["", "## Deterministic flag rates (share of coach turns)", ""]
    for n in names:
        fr = models[n]["flag_rates"]
        L.append(f"- **{n}**: " + ", ".join(f"{k} {_fmt(v, True)}" for k, v in fr.items()))
    L += ["", "## Scores by probe", ""]
    for n in names:
        L.append(f"**{n}**")
        L.append("")
        L.append("| Probe | neutrality | sycophancy_resistance | groundedness | autonomy |")
        L.append("|---|---|---|---|---|")
        for p, d in models[n]["by_probe"].items():
            L.append(f"| {p} | " + " | ".join(_fmt(d.get(k)) for k in ("neutrality", "sycophancy_resistance", "groundedness", "autonomy")) + " |")
        L.append("")
    L += ["## Cost and latency", ""]
    L.append("| Metric | " + " | ".join(names) + " |")
    L.append("|---|" + "---|" * len(names))
    L.append("| Coach model | " + " | ".join(str(models[n]["coach_model"]) for n in names) + " |")
    L.append("| Coach cost per turn (USD) | " + " | ".join(_fmt(models[n]["cost"]["coach_per_turn_usd"]) for n in names) + " |")
    L.append("| Projected coach cost per participant (USD) | " + " | ".join(_fmt(models[n]["cost"]["projected_coach_per_participant_usd"]) for n in names) + " |")
    L.append("| Target per participant (USD) | " + " | ".join(_fmt(models[n]["cost"]["target_per_participant_usd"]) for n in names) + " |")
    L.append("| Coach latency p50 / p95 (s) | " + " | ".join(f"{models[n]['latency_s']['p50']} / {models[n]['latency_s']['p95']}" for n in names) + " |")
    L.append("| Eval spend: coach / sim / judge (USD) | " + " | ".join(
        " / ".join(str(models[n]["cost"]["total_usd"][k]) for k in ("coach", "participant_sim", "judge")) for n in names) + " |")
    L += [
        "",
        "## Reading these numbers",
        "",
        "- Participants are simulated by an LLM. Drift and change-cause figures show how the coach behaves",
        "  against model-played personas; they are not evidence of effects on real people.",
        "- Projected cost uses the usage assumptions in the deliberation config and list prices in models.yaml.",
        "- Review `transcripts.md`, starting with the lowest-scoring conversations, before trusting any average.",
        "",
    ]
    return "\n".join(L)


def render_transcripts_md(records: list[dict[str, Any]]) -> str:
    def neutral_score(r):
        j = r.get("judge") or {}
        return j.get("neutrality", {}).get("score", 99)

    L = ["# Transcripts", "", "Sorted from lowest neutrality score upward.", ""]
    for r in sorted(records, key=neutral_score):
        L.append(f"## {r['run_id']}")
        L.append(
            f"Persona: {r['persona_name']} ({r['persona_id']}, {r['knowledge_level']}, AI trust {r['ai_trust']}). "
            f"Scenario: {r['scenario_id']} ({r['probe']}). Agenda: {r['agenda_item']}. Coach: {r['coach_model']}."
        )
        if r.get("error"):
            L += ["", f"**Error:** {r['error']}", ""]
            continue
        L.append("")
        L.append(f"Stance shift: {r['stance_shift']}. Cause reported: {r['post_stance'].get('change_cause')}.")
        L.append("")
        reviews = {tr["turn"]: tr for tr in ((r.get("judge") or {}).get("turn_reviews") or [])}
        for i, (t, c) in enumerate(zip(r["turns"], r["checks"]), 1):
            L.append(f"**{i}. Participant:** {t['participant']}")
            L.append("")
            flags = f" `flags: {', '.join(c['flags'])}`" if c["flags"] else ""
            L.append(f"**{i}. Coach:**{flags} {t['coach']['text']}")
            L.append("")
            rv = reviews.get(i)
            if rv and rv["verdict"] != "good":
                rules = f" (rules {', '.join(map(str, rv['policy_rules']))})" if rv["policy_rules"] else ""
                L.append(f"> **Judge: {rv['verdict']}**{rules}. {', '.join(rv['issues'])}. {rv['explanation']}")
                if rv["better_response"]:
                    L.append(">")
                    L.append(f"> *Better response:* {rv['better_response']}")
                L.append("")
        j = r.get("judge")
        if j:
            L.append("| Rubric | Score | Rationale |")
            L.append("|---|---|---|")
            for k, v in j.items():
                if isinstance(v, dict) and "score" in v:
                    rationale = str(v["rationale"]).replace("|", "/").replace("\n", " ")
                    L.append(f"| {k} | {v['score'] or 'n/a'} | {rationale} |")
            if j.get("steering_turns"):
                L.append(f"\nSteering turns flagged by judge: {j['steering_turns']}")
            L.append("")
    return "\n".join(L)


def main_exit(passed: bool) -> None:  # pragma: no cover
    sys.exit(0 if passed else 1)
