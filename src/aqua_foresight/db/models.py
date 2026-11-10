"""Modelo lógico mínimo — Especificação v2.0, §5.1, com ajustes desta implementação.

Princípios aplicados:
- Proveniência: toda linha de dado aponta para a `Ingestao` que a trouxe (vintage).
- Vintages preservados: revisões retroativas da fonte NÃO sobrescrevem o histórico;
  uma nova ingestão cria novas linhas. Isso permite reconstruir "o que se sabia" em
  qualquer data e evita vazamento temporal na validação (Espec. §5.2 e §12).
- Natureza do dado explícita: observado / estimado_provisorio / projetado / sintetico.
- Geometrias (PostGIS) ainda não modeladas: entram com o Mapa de Bacias (Fase 6).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aqua_foresight.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FonteDado(Base):
    __tablename__ = "fonte_dado"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug, ex.: noaa_cpc_roni
    nome: Mapped[str] = mapped_column(String(255))
    orgao: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    tipo_acesso: Mapped[str] = mapped_column(String(32))  # arquivo | api | manual
    licenca: Mapped[str | None] = mapped_column(String(255))
    frequencia_declarada: Mapped[str | None] = mapped_column(String(64))
    # RF-05: conector sem teste bem-sucedido = "nao_verificado", nunca "conectado".
    status_conector: Mapped[str] = mapped_column(String(32), default="nao_verificado")
    ultima_verificacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacoes: Mapped[str | None] = mapped_column(Text)

    ingestoes: Mapped[list["Ingestao"]] = relationship(back_populates="fonte")


class Ingestao(Base):
    """Registro de proveniência de cada carga (arquivo bruto + checksum)."""

    __tablename__ = "ingestao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fonte_id: Mapped[str] = mapped_column(ForeignKey("fonte_dado.id"))
    iniciada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="iniciada")  # iniciada|sucesso|falha
    modo: Mapped[str] = mapped_column(String(16))  # download | arquivo_local
    origem: Mapped[str] = mapped_column(Text)  # URL ou caminho informado
    sha256: Mapped[str | None] = mapped_column(String(64))
    caminho_bruto: Mapped[str | None] = mapped_column(Text)
    bytes_brutos: Mapped[int | None] = mapped_column(Integer)
    n_registros: Mapped[int | None] = mapped_column(Integer)
    # Marcação de dado de teste/demonstração (Espec. §6: nunca mascarar sintético como real).
    sintetico: Mapped[bool] = mapped_column(Boolean, default=False)
    mensagem: Mapped[str | None] = mapped_column(Text)

    fonte: Mapped[FonteDado] = relationship(back_populates="ingestoes")


class IndiceENOS(Base):
    __tablename__ = "indice_enos"
    __table_args__ = (UniqueConstraint("indicador", "ano", "estacao", "ingestao_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicador: Mapped[str] = mapped_column(String(32))  # RONI | ONI
    ano: Mapped[int] = mapped_column(Integer)  # ano do mês central, conforme convenção CPC
    estacao: Mapped[str] = mapped_column(String(3))  # DJF, JFM, ..., NDJ
    mes_central: Mapped[int] = mapped_column(Integer)  # 1..12 (DJF -> 1)
    valor: Mapped[float] = mapped_column(Float)
    unidade: Mapped[str] = mapped_column(String(16), default="degC")
    periodo_base: Mapped[str | None] = mapped_column(String(32))  # ex.: 1991-2020
    natureza: Mapped[str] = mapped_column(String(24))  # observado | estimado_provisorio | sintetico
    ingestao_id: Mapped[int] = mapped_column(ForeignKey("ingestao.id"))


class Reservatorio(Base):
    __tablename__ = "reservatorio"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(255))
    uf: Mapped[str] = mapped_column(String(2))
    orgao_regulador: Mapped[str] = mapped_column(String(255))
    observacoes: Mapped[str | None] = mapped_column(Text)


class SerieObservada(Base):
    """Séries locais (volume útil, chuva, vazão...). Loader de volume útil: próxima etapa."""

    __tablename__ = "serie_observada"
    __table_args__ = (
        UniqueConstraint("local_tipo", "local_id", "indicador", "data_hora", "ingestao_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    local_tipo: Mapped[str] = mapped_column(String(16))  # reservatorio | estacao | subbacia
    local_id: Mapped[str] = mapped_column(String(64))
    indicador: Mapped[str] = mapped_column(String(64))  # ex.: volume_util_pct
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valor: Mapped[float | None] = mapped_column(Float)
    unidade: Mapped[str] = mapped_column(String(16))
    qualidade: Mapped[str | None] = mapped_column(String(32))
    natureza: Mapped[str] = mapped_column(String(24), default="observado")
    ingestao_id: Mapped[int] = mapped_column(ForeignKey("ingestao.id"))


class NormaJuridica(Base):
    __tablename__ = "norma_juridica"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # ex.: adasa_res_56_2025
    jurisdicao: Mapped[str] = mapped_column(String(32))  # BR-DF, BR, ES, UE
    titulo: Mapped[str] = mapped_column(Text)
    orgao_emissor: Mapped[str] = mapped_column(String(255))
    data_ato: Mapped[date | None] = mapped_column(Date)
    data_publicacao: Mapped[date | None] = mapped_column(Date)
    publicacao: Mapped[str | None] = mapped_column(Text)  # ex.: DODF nº 157, 21/08/2025
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    vigencia_fim: Mapped[date | None] = mapped_column(Date)
    vigencia_status: Mapped[str] = mapped_column(String(32), default="a_conferir")
    fontes: Mapped[list] = mapped_column(JSON, default=list)  # URLs oficiais
    status_verificacao: Mapped[str] = mapped_column(String(64))
    observacoes: Mapped[str | None] = mapped_column(Text)


class LimiarEstadoHidrologico(Base):
    """Tabela 1 da Res. ADASA 56/2025: limite de volume útil por reservatório, mês e estado."""

    __tablename__ = "limiar_estado_hidrologico"
    __table_args__ = (UniqueConstraint("norma_id", "reservatorio_id", "mes", "estado"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    norma_id: Mapped[str] = mapped_column(ForeignKey("norma_juridica.id"))
    reservatorio_id: Mapped[str] = mapped_column(ForeignKey("reservatorio.id"))
    mes: Mapped[int] = mapped_column(Integer)  # 1..12
    estado: Mapped[str] = mapped_column(String(16))  # amarelo | vermelho
    limite_pct: Mapped[float] = mapped_column(Float)
    comparador: Mapped[str] = mapped_column(String(8), default="<")  # estrito, conforme Tabela 1
    dispositivo: Mapped[str] = mapped_column(String(64), default="art. 1º, Tabela 1")


class RegistroAuditoria(Base):
    """Trilha append-only (RNF-02). Imutabilidade forte (hash encadeado) é etapa futura."""

    __tablename__ = "registro_auditoria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ator: Mapped[str] = mapped_column(String(128))  # sistema | usuario:<id>
    acao: Mapped[str] = mapped_column(String(64))
    entidade: Mapped[str | None] = mapped_column(String(64))
    entidade_id: Mapped[str | None] = mapped_column(String(64))
    detalhes: Mapped[dict] = mapped_column(JSON, default=dict)
