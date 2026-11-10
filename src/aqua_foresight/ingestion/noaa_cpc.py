"""Adaptador NOAA/CPC — RONI (índice ENOS operacional do CPC desde 01/02/2026) e ONI legado.

Fontes oficiais (texto plano):
- RONI: https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt
- ONI (legado, mantido pelo CPC para continuidade): https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt

Formato: uma linha de cabeçalho e linhas "ESTACAO ANO [TOTAL] ANOMALIA".
O RONI tem 3 colunas; o ONI tem 4 (inclui a média absoluta TOTAL).
Base de anomalias informada pelo CPC para o RONI: 1991–2020.

O CPC informa que os valores mais recentes são estimativas e podem mudar por até
dois meses após a publicação inicial; por isso as duas últimas estações de cada
arquivo são gravadas como `estimado_provisorio`, e cada carga é um vintage novo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aqua_foresight.config import Settings
from aqua_foresight.db.models import FonteDado, IndiceENOS, Ingestao, RegistroAuditoria
from aqua_foresight.enso.phases import ESTACOES, MES_CENTRAL, PontoENOS
from aqua_foresight.ingestion import provenance

FONTES_CPC = {
    "RONI": {
        "id": "noaa_cpc_roni",
        "nome": "Relative Oceanic Niño Index (RONI)",
        "url": "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
        "periodo_base": "1991-2020",
        "arquivo": "RONI.ascii.txt",
    },
    "ONI": {
        "id": "noaa_cpc_oni",
        "nome": "Oceanic Niño Index (ONI) — legado",
        "url": "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
        "periodo_base": None,  # base móvel por períodos de 30 anos; não fixar aqui
        "arquivo": "oni.ascii.txt",
    },
}

N_ESTACOES_PROVISORIAS = 2


class ErroFormatoCPC(ValueError):
    pass


@dataclass(frozen=True)
class LinhaCPC:
    estacao: str
    ano: int
    anomalia: float


def parse_cpc_ascii(texto: str) -> list[LinhaCPC]:
    linhas: list[LinhaCPC] = []
    for n, bruto in enumerate(texto.splitlines(), start=1):
        partes = bruto.split()
        if not partes:
            continue
        if partes[0].upper() not in ESTACOES:
            if n == 1 or not linhas:
                continue  # cabeçalho
            raise ErroFormatoCPC(f"linha {n}: estação inválida {partes[0]!r}")
        if len(partes) not in (3, 4):
            raise ErroFormatoCPC(f"linha {n}: esperado 3 ou 4 colunas, obtido {len(partes)}")
        try:
            ano = int(partes[1])
            anomalia = float(partes[-1])
        except ValueError as exc:
            raise ErroFormatoCPC(f"linha {n}: valor não numérico ({bruto!r})") from exc
        if not (1850 <= ano <= 2100):
            raise ErroFormatoCPC(f"linha {n}: ano fora de faixa ({ano})")
        if not (-10.0 <= anomalia <= 10.0):
            raise ErroFormatoCPC(f"linha {n}: anomalia implausível ({anomalia})")
        linhas.append(LinhaCPC(partes[0].upper(), ano, anomalia))
    if not linhas:
        raise ErroFormatoCPC("arquivo sem linhas de dados")
    _checar_continuidade(linhas)
    return linhas


def _checar_continuidade(linhas: list[LinhaCPC]) -> None:
    chaves = [l.ano * 12 + MES_CENTRAL[l.estacao] for l in linhas]
    for a, b, linha in zip(chaves, chaves[1:], linhas[1:]):
        if b - a != 1:
            raise ErroFormatoCPC(
                f"descontinuidade antes de {linha.estacao}/{linha.ano} (série deve ser mensal contínua)"
            )


def garantir_fonte(session: Session, indicador: str) -> FonteDado:
    meta = FONTES_CPC[indicador]
    fonte = session.get(FonteDado, meta["id"])
    if fonte is None:
        fonte = FonteDado(
            id=meta["id"],
            nome=meta["nome"],
            orgao="NOAA / NCEP Climate Prediction Center",
            url=meta["url"],
            tipo_acesso="arquivo",
            licenca="Dado público do governo dos EUA (confirmar termos de uso)",
            frequencia_declarada="mensal",
            status_conector="nao_verificado",
        )
        session.add(fonte)
        session.flush()
    return fonte


@dataclass
class ResultadoIngestao:
    ingestao_id: int
    status: str
    n_registros: int
    sha256: str | None
    duplicado_de: int | None
    mensagem: str | None


def ingerir_indice_cpc(
    session: Session,
    settings: Settings,
    indicador: str = "RONI",
    arquivo_local: Path | None = None,
    sintetico: bool = False,
) -> ResultadoIngestao:
    """Baixa (ou lê arquivo local), preserva o bruto, valida e grava um novo vintage.

    Se o conteúdo for idêntico (mesmo SHA-256) ao último vintage bem-sucedido, nenhuma
    linha nova é criada; a ingestão é registrada como `sucesso` com referência ao anterior.
    """
    if indicador not in FONTES_CPC:
        raise ValueError(f"indicador não suportado: {indicador}")
    meta = FONTES_CPC[indicador]
    fonte = garantir_fonte(session, indicador)

    modo = "arquivo_local" if arquivo_local else "download"
    origem = str(arquivo_local) if arquivo_local else meta["url"]
    ing = Ingestao(fonte_id=fonte.id, modo=modo, origem=origem, sintetico=sintetico)
    session.add(ing)
    session.flush()

    try:
        conteudo = (
            provenance.ler_local(arquivo_local)
            if arquivo_local
            else provenance.baixar(meta["url"], settings.http_timeout)
        )
        ing.sha256 = provenance.sha256_bytes(conteudo)
        ing.bytes_brutos = len(conteudo)
        ing.caminho_bruto = str(
            provenance.preservar_bruto(conteudo, settings.raw_dir, fonte.id, meta["arquivo"])
        )
        linhas = parse_cpc_ascii(conteudo.decode("utf-8", errors="strict"))
    except Exception as exc:  # falha registrada, nunca silenciosa (RNF-07)
        ing.status = "falha"
        ing.mensagem = f"{type(exc).__name__}: {exc}"
        ing.concluida_em = datetime.now(timezone.utc)
        if modo == "download":
            fonte.status_conector = "falha"
            fonte.ultima_verificacao = ing.concluida_em
        _auditar(session, "ingestao_falha", ing)
        return ResultadoIngestao(ing.id, "falha", 0, ing.sha256, None, ing.mensagem)

    anterior = session.scalar(
        select(Ingestao)
        .where(
            Ingestao.fonte_id == fonte.id,
            Ingestao.status == "sucesso",
            Ingestao.sha256 == ing.sha256,
            Ingestao.sintetico == sintetico,
            Ingestao.id != ing.id,
        )
        .order_by(Ingestao.id.desc())
    )
    ing.concluida_em = datetime.now(timezone.utc)
    if modo == "download":
        fonte.status_conector = "verificado"
        fonte.ultima_verificacao = ing.concluida_em

    if anterior is not None:
        ing.status = "sucesso"
        ing.n_registros = 0
        ing.mensagem = f"conteúdo idêntico ao vintage da ingestão {anterior.id}; nada novo gravado"
        _auditar(session, "ingestao_sem_mudanca", ing)
        return ResultadoIngestao(ing.id, "sucesso", 0, ing.sha256, anterior.id, ing.mensagem)

    corte_provisorio = len(linhas) - N_ESTACOES_PROVISORIAS
    for idx, l in enumerate(linhas):
        if sintetico:
            natureza = "sintetico"
        elif idx >= corte_provisorio:
            natureza = "estimado_provisorio"
        else:
            natureza = "observado"
        session.add(
            IndiceENOS(
                indicador=indicador,
                ano=l.ano,
                estacao=l.estacao,
                mes_central=MES_CENTRAL[l.estacao],
                valor=l.anomalia,
                unidade="degC",
                periodo_base=meta["periodo_base"],
                natureza=natureza,
                ingestao_id=ing.id,
            )
        )
    ing.status = "sucesso"
    ing.n_registros = len(linhas)
    _auditar(session, "ingestao_sucesso", ing)
    return ResultadoIngestao(ing.id, "sucesso", len(linhas), ing.sha256, None, None)


def vintage_vigente(
    session: Session, indicador: str = "RONI", ate: datetime | None = None, incluir_sintetico: bool = False
) -> int | None:
    """ID da ingestão com linhas mais recente (opcionalmente até uma data: visão point-in-time)."""
    fonte_id = FONTES_CPC[indicador]["id"]
    q = (
        select(Ingestao.id)
        .where(Ingestao.fonte_id == fonte_id, Ingestao.status == "sucesso", Ingestao.n_registros > 0)
        .order_by(Ingestao.concluida_em.desc(), Ingestao.id.desc())
    )
    if not incluir_sintetico:
        q = q.where(Ingestao.sintetico.is_(False))
    if ate is not None:
        q = q.where(Ingestao.concluida_em <= ate)
    return session.scalar(q.limit(1))


def carregar_serie(session: Session, ingestao_id: int, indicador: str = "RONI") -> list[IndiceENOS]:
    return list(
        session.scalars(
            select(IndiceENOS)
            .where(IndiceENOS.ingestao_id == ingestao_id, IndiceENOS.indicador == indicador)
            .order_by(IndiceENOS.ano, IndiceENOS.mes_central)
        )
    )


def como_pontos(linhas: list[IndiceENOS]) -> list[PontoENOS]:
    return [PontoENOS(l.ano, l.estacao, l.valor) for l in linhas]


def contar_vintages(session: Session, indicador: str = "RONI") -> int:
    return session.scalar(
        select(func.count(func.distinct(IndiceENOS.ingestao_id))).where(IndiceENOS.indicador == indicador)
    ) or 0


def _auditar(session: Session, acao: str, ing: Ingestao) -> None:
    session.add(
        RegistroAuditoria(
            ator="sistema",
            acao=acao,
            entidade="ingestao",
            entidade_id=str(ing.id),
            detalhes={
                "fonte": ing.fonte_id,
                "modo": ing.modo,
                "origem": ing.origem,
                "sha256": ing.sha256,
                "n_registros": ing.n_registros,
                "sintetico": ing.sintetico,
                "mensagem": ing.mensagem,
            },
        )
    )
