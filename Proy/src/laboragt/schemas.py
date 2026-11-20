"""Contratos de datos (Pydantic): chunk indexado, consulta y respuesta del sistema."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from . import config


class UserRole(str, Enum):
    COLABORADOR = "colaborador"
    RRHH = "rrhh"
    ADMIN = "admin"


class AccessLevel(str, Enum):
    PUBLICO = "publico"
    INTERNO = "interno"
    CONFIDENCIAL = "confidencial"


# Qué niveles de acceso puede leer cada rol
ROLE_ACCESS: dict[UserRole, set[AccessLevel]] = {
    UserRole.COLABORADOR: {AccessLevel.PUBLICO, AccessLevel.INTERNO},
    UserRole.RRHH: {AccessLevel.PUBLICO, AccessLevel.INTERNO, AccessLevel.CONFIDENCIAL},
    UserRole.ADMIN: {AccessLevel.PUBLICO, AccessLevel.INTERNO},
}


class Chunk(BaseModel):
    """Fragmento indexado con metadatos mínimos de trazabilidad (sección 5.3 del enunciado)."""

    chunk_id: str
    text: str
    source: str  # nombre del archivo
    doc_id: str
    doc_title: str
    page: int  # página (1-based) donde inicia el fragmento
    page_end: int
    article: str | None = None  # p. ej. "82", "82 BIS", "II"
    section: str | None = None  # título/capítulo vigente
    version: str
    vigencia_desde: str | None = None
    vigencia_hasta: str | None = None
    access_level: AccessLevel
    hash: str


class Query(BaseModel):
    question: str = Field(min_length=3, max_length=config.MAX_QUESTION_CHARS)
    role: UserRole = UserRole.COLABORADOR

    @field_validator("question")
    @classmethod
    def strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("pregunta vacía")
        return v


class SourceRef(BaseModel):
    source: str
    page: int
    chunk_id: str
    article: str | None = None
    doc_title: str | None = None


class LaboraResponse(BaseModel):
    """Formato de salida contractual (sección 11 del enunciado)."""

    answer: str
    sources: list[SourceRef] = Field(default_factory=list)
    abstained: bool
    tool_used: str | None = None
    needs_human_review: bool = False


class LLMDraft(BaseModel):
    """Lo que se le pide al LLM: solo texto y etiquetas de chunks citados.

    Las fuentes finales se reconstruyen desde los metadatos, nunca desde el texto generado.
    """

    answer: str
    cited_chunk_ids: list[str] = Field(max_length=3)  # obligatorio; maxItems evita listas desbocadas
    insufficient_evidence: bool
