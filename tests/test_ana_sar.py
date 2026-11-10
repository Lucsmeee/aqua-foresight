"""Adaptador SAR/ANA. Amostras de resposta copiadas da API real em 10/11/2026 (diagnóstico)."""

from datetime import date

import httpx
import pytest

from aqua_foresight.ingestion import ana_sar

MEDICOES_2017_11_07 = [
    {"codigo": None, "estado": "Distrito Federal", "reservatorio": "DESCOBERTO", "capacidade": "85.99", "cota": "1021.86",
     "volume": "17.60", "volumeUtil": "20.47", "data": "07/11/2017"},
    {"codigo": None, "estado": "Distrito Federal", "reservatorio": "SANTA MARIA", "capacidade": "61.31", "cota": "1064.23",
     "volume": "13.55", "volumeUtil": "22.10", "data": "07/11/2017"},
    {"codigo": None, "estado": "Distrito Federal", "reservatorio": "LAGO PARANOÁ", "capacidade": "-", "cota": "1000.30",
     "volume": "-", "volumeUtil": "-", "data": "07/11/2017"},
    {"codigo": None, "estado": "TOTAL", "reservatorio": None, "capacidade": "147.3", "data": None},
]


def test_parse_medicoes():
    regs = ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2017, 11, 7))
    assert [(r.reservatorio, r.cota_m, r.volume_hm3, r.pct_sar) for r in regs] == [
        ("descoberto", 1021.86, 17.60, 20.47),
        ("santa_maria", 1064.23, 13.55, 22.10),
    ]


def test_data_trocada_e_detectada():
    with pytest.raises(ValueError, match="trocados"):
        ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2017, 7, 11))


def test_proxima_medicao_disponivel_e_aceita_com_a_data_devolvida():
    # comportamento real: pedido 18/02/1992 → API devolveu 24/02/1992 (sem medição diária na época)
    regs = ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2017, 11, 1))
    assert {r.data for r in regs} == {"2017-11-07"}
    # comportamento real desde 2010: pedido 01/11/2010 → devolveu 31/10/2010 (medição anterior)
    assert {r.data for r in ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2017, 11, 9))} == {"2017-11-07"}
    with pytest.raises(ValueError, match="inesperada"):
        ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2019, 11, 9))  # salto grande demais


def test_sem_medicao():
    itens = [{"reservatorio": "DESCOBERTO", "capacidade": "85.99", "cota": "-", "volume": "-", "volumeUtil": "-", "data": "-"}]
    assert ana_sar.parse_medicoes(itens, date(1987, 1, 15)) == []


def test_parse_grafico_com_nan_e_hm3_para_pct():
    corpo = {"listaAno": ["2025", "2026"], "capacidade": 85.99,
             "serie1": [{"data": "12-31", "volume": "83.83", "cota": "1029.82"}],
             "serie2": [{"data": "01-01", "volume": "NaN", "cota": "NaN"}, {"data": "11-09", "volume": "66.44", "cota": "1028.30"}]}
    regs = ana_sar.parse_grafico(corpo, "descoberto")
    assert [(r.data, r.pct_sar) for r in regs] == [("2025-12-31", 97.49), ("2026-11-09", 77.26)]


def test_cliente_usa_mes_dia_ano():
    vistos = []

    def handler(req: httpx.Request):
        vistos.append(req.url.params["data"])
        return httpx.Response(200, json=MEDICOES_2017_11_07)

    c = ana_sar.ClienteSAR(pausa=0, client=httpx.Client(base_url=ana_sar.BASE, transport=httpx.MockTransport(handler)))
    assert len(c.medicoes(date(2017, 11, 7))) == 2
    assert vistos == ["11/07/2017"]


def test_mesclar_e_csv(tmp_path):
    serie = {}
    g = ana_sar.Registro("2017-11-07", "descoberto", 1021.9, 17.7, 85.99, 20.6, "retornaGrafico")
    m = ana_sar.parse_medicoes(MEDICOES_2017_11_07, date(2017, 11, 7))
    assert ana_sar.mesclar(serie, m) == 2
    assert ana_sar.mesclar(serie, [g]) == 0  # medição do dia prevalece
    assert ana_sar.mesclar(serie, m) == 0  # idempotente
    p = tmp_path / "s.csv"
    ana_sar.gravar_serie(p, serie)
    assert ana_sar.ler_serie(p) == serie
    assert ana_sar.dias_faltantes(serie, date(2017, 11, 6), date(2017, 11, 8)) == [date(2017, 11, 6), date(2017, 11, 8)]
