"""Command-line interface.

  delib list                         personas, scenarios, modes, model profiles
  delib ingest   --config ...        load materials and build the retrieval index
  delib search   --config ... "q"    debug retrieval
  delib chat     --config ...        talk to the coach yourself
  delib simulate --config ... --persona ID --scenario ID
  delib eval     --suite ...         run an eval suite and write a report
  delib review   --run runs/<dir>    rebuild and open the interactive review page
  delib rejudge  --run runs/<dir> --config ...   re-score a run with the current judge
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from .coach import MODES, Coach, ParticipantJourney, update_journey
from .config import DeliberationConfig
from .corpus import MaterialIndex
from .corpus.index import load_documents
from .evals.checks import check_turn
from .evals.judge import Judge, load_rubrics
from .evals.review import render_review_html
from .evals.runner import EvalRunner, Suite, Thresholds, load_results, write_outputs
from .llm import Message, ModelRegistry
from .sim import Simulator, load_personas, load_scenarios

DEFAULT_MODELS = "configs/models.yaml"


def _registry(args) -> ModelRegistry:
    return ModelRegistry.load(args.models)


def _index(cfg: DeliberationConfig, reg: ModelRegistry, rebuild: bool = False) -> MaterialIndex:
    embedder = reg.client("embedder") if reg.has_role("embedder") else None
    return MaterialIndex.build(cfg, embedder=embedder, rebuild=rebuild)


def cmd_list(args) -> int:
    print("Personas:")
    for p in load_personas():
        twin = f" (mirror of {p.mirror_of})" if p.mirror_of else ""
        print(f"  {p.id:<26} {p.knowledge_level:<9} lean {p.lean:+d}  trust {p.ai_trust}{twin}")
    print("\nScenarios:")
    for s in load_scenarios():
        print(f"  {s.id:<22} mode={s.mode:<13} probe={s.probe}")
    print("\nCoach modes:", ", ".join(MODES))
    if Path(args.models).exists():
        reg = _registry(args)
        print(f"\nModel profiles ({args.models}):")
        for name, p in reg.profiles.items():
            print(f"  {name:<18} {p.provider:<18} {p.model}")
        print("Roles:", ", ".join(f"{k}={v}" for k, v in reg.roles.items() if v))
    return 0


def cmd_ingest(args) -> int:
    cfg = DeliberationConfig.load(args.config)
    docs = load_documents(cfg)
    if not docs:
        print(f"No materials found. Paths are resolved relative to {cfg.base_dir}.")
        return 1
    for d in docs:
        tags = f" agenda={','.join(d.agenda_items)}" if d.agenda_items else ""
        print(f"  {d.doc_id:<45} {d.kind:<10} {len(d.segments):>4} segs {len(d.text.split()):>7} words{tags}")
    idx = _index(cfg, _registry(args), rebuild=True)
    print(f"\nIndexed {len(idx.chunks)} chunks from {len(docs)} documents. Dense retrieval: {'on' if idx.embeddings else 'off'}.")
    return 0


def cmd_search(args) -> int:
    cfg = DeliberationConfig.load(args.config)
    idx = _index(cfg, _registry(args))
    for i, h in enumerate(idx.search(args.query, k=args.k, agenda_item=args.agenda, max_per_doc=args.max_per_doc or None), 1):
        print(f"\n[{i}] score={h.score:.3f}  {h.chunk.cite_label}  ({h.chunk.chunk_id})")
        print("    " + h.chunk.text[:400].replace("\n", " ") + ("..." if len(h.chunk.text) > 400 else ""))
    return 0


def cmd_chat(args) -> int:
    cfg = DeliberationConfig.load(args.config)
    reg = _registry(args)
    coach = Coach(reg.client(args.profile), cfg, _index(cfg, reg))
    journey_path = Path(args.journey) if args.journey else None
    if journey_path and journey_path.exists():
        journey = ParticipantJourney.model_validate_json(journey_path.read_text(encoding="utf-8"))
    else:
        journey = ParticipantJourney(participant_id="you", knowledge_level=args.level, focus_agenda_item=args.agenda)
    mode, agenda = args.mode, args.agenda or journey.focus_agenda_item
    history: list[Message] = []
    total = 0.0
    last_turn = None
    print(f"Deliberation Partner: {cfg.title}  (model {coach.client.profile.model}, mode {mode})")
    print("Commands: /mode <name>  /agenda <id>  /sources  /cost  /quit\n")
    while True:
        try:
            msg = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not msg:
            continue
        if msg.startswith("/"):
            cmd, _, arg = msg.partition(" ")
            if cmd == "/quit":
                break
            if cmd == "/mode" and arg in MODES:
                mode = arg
                print(f"(mode: {mode})")
            elif cmd == "/agenda":
                agenda = arg or None
                print(f"(agenda: {agenda})")
            elif cmd == "/sources" and last_turn:
                for i, c in enumerate(last_turn.sources, 1):
                    print(f"  [S{i}] {c.cite_label}")
            elif cmd == "/cost":
                print(f"(session cost: ${total:.4f})")
            else:
                print("(unknown command)")
            continue
        last_turn = coach.respond(journey, history, msg, mode, agenda)
        total += last_turn.cost_usd
        history += [Message("user", msg), Message("assistant", last_turn.text)]
        flags = check_turn(last_turn.to_dict(), journey.knowledge_level).flags
        print(f"\ncoach> {last_turn.text}")
        if last_turn.citations:
            print("       sources: " + "; ".join(f"[{c.label}] {c.source}" for c in last_turn.citations))
        if flags and args.show_flags:
            print(f"       flags: {', '.join(flags)}")
        print()
    if journey_path and history:
        update_journey(reg.client("journey"), cfg, journey, history)
        journey_path.write_text(journey.model_dump_json(indent=2), encoding="utf-8")
        print(f"Journey saved to {journey_path}")
    print(f"Session cost: ${total:.4f}")
    return 0


def cmd_simulate(args) -> int:
    cfg = DeliberationConfig.load(args.config)
    reg = _registry(args)
    personas = {p.id: p for p in load_personas()}
    scenarios = {s.id: s for s in load_scenarios()}
    if args.persona not in personas or args.scenario not in scenarios:
        print("Unknown persona or scenario. Run `delib list`.")
        return 1
    coach = Coach(reg.client(args.profile), cfg, _index(cfg, reg))
    sim = Simulator(coach, reg.client("participant_sim"), cfg)
    agenda = args.agenda or (cfg.agenda[0].id if cfg.agenda else None)
    tr = sim.run(personas[args.persona], scenarios[args.scenario], agenda, turns=args.turns)
    if tr.error:
        print("ERROR:", tr.error)
        return 1
    print(tr.render())
    print("\nChecks per coach turn:")
    for i, t in enumerate(tr.turns, 1):
        print(f"  turn {i}: {check_turn(t['coach'], tr.persona.knowledge_level).flags or 'clean'}")
    print(f"\nStance before: { {k: v['value'] for k, v in tr.pre_stance.items() if isinstance(v, dict)} }")
    print(f"Stance after:  { {k: v['value'] for k, v in tr.post_stance.items() if isinstance(v, dict)} }")
    print(f"Cause reported: {tr.post_stance.get('change_cause')}")
    print(f"Cost: {json.dumps({k: round(v, 5) for k, v in tr.cost_usd.items()})}")
    if args.out:
        Path(args.out).write_text(json.dumps(tr.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def cmd_eval(args) -> int:
    suite, suite_dir = Suite.load(args.suite)
    cfg_path = args.config or (str(suite_dir / suite.deliberation) if suite.deliberation else None)
    if not cfg_path:
        print("This suite has no 'deliberation' path; pass --config.")
        return 2
    cfg = DeliberationConfig.load(cfg_path)
    runner = EvalRunner(suite, cfg, _registry(args), out_root=args.out, rebuild_index=args.rebuild)
    n = len(runner.plan())
    if n > 30 and not args.yes:
        reply = input(f"This will run {n} conversations with real API calls. Continue? [y/N] ")
        if reply.strip().lower() not in {"y", "yes"}:
            return 1
    out, summary, passed = runner.run()
    print(f"\nReport: {out / 'summary.md'}")
    print(f"Review: {out / 'review.html'}")
    for model, ms in summary["models"].items():
        r = ms["rubrics"]
        print(
            f"  {model}: neutrality {r['neutrality']['mean']}, sycophancy_resistance {r['sycophancy_resistance']['mean']}, "
            f"groundedness {r['groundedness']['mean']}, stance-leak rate {ms['stance_leak_rate']}, "
            f"projected ${ms['cost']['projected_coach_per_participant_usd']}/participant"
        )
    th = summary["thresholds"]
    if th["failures"]:
        print("Threshold failures:")
        for f in th["failures"]:
            print("  -", f)
    if args.open:
        webbrowser.open((out / "review.html").resolve().as_uri())
    return 0 if passed else 1


def cmd_review(args) -> int:
    run_dir = Path(args.run)
    records = load_results(run_dir)
    summary_path = run_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"models": {}}
    out = run_dir / "review.html"
    out.write_text(render_review_html(records, summary, run_dir.name), encoding="utf-8")
    print(f"Review: {out}")
    if not args.no_open:
        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_rejudge(args) -> int:
    run_dir = Path(args.run)
    records = load_results(run_dir)
    old_summary_path = run_dir / "summary.json"
    old = json.loads(old_summary_path.read_text(encoding="utf-8")) if old_summary_path.exists() else {}
    cfg = DeliberationConfig.load(args.config)
    reg = _registry(args)
    index = _index(cfg, reg)

    def chunk_text(cid: str) -> str:
        c = index.by_id.get(cid)
        return c.text if c else ""

    rubrics = load_rubrics()
    judge = Judge(reg.client("judge"), cfg, rubrics, chunk_text)
    scenarios = {s.id: s for s in load_scenarios()}
    todo = [r for r in records if not r.get("error")]
    print(f"Re-judging {len(todo)} conversations in {run_dir} with {judge.client.profile.model}")
    if any(not r.get("excerpts") for r in todo):
        print("Note: this run did not store the excerpts the coach saw. They will be rebuilt from the current\n"
              "index, which may differ slightly if materials or cleaning rules changed since the run.")

    def work(rec):
        if not rec.get("scenario_brief"):
            sc = scenarios.get(rec["scenario_id"])
            rec["scenario_brief"] = sc.brief.replace("{agenda}", rec.get("agenda_item") or "the framing question").strip() if sc else ""
        if not rec.get("excerpts"):
            # Older runs did not store excerpt text; fall back to the current index.
            rec["excerpts"] = {s["chunk_id"]: chunk_text(s["chunk_id"]) for t in rec["turns"] for s in t["coach"]["sources"]}
            rec["excerpts_from_current_index"] = True
        rec["checks"] = [check_turn(t["coach"], rec["knowledge_level"]).to_dict() for t in rec["turns"]]
        rec.pop("judge_error", None)
        try:
            scores, resp = judge.score(rec, rec["scenario_brief"])
            rec["judge"] = scores
            rec["cost_usd"]["judge"] = resp.cost_usd
            return f"  {rec['run_id']}: ok"
        except Exception as exc:  # noqa: BLE001
            rec["judge_error"] = f"{type(exc).__name__}: {exc}"
            return f"  {rec['run_id']}: ERROR {rec['judge_error']}"

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for line in pool.map(work, todo):
            print(line)
    backup = run_dir / "results.before-rejudge.jsonl"
    if not backup.exists():
        (run_dir / "results.jsonl").replace(backup)
    if args.suite:
        thresholds = Suite.load(args.suite)[0].thresholds
    else:
        thresholds = Thresholds(**((old.get("thresholds") or {}).get("config") or {}))
    summary, passed = write_outputs(
        run_dir, records, cfg, [r.id for r in rubrics], old.get("suite", run_dir.name), thresholds,
        time.perf_counter() - start,
    )
    print(f"\nReport: {run_dir / 'summary.md'}\nReview: {run_dir / 'review.html'}")
    if not args.no_open:
        webbrowser.open((run_dir / "review.html").resolve().as_uri())
    return 0 if passed else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="delib", description="Personal Deliberation Partner")
    ap.add_argument("--models", default=DEFAULT_MODELS, help="model profiles YAML (default: configs/models.yaml)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    p = sub.add_parser("ingest")
    p.add_argument("--config", required=True)
    p.set_defaults(fn=cmd_ingest)

    p = sub.add_parser("search")
    p.add_argument("--config", required=True)
    p.add_argument("query")
    p.add_argument("--agenda")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--max-per-doc", type=int, default=1, help="0 to disable the per-source cap")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("chat")
    p.add_argument("--config", required=True)
    p.add_argument("--profile", default="coach", help="role or profile name for the coach")
    p.add_argument("--level", default="some", choices=["novice", "some", "informed", "expert"])
    p.add_argument("--mode", default="auto", choices=MODES)
    p.add_argument("--agenda")
    p.add_argument("--journey", help="JSON file to load and save the participant journey")
    p.add_argument("--show-flags", action="store_true")
    p.set_defaults(fn=cmd_chat)

    p = sub.add_parser("simulate")
    p.add_argument("--config", required=True)
    p.add_argument("--persona", required=True)
    p.add_argument("--scenario", required=True)
    p.add_argument("--agenda")
    p.add_argument("--turns", type=int)
    p.add_argument("--profile", default="coach")
    p.add_argument("--out", help="write the transcript JSON here")
    p.set_defaults(fn=cmd_simulate)

    p = sub.add_parser("eval")
    p.add_argument("--suite", required=True)
    p.add_argument("--config", help="overrides the suite's deliberation path")
    p.add_argument("--out", default="runs")
    p.add_argument("--rebuild", action="store_true", help="rebuild the retrieval index")
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--open", action="store_true", help="open review.html in your browser when done")
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("review", help="rebuild and open the interactive review page for a run")
    p.add_argument("--run", required=True, help="path to a runs/<suite>-<timestamp> folder")
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("rejudge", help="re-score an existing run with the current judge (no new conversations)")
    p.add_argument("--run", required=True)
    p.add_argument("--config", required=True, help="the deliberation config the run used")
    p.add_argument("--suite", help="re-apply this suite's thresholds")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-open", action="store_true")
    p.set_defaults(fn=cmd_rejudge)
    return ap


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
        except Exception:  # noqa: BLE001
            pass
    load_dotenv()
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
