"""Carga idempotente da base normativa e dos reservatórios do piloto."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqua_foresight.db.models import LimiarEstadoHidrologico, NormaJuridica, RegistroAuditoria, Reservatorio
from aqua_foresight.legal import adasa_56_2025 as adasa


def carregar_base_normativa(session: Session) -> dict[str, int]:
    criados = {"reservatorios": 0, "normas": 0, "limiares": 0}
    for r in adasa.RESERVATORIOS:
        if session.get(Reservatorio, r["id"]) is None:
            session.add(Reservatorio(**r))
            criados["reservatorios"] += 1
    if session.get(NormaJuridica, adasa.NORMA_ID) is None:
        session.add(NormaJuridica(**adasa.NORMA))
        criados["normas"] += 1
    session.flush()

    existentes = {
        (l.reservatorio_id, l.mes, l.estado)
        for l in session.scalars(
            select(LimiarEstadoHidrologico).where(LimiarEstadoHidrologico.norma_id == adasa.NORMA_ID)
        )
    }
    for linha in adasa.limiares_linhas():
        chave = (linha["reservatorio_id"], linha["mes"], linha["estado"])
        if chave not in existentes:
            session.add(LimiarEstadoHidrologico(**linha))
            criados["limiares"] += 1

    if any(criados.values()):
        session.add(
            RegistroAuditoria(
                ator="sistema",
                acao="base_normativa_carregada",
                entidade="norma_juridica",
                entidade_id=adasa.NORMA_ID,
                detalhes=criados,
            )
        )
    return criados
