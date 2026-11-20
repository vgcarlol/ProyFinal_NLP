import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from pydantic import ValidationError

from laboragt.ingest.chunker import ARTICLE_RX, split_units
from laboragt.ingest.clean import clean_pages, normalize
from laboragt.ingest.extract import PageText
from laboragt.retrieval.bm25 import BM25Index, tokenize
from laboragt.schemas import AccessLevel, Chunk, LaboraResponse, Query, UserRole
from laboragt.trace import mask_pii


# ---------- chunking ----------
@pytest.mark.parametrize("line,art", [
    ("ARTÍCULO 82.", "82"),
    ("ARTÍCULO 15 BIS.", "15 BIS"),
    ("ARTÍCULO II.", "II"),
    ("Ú A e ARTÍCULO 3. Salario Mínimo para las Actividades", "3"),  # ruido de OCR
    ("Artículo 9o. Para el cálculo de la indemnización", "9"),
])
def test_article_headers(line, art):
    m = ARTICLE_RX.match(line)
    assert m and m.group(1) == art


@pytest.mark.parametrize("line", ["y d) del Artículo 82.", "Artículo 82 del Código de Trabajo", "artículos 101, 102"])
def test_internal_references_are_not_headers(line):
    assert ARTICLE_RX.match(line) is None


def test_split_units_keeps_article_and_page():
    pages = [PageText(1, "ARTÍCULO 1.\nTexto uno.\n\n2", False), PageText(2, "ARTÍCULO 2.\nTexto dos.", False)]
    units = split_units(clean_pages(pages))
    assert [(u.article, u.page) for u in units] == [("1", 1), ("2", 2)]
    assert "2" not in units[0].text.split()  # número de página eliminado como ruido


def test_clean_start_marker_drops_foreign_decree():
    pages = [PageText(1, "DECRETO NUMERO 36-2001\nimpuestos\nDECRETO NUMERO 37-2001\nARTICULO 1. bonificación", False)]
    lines = clean_pages(pages, start_regex="DECRETO NUMERO 37-2001")
    assert all("impuestos" not in l for _, l in lines)


def test_normalize_hyphenation_and_ligatures():
    assert normalize("traba-\njador ﬁnal") == "trabajador final"


# ---------- recuperación ----------
def test_tokenize_strips_accents_stopwords_and_plurals():
    assert tokenize("¿Cuántas vacaciones tienen los trabajadores?") == ["vacacion", "trabajador"]
    assert "37-2001" in tokenize("Decreto 37-2001")


def _chunk(cid, text, level):
    return Chunk(chunk_id=cid, text=text, source="x.pdf", doc_id=cid.split("-")[0], doc_title="t", page=1,
                 page_end=1, version="1", access_level=level, hash="h")


def test_role_filter_blocks_confidential_for_colaborador():
    idx = BM25Index.build([
        _chunk("pub-1", "vacaciones quince días hábiles", AccessLevel.PUBLICO),
        _chunk("conf-1", "banda salarial gerente confidencial", AccessLevel.CONFIDENCIAL),
        _chunk("int-1", "uniforme tiendas", AccessLevel.INTERNO),
    ])
    assert idx.search("banda salarial gerente", UserRole.COLABORADOR) == []
    assert idx.search("banda salarial gerente", UserRole.RRHH)[0].chunk.chunk_id == "conf-1"


# ---------- contratos y seguridad ----------
def test_query_validation():
    with pytest.raises(ValidationError):
        Query(question="x" * 600)
    with pytest.raises(ValidationError):
        Query(question="  ")
    assert Query(question="  hola   mundo ").question == "hola mundo"


def test_response_schema_fields():
    r = LaboraResponse(answer="a", abstained=True)
    assert set(r.model_dump()) == {"answer", "sources", "abstained", "tool_used", "needs_human_review"}


def test_pii_masking():
    s = mask_pii("DPI 2345 67890 0101, correo ana@demo.com, tel 5555-1234")
    assert "[DPI]" in s and "[EMAIL]" in s and "[TEL]" in s and "ana@" not in s
