"""Índice léxico BM25 (línea base). Tokenización en español sin tildes, con stopwords."""
from __future__ import annotations

import pickle
import re
import unicodedata
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from .. import config
from ..schemas import ROLE_ACCESS, Chunk, UserRole

STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del
desde donde durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto
estos fue fueron ha han hasta hay la las le les lo los mas me mi mis muy ni no nos o os otra otras
otro otros para pero poco por porque que quien quienes se sea segun ser si sido sin sobre solo su
sus tambien tan tanto te tiene tienen todo todos tu tus un una uno unos y ya yo cuanto cuanta
cuantos cuantas debe deben puede pueden cual
""".split())

TOKEN_RX = re.compile(r"[a-z0-9]+(?:-[0-9]+)?")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def tokenize(text: str) -> list[str]:
    toks = TOKEN_RX.findall(strip_accents(text.lower()))
    out = []
    for t in toks:
        if t in STOPWORDS or (len(t) == 1 and not t.isdigit()):
            continue
        # plural simple: "vacaciones" -> "vacacion", "trabajadores" -> "trabajador"
        if not t[0].isdigit() and len(t) > 4:
            if t.endswith("es") and t[-3] in "nrldz":
                t = t[:-2]
            elif t.endswith("s"):
                t = t[:-1]
        out.append(t)
    return out


@dataclass
class Hit:
    chunk: Chunk
    score: float
    rank: int


class BM25Index:
    PATH = config.INDEX_DIR / "bm25.pkl"

    def __init__(self, chunks: list[Chunk], bm25: BM25Okapi):
        self.chunks = chunks
        self.bm25 = bm25

    @classmethod
    def build(cls, chunks: list[Chunk]) -> "BM25Index":
        corpus = [tokenize(c.text) for c in chunks]
        return cls(chunks, BM25Okapi(corpus, k1=1.5, b=0.75))

    def save(self) -> None:
        config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.PATH, "wb") as f:
            pickle.dump({"chunks": [c.model_dump() for c in self.chunks], "bm25": self.bm25}, f)

    @classmethod
    def load(cls) -> "BM25Index":
        with open(cls.PATH, "rb") as f:
            d = pickle.load(f)
        return cls([Chunk(**c) for c in d["chunks"]], d["bm25"])

    def search(self, query: str, role: UserRole, k: int = config.TOP_K) -> list[Hit]:
        """Búsqueda con filtro obligatorio de acceso por rol (se aplica ANTES de devolver texto)."""
        allowed = ROLE_ACCESS[role]
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[Hit] = []
        for i in order:
            if self.chunks[i].access_level not in allowed:
                continue
            if scores[i] <= 0:
                break
            hits.append(Hit(self.chunks[i], float(scores[i]), len(hits) + 1))
            if len(hits) >= k:
                break
        return hits
