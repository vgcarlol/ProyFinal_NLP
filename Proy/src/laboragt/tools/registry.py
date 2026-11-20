"""Registro y ejecución controlada de herramientas.

Controles: lista blanca de herramientas, validación Pydantic de argumentos, permisos por rol,
máximo de llamadas por consulta, timeout, degradación controlada y confirmación humana (HITL)
para la única acción crítica (borrador de liquidación).
"""
from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .. import config
from ..schemas import UserRole
from .empleados import EmpleadoInput, PermissionDenied, consultar_empleado, safe_view
from .prestaciones import Motivo, PrestacionesInput, TipoCalculo, calcular_prestaciones


class ToolUnavailable(Exception):
    pass


@dataclass
class ToolContext:
    role: UserRole
    session_employee_id: str | None = None
    confirmed: bool = False  # el usuario confirmó explícitamente la acción crítica
    simulate_unavailable: set[str] = field(default_factory=set)  # para pruebas de degradación
    calls: int = 0


@dataclass
class ToolOutcome:
    tool: str
    ok: bool
    data: Any = None
    error: str | None = None
    error_type: str | None = None  # validacion | permiso | no_encontrado | no_disponible | limite | confirmacion
    needs_confirmation: bool = False


class LiquidacionInput(BaseModel):
    employee_id: str
    fecha_fin: date
    motivo: Motivo = Motivo.DESPIDO_INJUSTIFICADO


def _tool_calcular(args: dict, ctx: ToolContext) -> Any:
    args = dict(args)
    # Si se indica un empleado, completar salario y fechas desde su registro (con RBAC)
    if args.get("employee_id"):
        emp = consultar_empleado(EmpleadoInput(employee_id=args["employee_id"]), ctx.role, ctx.session_employee_id)
        args.setdefault("salario_mensual", emp.salario_base)
        if not args.get("salario_mensual"):
            args["salario_mensual"] = emp.salario_base
        if not args.get("fecha_inicio"):
            args["fecha_inicio"] = emp.fecha_ingreso
        if not args.get("ultima_fecha_vacaciones"):
            args["ultima_fecha_vacaciones"] = emp.ultima_fecha_vacaciones
    args.pop("employee_id", None)
    if not args.get("fecha_fin"):
        args["fecha_fin"] = date.today()
    inp = PrestacionesInput(**{k: v for k, v in args.items() if v is not None})
    return {"input": inp.model_dump(mode="json"), "result": calcular_prestaciones(inp).model_dump(mode="json")}


def _tool_empleado(args: dict, ctx: ToolContext) -> Any:
    emp = consultar_empleado(EmpleadoInput(**args), ctx.role, ctx.session_employee_id)
    return safe_view(emp)


def _tool_borrador(args: dict, ctx: ToolContext) -> Any:
    if ctx.role != UserRole.RRHH:
        raise PermissionDenied("Solo Recursos Humanos puede generar borradores de liquidación.")
    inp = LiquidacionInput(**args)
    emp = consultar_empleado(EmpleadoInput(employee_id=inp.employee_id), ctx.role, ctx.session_employee_id)
    calc = calcular_prestaciones(PrestacionesInput(
        tipo=TipoCalculo.LIQUIDACION, salario_mensual=emp.salario_base, fecha_inicio=emp.fecha_ingreso,
        fecha_fin=inp.fecha_fin, motivo=inp.motivo, ultima_fecha_vacaciones=emp.ultima_fecha_vacaciones))
    return {"estado": "BORRADOR — no se ha enviado ni registrado nada", "empleado": safe_view(emp),
            "motivo": inp.motivo.value, "fecha_fin": inp.fecha_fin.isoformat(),
            "result": calc.model_dump(mode="json"),
            "requiere_aprobacion": "Gerencia de RRHH (y Gerencia General si supera Q50,000.00)"}


TOOLS: dict[str, tuple[Callable[[dict, ToolContext], Any], bool]] = {
    # nombre: (función, es_acción_crítica)
    "calcular_prestaciones": (_tool_calcular, False),
    "consultar_empleado": (_tool_empleado, False),
    "generar_borrador_liquidacion": (_tool_borrador, True),
}
_POOL = cf.ThreadPoolExecutor(max_workers=2)


def run_tool(name: str, args: dict, ctx: ToolContext) -> ToolOutcome:
    if name not in TOOLS:
        return ToolOutcome(name, False, error=f"Herramienta no permitida: {name}", error_type="validacion")
    if ctx.calls >= config.TOOL_MAX_CALLS:
        return ToolOutcome(name, False, error="Se alcanzó el límite de llamadas a herramientas por consulta.",
                           error_type="limite")
    fn, critical = TOOLS[name]
    if critical and not ctx.confirmed:
        return ToolOutcome(name, False, needs_confirmation=True, error_type="confirmacion",
                           error="Esta acción requiere confirmación humana explícita antes de ejecutarse.")
    ctx.calls += 1
    try:
        if name in ctx.simulate_unavailable:
            raise ToolUnavailable(f"El servicio '{name}' no está disponible.")
        data = _POOL.submit(fn, args, ctx).result(timeout=config.TOOL_TIMEOUT_S)
        return ToolOutcome(name, True, data=data)
    except ValidationError as e:
        msgs = "; ".join(f"{'.'.join(map(str, er['loc'])) or 'entrada'}: {er['msg']}" for er in e.errors())
        return ToolOutcome(name, False, error=f"Parámetros inválidos: {msgs}", error_type="validacion")
    except PermissionDenied as e:
        return ToolOutcome(name, False, error=str(e), error_type="permiso")
    except LookupError as e:
        return ToolOutcome(name, False, error=str(e), error_type="no_encontrado")
    except (ToolUnavailable, cf.TimeoutError) as e:
        return ToolOutcome(name, False, error=str(e) or "Tiempo de espera agotado.", error_type="no_disponible")
    except ValueError as e:
        return ToolOutcome(name, False, error=f"Parámetros inválidos: {e}", error_type="validacion")
