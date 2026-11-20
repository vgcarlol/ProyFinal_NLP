"""Herramienta: consulta de registros de empleados (SQLite, datos 100 % sintéticos).

Control de acceso: RRHH consulta cualquier registro; un colaborador solo el propio
(su employee_id viene de la sesión, nunca de la pregunta). SQL parametrizado de solo lectura.
"""
from __future__ import annotations

import random
import re
import sqlite3
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, field_validator

from .. import config
from ..schemas import UserRole

ID_RX = re.compile(r"^E-\d{3}$")


class PermissionDenied(Exception):
    pass


class EmpleadoInput(BaseModel):
    employee_id: str

    @field_validator("employee_id")
    @classmethod
    def fmt(cls, v: str) -> str:
        v = v.strip().upper()
        if not ID_RX.match(v):
            raise ValueError("employee_id debe tener el formato E-000")
        return v


class Empleado(BaseModel):
    employee_id: str
    nombre: str
    puesto: str
    fecha_ingreso: date
    salario_base: Decimal
    circunscripcion: str
    ultima_fecha_vacaciones: date | None
    dpi: str  # PII sintética: nunca se devuelve completa al LLM ni a los logs
    email: str


def _connect(readonly: bool = True) -> sqlite3.Connection:
    if readonly:
        return sqlite3.connect(f"file:{config.EMPLOYEES_DB}?mode=ro", uri=True)
    return sqlite3.connect(config.EMPLOYEES_DB)


def consultar_empleado(inp: EmpleadoInput, role: UserRole, session_employee_id: str | None) -> Empleado:
    if role == UserRole.COLABORADOR and inp.employee_id != (session_employee_id or "").upper():
        raise PermissionDenied("Un colaborador solo puede consultar su propio registro.")
    if role == UserRole.ADMIN:
        raise PermissionDenied("El rol administrador no tiene acceso a datos personales.")
    with _connect() as con:
        row = con.execute(
            "SELECT employee_id, nombre, puesto, fecha_ingreso, salario_base, circunscripcion, "
            "ultima_fecha_vacaciones, dpi, email FROM empleados WHERE employee_id = ?",
            (inp.employee_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"No existe el empleado {inp.employee_id}")
    keys = list(Empleado.model_fields)
    return Empleado(**dict(zip(keys, row)))


def safe_view(e: Empleado) -> dict:
    """Vista sin PII sensible para el LLM y los logs."""
    return {"employee_id": e.employee_id, "nombre": e.nombre, "puesto": e.puesto,
            "fecha_ingreso": e.fecha_ingreso.isoformat(), "salario_base": f"Q{e.salario_base:,.2f}",
            "circunscripcion": e.circunscripcion,
            "ultima_fecha_vacaciones": e.ultima_fecha_vacaciones.isoformat() if e.ultima_fecha_vacaciones else None,
            "dpi": "****" + e.dpi[-4:]}


# ---------------- generación de la base sintética ----------------
NOMBRES = ["Ana", "Luis", "María", "José", "Carmen", "Jorge", "Lucía", "Pedro", "Sofía", "Diego",
           "Gabriela", "Andrés", "Valeria", "Miguel", "Daniela", "Fernando", "Paola", "Ricardo", "Elena", "Mario"]
APELLIDOS = ["López", "García", "Pérez", "Morales", "Hernández", "Castillo", "Ramírez", "Méndez", "Juárez",
             "Reyes", "Cifuentes", "Ajú", "Xicará", "Coc", "Barrios", "Estrada", "Monzón", "Chávez"]
PUESTOS = [("Vendedor de tienda", 4100, 4900, "CE2"), ("Cajero", 4300, 5100, "CE2"), ("Bodeguero", 4100, 4700, "CE2"),
           ("Asistente administrativo", 5200, 6500, "CE1"), ("Analista de Recursos Humanos", 7500, 9800, "CE1"),
           ("Analista contable", 7800, 10200, "CE1"), ("Gerente de tienda", 11000, 14500, "CE2")]


def build_db(n: int = 50, seed: int = 2026) -> None:
    rnd = random.Random(seed)
    config.EMPLOYEES_DB.parent.mkdir(parents=True, exist_ok=True)
    if config.EMPLOYEES_DB.exists():
        config.EMPLOYEES_DB.unlink()
    with _connect(readonly=False) as con:
        con.execute("""CREATE TABLE empleados (
            employee_id TEXT PRIMARY KEY, nombre TEXT, puesto TEXT, fecha_ingreso TEXT,
            salario_base TEXT, circunscripcion TEXT, ultima_fecha_vacaciones TEXT, dpi TEXT, email TEXT)""")
        for i in range(1, n + 1):
            puesto, lo, hi, ce = rnd.choice(PUESTOS)
            nombre = f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)} {rnd.choice(APELLIDOS)}"
            ingreso = date(2026, 6, 30) - timedelta(days=rnd.randint(120, 365 * 12))
            salario = Decimal(rnd.randrange(lo, hi, 50))
            # último goce de vacaciones: dentro de los 14 meses previos a jun-2026 (o ninguno registrado)
            ult_vac = date(2026, 6, 30) - timedelta(days=rnd.randint(30, 420)) if rnd.random() < 0.6 else None
            if ult_vac and ult_vac <= ingreso + timedelta(days=365):
                ult_vac = None
            dpi = f"{rnd.randint(1000, 9999)}{rnd.randint(10000, 99999)}{rnd.randint(101, 2299):04d}"
            email = f"{nombre.split()[0].lower()}.{i:03d}@comercialdemo.example"
            con.execute("INSERT INTO empleados VALUES (?,?,?,?,?,?,?,?,?)",
                        (f"E-{i:03d}", nombre, puesto, ingreso.isoformat(), str(salario), ce,
                         ult_vac.isoformat() if ult_vac else None, dpi, email))
