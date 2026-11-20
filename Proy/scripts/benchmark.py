"""Benchmark automatizado sobre eval/dataset.jsonl (20 casos núcleo + 7 de herramientas).

Métricas:
  Recuperación: Recall@k (grupos de evidencia cubiertos), Hit@k, MRR, redundancia del contexto.
  Respuesta:    precisión de citas, exactitud de abstención, fidelidad y corrección (LLM-as-judge).
  Herramientas: herramienta correcta, resultado esperado (monto exacto / tipo de error).
  Operación:    latencia media y P95, tokens, llamadas al LLM, costo.

Uso:
  python Proy/scripts/benchmark.py --system baseline
  python Proy/scripts/benchmark.py --system agent --judge
  python Proy/scripts/benchmark.py --system agent --retrieval-only
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # sin depender del .pth
os.environ.setdefault("TODAY", "2026-11-19")  # fecha fija -> resultados reproducibles

import argparse
import csv
import json
import re
import statistics
import time
from datetime import datetime

from laboragt import config
from laboragt.schemas import UserRole

EVAL_DIR = config.PROY_DIR / "eval"


def chunk_keys(doc_id: str, article: str | None, page: int) -> set[str]:
    keys = {f"{doc_id}:p{page}"}
    if article:
        keys.add(f"{doc_id}:{article}")
    return keys


def retrieval_metrics(hits, groups: list[list[str]]):
    if not groups:
        return None, None, None
    hit_keys = [chunk_keys(h.chunk.doc_id, h.chunk.article, h.chunk.page) for h in hits]
    covered = sum(any(alt in ks for ks in hit_keys for alt in g) for g in groups)
    all_alts = {a for g in groups for a in g}
    rr = 0.0
    for rank, ks in enumerate(hit_keys, start=1):
        if ks & all_alts:
            rr = 1.0 / rank
            break
    return covered / len(groups), float(covered > 0), rr


def redundancy(hits) -> float | None:
    """Proporción de chunks del top-k que repiten un artículo ya presente (ruido/redundancia)."""
    if not hits:
        return None
    keys = [(h.chunk.doc_id, h.chunk.article or h.chunk.chunk_id) for h in hits]
    return 1 - len(set(keys)) / len(keys)


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))] if xs else 0.0


def make_system(name: str):
    if name == "baseline":
        from laboragt.baseline import BaselineRAG
        return BaselineRAG()
    from laboragt.agent import LaboraAgent
    return LaboraAgent()


def run_case(system, c):
    role = UserRole(c.get("role", "colaborador"))
    if system.name.startswith("baseline"):
        return system.answer(c["question"], role)
    return system.answer(c["question"], role, employee_id=c.get("employee_id"),
                         confirmed=c.get("confirmed", False),
                         simulate_unavailable=set(c.get("simulate_unavailable", [])))


def tool_check(c, resp, info_decision) -> dict:
    """Evalúa los casos de herramientas contra su resultado esperado."""
    if "expected_tool" not in c:
        return {}
    ok_tool = resp.tool_used == c["expected_tool"]
    ok = ok_tool and resp.abstained == c.get("expected_abstained", resp.abstained)
    if "expected_total" in c:
        m = re.search(r"Total: Q([\d,]+\.\d{2})", resp.answer)
        ok = ok and bool(m) and abs(float(m.group(1).replace(",", "")) - c["expected_total"]) < 0.005
    if "expected_error_type" in c:
        ok = ok and info_decision == f"herramienta_{c['expected_error_type']}"
    if "expected_human_review" in c:
        ok = ok and resp.needs_human_review == c["expected_human_review"]
    for s in c.get("expected_contains", []):
        ok = ok and s in resp.answer
    if c.get("expected_sources"):
        ok = ok and any(s.article == "82" for s in resp.sources)
    return {"tool_selected_ok": ok_tool, "tool_case_ok": ok}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["baseline", "agent"], default="agent")
    ap.add_argument("--dataset", default=str(EVAL_DIR / "dataset.jsonl"))
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--judge", action="store_true", help="evalúa fidelidad/corrección con LLM-as-judge")
    a = ap.parse_args()

    cases = [json.loads(l) for l in open(a.dataset, encoding="utf-8") if l.strip()]
    system = make_system(a.system)
    if a.system == "agent" and config.LLM_MODEL != "qwen2.5:7b-instruct":  # ablación de modelo
        system.name += "__" + config.LLM_MODEL.replace(":", "-").replace(".", "")
    # calentamiento: carga modelos (no se mide)
    if a.system == "agent":
        system.retriever.search("calentamiento de modelos", UserRole.RRHH)

    rows = []
    for c in cases:
        is_tool_case = "expected_tool" in c
        if a.retrieval_only:
            if is_tool_case:
                continue
            retr = system.retriever.search if hasattr(system, "retriever") else system.retrieve
            t0 = time.perf_counter()
            hits = retr(c["question"], UserRole(c["role"]))
            resp, lat, info = None, time.perf_counter() - t0, None
        else:
            resp, info = run_case(system, c)
            hits, lat = info.hits, info.latency_s
        recall, hit, rr = retrieval_metrics(hits, c.get("expected_sources", [])) if not is_tool_case else (None, None, None)

        row = {"id": c["id"], "category": c["category"], "answerable": c["answerable"],
               "recall@k": recall, "hit@k": hit, "rr": rr, "redundancy": redundancy(hits) if not is_tool_case else None,
               "latency_s": round(lat, 3),
               "top1": hits[0].chunk.chunk_id if hits else "", "top1_score": round(hits[0].score, 4) if hits else 0}
        if resp is not None:
            alts = {x for g in c.get("expected_sources", []) for x in g}
            cited = [chunk_keys(s.chunk_id.rsplit("-", 1)[0], s.article, s.page) for s in resp.sources]
            correct_cites = sum(bool(k & alts) for k in cited)
            row.update({
                "decision": info.decision, "abstained": resp.abstained, "tool_used": resp.tool_used,
                "abstention_correct": resp.abstained == (not c["answerable"]),
                "n_citations": len(cited),
                "citation_precision": (correct_cites / len(cited)) if (cited and alts) else None,
                "needs_human_review": resp.needs_human_review,
                "llm_calls": info.llm_calls, "prompt_tokens": info.prompt_tokens, "output_tokens": info.output_tokens,
                **tool_check(c, resp, info.decision),
            })
            if a.judge and not resp.abstained and not is_tool_case:
                from laboragt.judge import judge
                ctx = [h.chunk.text for h in hits if h.chunk.chunk_id in {s.chunk_id for s in resp.sources}]
                j, _, _ = judge(c["question"], resp.answer, ctx, c["expected_behavior"])
                if j:
                    row["faithfulness"] = round(j.claims_supported / j.claims_total, 3) if j.claims_total else 1.0
                    row["judge_correct"] = j.correct
                    row["judge_rationale"] = j.rationale
            if a.judge and not is_tool_case and resp.abstained:
                row["judge_correct"] = not c["answerable"]  # abstención correcta = respuesta correcta
            row["answer"] = resp.answer
            row["expected_behavior"] = c["expected_behavior"]
        rows.append(row)
        flag = "" if resp is None else ("ABST" if resp.abstained else "RESP")
        extra = f" tool_ok={row.get('tool_case_ok')}" if is_tool_case and resp is not None else ""
        print(f"{c['id']:4s} {c['category']:28s} recall={recall!s:5.5s} rr={rr!s:5.5s} {flag:4s} "
              f"{lat:6.2f}s{extra}  top1={row['top1']}", flush=True)

    def mean(key, subset=None):
        vals = [r[key] for r in (subset if subset is not None else rows) if r.get(key) is not None]
        return round(statistics.mean(vals), 3) if vals else None

    core = [r for r in rows if not r["category"].startswith("herramienta")]
    ans = [r for r in core if r["answerable"]]
    summary = {
        "system": system.name, "k": config.TOP_K, "n_cases": len(rows),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "retrieval": {"recall@k": mean("recall@k", ans), "hit@k": mean("hit@k", ans), "mrr": mean("rr", ans),
                      "redundancy": mean("redundancy", ans)},
        "operation": {"latency_mean_s": round(statistics.mean(r["latency_s"] for r in rows), 3),
                      "latency_p95_s": round(p95([r["latency_s"] for r in rows]), 3)},
    }
    if not a.retrieval_only:
        unans = [r for r in core if not r["answerable"]]
        tools = [r for r in rows if r["category"].startswith("herramienta")]
        summary["answer"] = {
            "citation_precision": mean("citation_precision", ans),
            "abstention_accuracy": mean("abstention_correct", core),
            "abstention_on_unanswerable": mean("abstention_correct", unans),
            "false_abstention_rate": round(sum(r["abstained"] for r in ans) / len(ans), 3) if ans else None,
        }
        if a.judge:
            summary["answer"]["faithfulness"] = mean("faithfulness", core)
            summary["answer"]["judge_correctness"] = mean("judge_correct", core)
        summary["tools"] = {"n": len(tools), "tool_selection_accuracy": mean("tool_selected_ok", tools),
                            "tool_case_accuracy": mean("tool_case_ok", tools)}
        summary["operation"].update({
            "llm_calls_total": sum(r["llm_calls"] for r in rows),
            "prompt_tokens_mean": mean("prompt_tokens"), "output_tokens_mean": mean("output_tokens"),
            "api_cost_usd": 0.0,
        })

    out = EVAL_DIR / "results"
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{system.name}{'_retrieval' if a.retrieval_only else ''}_{datetime.now():%Y%m%d_%H%M%S}"
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(out / f"{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    (out / f"{tag}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nResultados: {out / tag}.csv")


if __name__ == "__main__":
    main()
