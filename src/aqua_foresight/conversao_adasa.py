"""Conversão do percentual publicado pelo SAR/ANA para a base de "volume útil" usada pela ADASA.

Por que existe: os limiares da Res. ADASA 56/2025 são em % do volume útil calculado pela ADASA.
Comparando datas em que a ADASA divulgou o percentual com o que o SAR/ANA retorna para o mesmo dia:

- Santa Maria: coincidem (diferença ≤ 0,12 p.p. em 5 datas, 2016–2022) → usa-se o valor do SAR.
- Descoberto: divergem sistematicamente (SAR 20,47% × ADASA 5,3% em 07/11/2017). A relação é linear,
  compatível com a ADASA descontar ~16% da capacidade usada pelo SAR (volume abaixo da tomada útil):
      ADASA ≈ A · SAR + B,  A = 1,19002, B = −18,9976  (ajuste por mínimos quadrados, 6 pontos,
      resíduo máximo 0,26 p.p.; equivale a (SAR − 15,96) / (100 − 15,96) × 100).

Além disso, o volume histórico do Descoberto no SAR foi calculado com curvas cota-volume diferentes ao
longo do tempo (ex.: cota 1027,19 m em 2015 → 55,35 hm³; cota 1027,76 m em 2013 → 47,17 hm³). Para ter
uma série coerente, o percentual do Descoberto é recalculado a partir da COTA (medição direta), usando
a relação cota→% observada no período de referência (≥ 2017, onde a calibração foi feita).

Tudo aqui é ESTIMATIVA documentada, não dado oficial da ADASA. A natureza do valor é "estimado".
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

A_DESCOBERTO = 1.19002
B_DESCOBERTO = -18.9976
INICIO_PERIODO_REFERENCIA = "2017-01-01"

# Pontos de calibração: (data, % SAR/ANA no dia, % divulgado pela ADASA, fonte da divulgação)
CALIBRACAO_DESCOBERTO = [
    ("2017-08-14", 45.27, 34.79, "Congresso em Foco, citando Adasa"),
    ("2017-08-31", 40.38, 28.88, "Congresso em Foco, citando Adasa"),
    ("2017-10-10", 27.76, 14.3, "Agência Brasil, citando Adasa"),
    ("2017-11-07", 20.47, 5.3, "Correio Braziliense, citando Adasa"),
    ("2018-04-27", 91.64, 90.1, "Correio Braziliense, citando Adasa"),
    ("2022-10-05", 55.53, 47.1, "Jornal de Brasília, citando o SIRH/Adasa"),
]
VALIDACAO_SANTA_MARIA = [
    ("2016-11-19", 40.42, 40.3, "Jornal de Brasília, citando Adasa"),
    ("2017-08-14", 40.96, 40.96, "Congresso em Foco, citando Adasa"),
    ("2017-08-31", 36.63, 36.55, "Congresso em Foco, citando Adasa"),
    ("2017-11-05", 21.87, 21.8, "Jornal de Brasília, citando Adasa"),
    ("2022-10-05", 78.09, 78.0, "Jornal de Brasília, citando o SIRH/Adasa"),
]


def sar_para_adasa_descoberto(pct_sar: float) -> float:
    return max(0.0, min(100.0, A_DESCOBERTO * pct_sar + B_DESCOBERTO))


@dataclass
class CurvaCota:
    """Relação cota (m) → % SAR por interpolação linear em cotas ordenadas (média por cota arredondada)."""

    cotas: list[float]
    pcts: list[float]

    @classmethod
    def ajustar(cls, pares: list[tuple[float, float]]) -> "CurvaCota":
        grupos: dict[float, list[float]] = {}
        for cota, pct in pares:
            grupos.setdefault(round(cota, 2), []).append(pct)
        cotas = sorted(grupos)
        pcts = [sum(grupos[c]) / len(grupos[c]) for c in cotas]
        # força monotonicidade (volume não pode cair com a cota subindo): máximo acumulado
        for i in range(1, len(pcts)):
            pcts[i] = max(pcts[i], pcts[i - 1])
        return cls(cotas, pcts)

    def __call__(self, cota: float) -> tuple[float, bool]:
        """Retorna (pct, dentro_da_faixa). Fora da faixa observada, satura no extremo e sinaliza."""
        if cota <= self.cotas[0]:
            return self.pcts[0], cota == self.cotas[0]
        if cota >= self.cotas[-1]:
            return self.pcts[-1], cota == self.cotas[-1]
        i = bisect_left(self.cotas, cota)
        c0, c1, p0, p1 = self.cotas[i - 1], self.cotas[i], self.pcts[i - 1], self.pcts[i]
        return p0 + (p1 - p0) * (cota - c0) / (c1 - c0), True


def converter_serie(linhas: list[dict]) -> tuple[list[dict], dict]:
    """Recebe linhas do CSV do SAR e devolve observações na base ADASA, com natureza e método."""
    ref = [(float(l["cota_m"]), float(l["pct_sar"])) for l in linhas
           if l["reservatorio"] == "descoberto" and l["data"] >= INICIO_PERIODO_REFERENCIA and l["cota_m"] and l["pct_sar"]]
    curva = CurvaCota.ajustar(ref) if len(ref) >= 30 else None
    out, fora = [], 0
    for l in linhas:
        res, pct_sar = l["reservatorio"], float(l["pct_sar"]) if l.get("pct_sar") else None
        cota = float(l["cota_m"]) if l.get("cota_m") else None
        if res == "santa_maria":
            if pct_sar is None:
                continue
            out.append({"res": res, "data": l["data"], "valor": round(min(pct_sar, 100.0), 2), "valor_sar": pct_sar,
                        "cota": cota, "natureza": "observado", "metodo": "sar_igual_adasa"})
        elif res == "descoberto":
            if cota is not None and curva is not None:
                base, ok = curva(cota)
                fora += 0 if ok else 1
                metodo = "cota_curva_ref_2017+_conversao_linear" + ("" if ok else "_fora_da_faixa")
            elif pct_sar is not None and l["data"] >= INICIO_PERIODO_REFERENCIA:
                base, metodo = pct_sar, "conversao_linear"
            else:
                continue
            out.append({"res": res, "data": l["data"], "valor": round(sar_para_adasa_descoberto(base), 2), "valor_sar": pct_sar,
                        "cota": cota, "natureza": "estimado", "metodo": metodo})
    meta = {
        "descoberto": {"A": A_DESCOBERTO, "B": B_DESCOBERTO, "pontos_curva_cota": len(curva.cotas) if curva else 0,
                       "faixa_cota_ref": [curva.cotas[0], curva.cotas[-1]] if curva else None,
                       "obs_fora_da_faixa": fora, "calibracao": CALIBRACAO_DESCOBERTO},
        "santa_maria": {"validacao": VALIDACAO_SANTA_MARIA},
    }
    return out, meta
