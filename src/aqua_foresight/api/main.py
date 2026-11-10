"""API FastAPI mínima. Documentação interativa em /docs (OpenAPI)."""

from __future__ import annotations

from datetime import date
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from aqua_foresight import __version__
from aqua_foresight.config import get_settings
from aqua_foresight.db import init_db, make_engine, make_session_factory
from aqua_foresight.db.models import FonteDado, Ingestao, LimiarEstadoHidrologico, NormaJuridica, RegistroAuditoria
from aqua_foresight.enso.phases import classificar_fases
from aqua_foresight.ingestion import noaa_cpc
from aqua_foresight.legal.enquadramento import enquadrar
from aqua_foresight.legal.seed import carregar_base_normativa


class EnquadramentoIn(BaseModel):
    reservatorio_id: str = Field(examples=["descoberto"])
    data_referencia: date
    valor_pct: float = Field(description="Volume útil em %")
    natureza: Literal["observado", "projetado"]
    data_dado: date | None = None


def create_app(session_factory: sessionmaker[Session] | None = None) -> FastAPI:
    if session_factory is None:
        engine = make_engine()
        init_db(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as s:
            carregar_base_normativa(s)
            s.commit()

    app = FastAPI(
        title="Aqua Foresight API",
        version=__version__,
        description=(
            "Sistema de apoio à decisão. Nenhum endpoint emite atos administrativos; "
            "resultados de enquadramento são indicativos e exigem revisão humana."
        ),
    )

    def get_session() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    @app.get("/health")
    def health(s: Session = Depends(get_session)) -> dict:
        s.execute(select(1))
        return {"status": "ok", "versao": __version__}

    @app.get("/fontes")
    def fontes(s: Session = Depends(get_session)) -> list[dict]:
        out = []
        for f in s.scalars(select(FonteDado).order_by(FonteDado.id)):
            ultima = s.scalar(
                select(Ingestao).where(Ingestao.fonte_id == f.id).order_by(Ingestao.id.desc()).limit(1)
            )
            out.append(
                {
                    "id": f.id,
                    "nome": f.nome,
                    "orgao": f.orgao,
                    "url": f.url,
                    "status_conector": f.status_conector,
                    "ultima_verificacao": f.ultima_verificacao,
                    "ultima_ingestao": None
                    if ultima is None
                    else {
                        "id": ultima.id,
                        "status": ultima.status,
                        "modo": ultima.modo,
                        "concluida_em": ultima.concluida_em,
                        "sha256": ultima.sha256,
                        "n_registros": ultima.n_registros,
                        "sintetico": ultima.sintetico,
                        "mensagem": ultima.mensagem,
                    },
                }
            )
        return out

    @app.get("/enos/{indicador}")
    def enos(
        indicador: Literal["RONI", "ONI"],
        ultimos: int = Query(24, ge=1, le=2000),
        incluir_sintetico: bool = False,
        s: Session = Depends(get_session),
    ) -> dict:
        vid = noaa_cpc.vintage_vigente(s, indicador, incluir_sintetico=incluir_sintetico)
        if vid is None:
            raise HTTPException(404, f"Nenhum vintage de {indicador} ingerido. Rode `aqua ingest-enos`.")
        linhas = noaa_cpc.carregar_serie(s, vid, indicador)
        fases = classificar_fases(noaa_cpc.como_pontos(linhas))
        ing = s.get(Ingestao, vid)
        serie = [
            {
                "ano": l.ano,
                "estacao": l.estacao,
                "mes_central": l.mes_central,
                "valor": l.valor,
                "unidade": l.unidade,
                "natureza": l.natureza,
                "condicao": f.condicao,
                "episodio": f.episodio,
                "episodio_confirmado": f.episodio_confirmado,
            }
            for l, f in zip(linhas, fases)
        ][-ultimos:]
        return {
            "indicador": indicador,
            "fonte": ing.fonte_id,
            "origem": ing.origem,
            "ingestao_id": vid,
            "ingerido_em": ing.concluida_em,
            "sha256": ing.sha256,
            "sintetico": ing.sintetico,
            "periodo_base": linhas[0].periodo_base if linhas else None,
            "criterio_fase": "CPC: |índice| >= 0,5 °C por >= 5 estações trimestrais consecutivas",
            "aviso": "Fase oceânica do ENOS; impacto no DF é hipótese em teste, não premissa.",
            "serie": serie,
        }

    @app.get("/normas")
    def normas(s: Session = Depends(get_session)) -> list[dict]:
        return [
            {
                "id": n.id,
                "jurisdicao": n.jurisdicao,
                "titulo": n.titulo,
                "orgao_emissor": n.orgao_emissor,
                "publicacao": n.publicacao,
                "vigencia_status": n.vigencia_status,
                "status_verificacao": n.status_verificacao,
                "fontes": n.fontes,
            }
            for n in s.scalars(select(NormaJuridica))
        ]

    @app.get("/limiares/{reservatorio_id}")
    def limiares(reservatorio_id: str, s: Session = Depends(get_session)) -> dict:
        rows = list(
            s.scalars(
                select(LimiarEstadoHidrologico)
                .where(LimiarEstadoHidrologico.reservatorio_id == reservatorio_id)
                .order_by(LimiarEstadoHidrologico.mes, LimiarEstadoHidrologico.estado)
            )
        )
        if not rows:
            raise HTTPException(404, "Reservatório sem limiares cadastrados.")
        meses: dict[int, dict] = {}
        for r in rows:
            meses.setdefault(r.mes, {"mes": r.mes})[r.estado] = r.limite_pct
        return {
            "reservatorio_id": reservatorio_id,
            "norma_id": rows[0].norma_id,
            "dispositivo": rows[0].dispositivo,
            "comparador": "<",
            "unidade": "% do volume útil",
            "meses": [meses[m] for m in sorted(meses)],
        }

    @app.post("/enquadramento")
    def post_enquadramento(body: EnquadramentoIn, s: Session = Depends(get_session)) -> dict:
        res = enquadrar(
            s,
            reservatorio_id=body.reservatorio_id,
            data_referencia=body.data_referencia,
            valor_pct=body.valor_pct,
            natureza=body.natureza,
            data_dado=body.data_dado,
            max_defasagem_dias=get_settings().max_defasagem_observacao_dias,
            ator="api",
        )
        return res.as_dict()

    @app.get("/auditoria")
    def auditoria(limite: int = Query(50, ge=1, le=1000), s: Session = Depends(get_session)) -> list[dict]:
        return [
            {
                "id": r.id,
                "ocorrido_em": r.ocorrido_em,
                "ator": r.ator,
                "acao": r.acao,
                "entidade": r.entidade,
                "entidade_id": r.entidade_id,
                "detalhes": r.detalhes,
            }
            for r in s.scalars(select(RegistroAuditoria).order_by(RegistroAuditoria.id.desc()).limit(limite))
        ]

    return app


def app_factory() -> FastAPI:  # usado por `uvicorn --factory`
    return create_app()
