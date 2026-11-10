"""Fixtures de teste.

ATENÇÃO: todos os valores de ENOS gerados aqui são SINTÉTICOS, construídos apenas para
exercitar o parser e o classificador. Não representam observações do NOAA/CPC.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aqua_foresight.config import Settings
from aqua_foresight.db import Base, init_db, make_engine, make_session_factory
from aqua_foresight.db import models  # noqa: F401  (registra tabelas para drop_all)
from aqua_foresight.enso.phases import ESTACOES
from aqua_foresight.legal.seed import carregar_base_normativa

# 24 estações sintéticas a partir de DJF/2000: neutro(4) -> quente(6) -> neutro(5) -> frio(4) -> neutro(3) -> quente(2, em curso)
VALORES_SINTETICOS = [
    0.1, -0.2, 0.3, 0.4,
    0.5, 0.8, 1.2, 1.5, 1.1, 0.6,
    0.4, 0.0, -0.3, -0.4, 0.2,
    -0.5, -0.7, -0.9, -0.6,
    -0.4, 0.1, 0.3,
    0.6, 0.9,
]


def texto_cpc_sintetico(valores=VALORES_SINTETICOS, ano0=2000, quatro_colunas=False) -> str:
    cab = "SEAS  YR   TOTAL   ANOM" if quatro_colunas else "SEAS  YR   ANOM"
    linhas = [cab]
    for i, v in enumerate(valores):
        est = ESTACOES[i % 12]
        ano = ano0 + i // 12
        if quatro_colunas:
            linhas.append(f"  {est} {ano}  {26.5 + v:6.2f}  {v:6.2f}")
        else:
            linhas.append(f"  {est} {ano}  {v:6.2f}")
    return "\n".join(linhas) + "\n"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # AQUA_TEST_DATABASE_URL permite rodar a mesma suíte contra PostgreSQL real.
    url = os.environ.get("AQUA_TEST_DATABASE_URL") or f"sqlite:///{tmp_path}/teste.db"
    return Settings(database_url=url, raw_dir=tmp_path / "raw")


@pytest.fixture
def factory(settings: Settings):
    engine = make_engine(settings.database_url)
    if not settings.database_url.startswith("sqlite"):
        Base.metadata.drop_all(engine)
    init_db(engine)
    f = make_session_factory(engine)
    with f() as s:
        carregar_base_normativa(s)
        s.commit()
    return f


@pytest.fixture
def session(factory):
    s = factory()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def arquivo_sintetico(tmp_path: Path) -> Path:
    p = tmp_path / "RONI_SINTETICO.ascii.txt"
    p.write_text(texto_cpc_sintetico())
    return p
