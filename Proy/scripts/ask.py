"""CLI para consultar el sistema.

Uso:
  python Proy/scripts/ask.py "¿Cuántos días de vacaciones me corresponden?" --role colaborador --debug
  python Proy/scripts/ask.py "¿Cuál es mi salario?" --role colaborador --employee-id E-014
  python Proy/scripts/ask.py "Genera el borrador de liquidación del empleado E-010" --role rrhh --confirm
  python Proy/scripts/ask.py "..." --system baseline
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # sin depender del .pth

import argparse
import json

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--role", default="colaborador", choices=["colaborador", "rrhh", "admin"])
    ap.add_argument("--employee-id", default=None, help="employee_id de la sesión (p. ej. E-014)")
    ap.add_argument("--confirm", action="store_true", help="confirmación humana para acciones críticas")
    ap.add_argument("--system", choices=["agent", "baseline"], default="agent")
    ap.add_argument("--debug", action="store_true", help="muestra los candidatos recuperados")
    a = ap.parse_args()

    if a.system == "baseline":
        from laboragt.baseline import BaselineRAG
        resp, info = BaselineRAG().answer(a.question, a.role)
    else:
        from laboragt.agent import LaboraAgent
        resp, info = LaboraAgent().answer(a.question, a.role, employee_id=a.employee_id, confirmed=a.confirm)
    if a.debug:
        for h in info.hits:
            print(f"  #{h.rank} {h.score:8.4f}  {h.chunk.chunk_id:34s} art={h.chunk.article} p{h.chunk.page}")
        print(f"  decisión={info.decision} latencia={info.latency_s:.2f}s tokens={info.prompt_tokens}+{info.output_tokens}\n")
    print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=2))
