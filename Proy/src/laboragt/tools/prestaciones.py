"""Herramienta determinista: cálculo de prestaciones laborales (Guatemala, sector privado).

Reglas implementadas (con su base legal, que también se cita en la respuesta):
- Indemnización (CT art. 82): 1 mes de salario por año de servicio continuo, proporcional en fracción.
  Base mensual = salario promedio de los últimos 6 meses + 1/12 de aguinaldo + 1/12 de Bono 14
  (Decreto 76-78 art. 9 y Decreto 42-92 art. 4: proporción de seis meses de cada prestación).
- Aguinaldo (Decreto 76-78 arts. 1-2): 100 % del salario mensual por año; período 1-dic a 30-nov.
- Bono 14 (Decreto 42-92 arts. 1-3): 100 % del salario mensual por año; período 1-jul a 30-jun.
- Vacaciones (CT arts. 130 y 133): 15 días hábiles por año; proporcionales si no se gozaron.
Supuestos: año de 365 días; salario diario = salario mensual / 30; las vacaciones pendientes se
calculan desde la última fecha de goce (o desde el ingreso si no se indica).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator

Q = Decimal("0.01")


class Motivo(str, Enum):
    DESPIDO_INJUSTIFICADO = "despido_injustificado"
    DESPIDO_JUSTIFICADO = "despido_justificado"
    RENUNCIA = "renuncia"


class TipoCalculo(str, Enum):
    INDEMNIZACION = "indemnizacion"
    AGUINALDO = "aguinaldo"
    BONO14 = "bono14"
    VACACIONES = "vacaciones"
    LIQUIDACION = "liquidacion"  # suma de todo lo que corresponda según el motivo


class PrestacionesInput(BaseModel):
    tipo: TipoCalculo
    salario_mensual: Decimal = Field(gt=0, le=100_000, description="Salario ordinario mensual promedio (Q)")
    fecha_inicio: date
    fecha_fin: date
    motivo: Motivo = Motivo.DESPIDO_INJUSTIFICADO
    ultima_fecha_vacaciones: date | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.fecha_fin < self.fecha_inicio:
            raise ValueError("fecha_fin no puede ser anterior a fecha_inicio")
        if self.fecha_inicio.year < 1950:
            raise ValueError("fecha_inicio fuera de rango")
        if self.fecha_fin > date.today() + timedelta(days=366):
            raise ValueError("fecha_fin demasiado lejana en el futuro")
        if (self.fecha_fin - self.fecha_inicio).days > 365 * 60:
            raise ValueError("relación laboral mayor a 60 años: revisar fechas")
        return self


class Concepto(BaseModel):
    concepto: str
    monto: Decimal
    formula: str
    base_legal: str


class PrestacionesResult(BaseModel):
    conceptos: list[Concepto]
    total: Decimal
    dias_laborados: int
    supuestos: list[str]
    base_legal_refs: list[tuple[str, str]]  # (doc_id, artículo) para recuperar citas


def _r(x: Decimal) -> Decimal:
    return x.quantize(Q, rounding=ROUND_HALF_UP)


def _dias(a: date, b: date) -> int:
    return (b - a).days + 1  # inclusivo


def _periodo_inicio(fin: date, mes: int, dia: int) -> date:
    """Inicio del período anual (p. ej. 1-dic para aguinaldo) que contiene la fecha fin."""
    inicio = date(fin.year, mes, dia)
    return inicio if inicio <= fin else date(fin.year - 1, mes, dia)


def indemnizacion(inp: PrestacionesInput) -> Concepto:
    base = inp.salario_mensual * Decimal(14) / Decimal(12)
    dias = _dias(inp.fecha_inicio, inp.fecha_fin)
    monto = _r(base * Decimal(dias) / Decimal(365))
    return Concepto(concepto="Indemnización por tiempo servido", monto=monto,
                    formula=f"(Q{inp.salario_mensual} × 14/12) × {dias}/365 días",
                    base_legal="Código de Trabajo art. 82; Decreto 76-78 art. 9; Decreto 42-92 art. 4")


def aguinaldo(inp: PrestacionesInput) -> Concepto:
    ini = max(_periodo_inicio(inp.fecha_fin, 12, 1), inp.fecha_inicio)
    dias = _dias(ini, inp.fecha_fin)
    monto = _r(inp.salario_mensual * Decimal(dias) / Decimal(365))
    return Concepto(concepto="Aguinaldo proporcional", monto=monto,
                    formula=f"Q{inp.salario_mensual} × {dias}/365 (del {ini:%d/%m/%Y} al {inp.fecha_fin:%d/%m/%Y})",
                    base_legal="Decreto 76-78 arts. 1 y 2")


def bono14(inp: PrestacionesInput) -> Concepto:
    ini = max(_periodo_inicio(inp.fecha_fin, 7, 1), inp.fecha_inicio)
    dias = _dias(ini, inp.fecha_fin)
    monto = _r(inp.salario_mensual * Decimal(dias) / Decimal(365))
    return Concepto(concepto="Bono 14 proporcional", monto=monto,
                    formula=f"Q{inp.salario_mensual} × {dias}/365 (del {ini:%d/%m/%Y} al {inp.fecha_fin:%d/%m/%Y})",
                    base_legal="Decreto 42-92 arts. 1, 2 y 3")


def _ultimo_aniversario(inicio: date, fin: date) -> date:
    years = fin.year - inicio.year
    for y in (years, years - 1):
        try:
            d = inicio.replace(year=inicio.year + y)
        except ValueError:  # 29 de febrero
            d = date(inicio.year + y, 2, 28)
        if inicio <= d <= fin:
            return d
    return inicio


def vacaciones(inp: PrestacionesInput) -> Concepto:
    # Sin fecha de último goce se asume que los períodos anteriores se gozaron y se compensa
    # la parte proporcional del período en curso (CT art. 133).
    desde = inp.ultima_fecha_vacaciones or _ultimo_aniversario(inp.fecha_inicio, inp.fecha_fin)
    desde = max(desde, inp.fecha_inicio)
    dias = _dias(desde, inp.fecha_fin)
    dias_vac = Decimal(15) * Decimal(dias) / Decimal(365)
    diario = inp.salario_mensual / Decimal(30)
    monto = _r(dias_vac * diario)
    return Concepto(concepto="Vacaciones no gozadas (proporcionales)", monto=monto,
                    formula=f"15 días × {dias}/365 = {dias_vac.quantize(Q)} días × (Q{inp.salario_mensual}/30)",
                    base_legal="Código de Trabajo arts. 130 y 133")


REFS = {
    "indemnizacion": [("codigo_trabajo", "82"), ("ley_aguinaldo", "9"), ("ley_bono14", "4")],
    "aguinaldo": [("ley_aguinaldo", "1"), ("ley_aguinaldo", "2")],
    "bono14": [("ley_bono14", "2"), ("ley_bono14", "3")],
    "vacaciones": [("codigo_trabajo", "130"), ("codigo_trabajo", "133")],
}


def calcular_prestaciones(inp: PrestacionesInput) -> PrestacionesResult:
    t = inp.tipo
    conceptos: list[Concepto] = []
    refs: list[tuple[str, str]] = []
    supuestos = ["Año de 365 días; salario diario = mensual/30.",
                 "Se usa el salario mensual indicado como promedio de los últimos 6 meses."]
    if t in (TipoCalculo.INDEMNIZACION, TipoCalculo.LIQUIDACION):
        if inp.motivo == Motivo.DESPIDO_INJUSTIFICADO:
            conceptos.append(indemnizacion(inp))
            refs += REFS["indemnizacion"]
        elif t == TipoCalculo.INDEMNIZACION:
            supuestos.append(f"Con motivo '{inp.motivo.value}' no corresponde indemnización (CT art. 82).")
            refs += REFS["indemnizacion"][:1]
    if t in (TipoCalculo.AGUINALDO, TipoCalculo.LIQUIDACION):
        conceptos.append(aguinaldo(inp))
        refs += REFS["aguinaldo"]
    if t in (TipoCalculo.BONO14, TipoCalculo.LIQUIDACION):
        conceptos.append(bono14(inp))
        refs += REFS["bono14"]
    if t in (TipoCalculo.VACACIONES, TipoCalculo.LIQUIDACION):
        conceptos.append(vacaciones(inp))
        refs += REFS["vacaciones"]
        if inp.ultima_fecha_vacaciones is None:
            supuestos.append("No se indicó la última fecha de goce de vacaciones: se asumió que los períodos "
                             "anteriores se gozaron y se compensa el período en curso desde el último aniversario.")
    total = _r(sum((c.monto for c in conceptos), Decimal(0)))
    return PrestacionesResult(conceptos=conceptos, total=total,
                              dias_laborados=_dias(inp.fecha_inicio, inp.fecha_fin),
                              supuestos=supuestos, base_legal_refs=list(dict.fromkeys(refs)))
