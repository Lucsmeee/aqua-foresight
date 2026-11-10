"""Estações trimestrais do CPC e classificação de episódios ENOS.

Definição operacional usada (NOAA/CPC, tabela histórica de episódios):
- condição quente/fria numa estação: índice >= +0,5 °C / <= -0,5 °C;
- episódio El Niño / La Niña: pelo menos 5 estações trimestrais sobrepostas
  consecutivas na mesma condição.

Isto classifica a FASE oceânica. Não diz nada sobre impacto no DF: a relação
com chuva/vazão local é hipótese a testar (H1/H2 da Especificação), não premissa.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

ESTACOES: tuple[str, ...] = (
    "DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
    "JJA", "JAS", "ASO", "SON", "OND", "NDJ",
)
# Mês central de cada estação (DJF -> janeiro ... NDJ -> dezembro).
MES_CENTRAL: dict[str, int] = {s: i + 1 for i, s in enumerate(ESTACOES)}

LIMIAR_PADRAO = 0.5
MIN_ESTACOES_EPISODIO = 5

Fase = Literal["el_nino", "la_nina", "neutro"]


@dataclass(frozen=True)
class PontoENOS:
    ano: int
    estacao: str
    valor: float

    @property
    def mes_central(self) -> int:
        return MES_CENTRAL[self.estacao]

    @property
    def chave_temporal(self) -> int:
        return self.ano * 12 + self.mes_central


@dataclass(frozen=True)
class FaseClassificada:
    ano: int
    estacao: str
    valor: float
    condicao: Fase  # condição da estação isolada
    episodio: Fase  # fase pelo critério de 5 estações consecutivas
    episodio_confirmado: bool  # False se a sequência que chega ao fim da série ainda tem < 5


def _condicao(valor: float, limiar: float) -> Fase:
    if valor >= limiar:
        return "el_nino"
    if valor <= -limiar:
        return "la_nina"
    return "neutro"


def classificar_fases(
    pontos: Sequence[PontoENOS],
    limiar: float = LIMIAR_PADRAO,
    min_estacoes: int = MIN_ESTACOES_EPISODIO,
) -> list[FaseClassificada]:
    """Classifica cada estação. Exige série ordenada e sem lacunas."""
    ordenados = sorted(pontos, key=lambda p: p.chave_temporal)
    for a, b in zip(ordenados, ordenados[1:]):
        if b.chave_temporal - a.chave_temporal != 1:
            raise ValueError(
                f"Série ENOS com lacuna ou duplicata entre {a.estacao}/{a.ano} e {b.estacao}/{b.ano}"
            )

    condicoes = [_condicao(p.valor, limiar) for p in ordenados]
    episodio: list[Fase] = ["neutro"] * len(ordenados)
    confirmado = [True] * len(ordenados)

    i = 0
    n = len(ordenados)
    while i < n:
        j = i
        while j + 1 < n and condicoes[j + 1] == condicoes[i]:
            j += 1
        tamanho = j - i + 1
        if condicoes[i] != "neutro":
            chega_ao_fim = j == n - 1
            if tamanho >= min_estacoes:
                for k in range(i, j + 1):
                    episodio[k] = condicoes[i]
            elif chega_ao_fim:
                # Sequência em curso: pode virar episódio com dados futuros.
                for k in range(i, j + 1):
                    confirmado[k] = False
        i = j + 1

    return [
        FaseClassificada(p.ano, p.estacao, p.valor, c, e, ok)
        for p, c, e, ok in zip(ordenados, condicoes, episodio, confirmado)
    ]
