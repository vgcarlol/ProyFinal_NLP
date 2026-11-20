"""Suite adversaria (Fase 5): ejecuta eval/security_tests.jsonl contra el sistema y documenta
Amenaza | Componente | Comportamiento esperado | Resultado observado | Mitigación | Resultado.

Uso:  python Proy/scripts/security_tests.py [--system agent|baseline]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("TODAY", "2026-11-19")

import argparse
import csv
import json
from datetime import datetime

from laboragt import config
from laboragt.schemas import UserRole

EVAL_DIR = config.PROY_DIR / "eval"


def evaluate(case, resp, decision) -> tuple[bool, str]:
    problems = []
    low = resp.answer.lower()
    for s in case.get("must_not_contain", []):
        if s.lower() in low:
            problems.append(f"contiene '{s}'")
    if case.get("expect_blocked") and not resp.abstained:
        problems.append("no fue bloqueado/abstenido")
    if et := case.get("expected_error_type"):
        if decision != f"herramienta_{et}":
            problems.append(f"decisión {decision} != herramienta_{et}")
    return (not problems), "; ".join(problems)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["agent", "baseline"], default="agent")
    a = ap.parse_args()
    if a.system == "agent":
        from laboragt.agent import LaboraAgent
        system = LaboraAgent()
    else:
        from laboragt.baseline import BaselineRAG
        system = BaselineRAG()

    cases = [json.loads(l) for l in open(EVAL_DIR / "security_tests.jsonl", encoding="utf-8") if l.strip()]
    rows = []
    for c in cases:
        if a.system == "agent":
            resp, info = system.answer(c["question"], UserRole(c["role"]), employee_id=c.get("employee_id"),
                                       confirmed=c.get("confirmed", False))
        else:
            resp, info = system.answer(c["question"], UserRole(c["role"]))
        passed, why = evaluate(c, resp, info.decision)
        observed = f"[{info.decision}] {resp.answer[:220]}"
        rows.append({"id": c["id"], "vector": c["vector"], "amenaza": c["threat"], "componente": c["component"],
                     "esperado": c["expected_behavior"], "observado": observed, "mitigacion": c["mitigation"],
                     "resultado": "PASA" if passed else "FALLA", "detalle": why,
                     "abstained": resp.abstained, "needs_human_review": resp.needs_human_review,
                     "latency_s": round(info.latency_s, 2)})
        print(f"{c['id']} {c['vector']:22s} {'PASA ' if passed else 'FALLA'} [{info.decision}] {why}", flush=True)

    n_pass = sum(r["resultado"] == "PASA" for r in rows)
    out = EVAL_DIR / "results"
    out.mkdir(parents=True, exist_ok=True)
    tag = f"security_{a.system}_{datetime.now():%Y%m%d_%H%M%S}"
    with open(out / f"{tag}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    md = [f"# Pruebas de seguridad — {a.system} ({datetime.now():%Y-%m-%d %H:%M})", "",
          f"**Resultado: {n_pass}/{len(rows)} pruebas superadas ({n_pass / len(rows):.0%}).**", "",
          "| ID | Vector | Amenaza | Componente | Esperado | Observado | Mitigación | Resultado |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        obs = r["observado"].replace("|", "/").replace("\n", " ")
        md.append(f"| {r['id']} | {r['vector']} | {r['amenaza']} | {r['componente']} | {r['esperado']} | {obs} | "
                  f"{r['mitigacion']} | {r['resultado']} |")
    (out / f"{tag}.md").write_text("\n".join(md), encoding="utf-8")
    summary = {"system": a.system, "passed": n_pass, "total": len(rows), "block_rate": round(n_pass / len(rows), 3)}
    (out / f"{tag}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{n_pass}/{len(rows)} superadas -> {out / tag}.md")


if __name__ == "__main__":
    main()
