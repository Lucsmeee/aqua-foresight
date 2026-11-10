"""Leitura de planilhas de volume útil. Conteúdos de teste são SINTÉTICOS (formato do SAR)."""

from datetime import date
from io import BytesIO

from aqua_foresight.ingestion.volume_arquivo import parse_data, parse_num, processar_arquivo

HOJE = date(2026, 11, 10)

CSV_SAR = (
    '"Reservatório";"Cota (m)";"Volume (hm³)";"Volume (%)";"Data"\n'
    '"Descoberto";"1029,10";"55,2";"62,40";"09/11/2026"\n'
    '"Santa Maria";"1068,3";"40,1";"71,20";"09/11/2026"\n'
    '"Lago Paranoá";"999,8";"";"";"09/11/2026"\n'
).encode("utf-8")


def test_formato_sar_com_reservatorio_em_coluna():
    r = processar_arquivo(CSV_SAR, "sar_df.csv", HOJE)
    assert [(o["res"], o["data"], o["valor"]) for o in r.obs] == [
        ("descoberto", "2026-11-09", 62.4),
        ("santa_maria", "2026-11-09", 71.2),
    ]
    assert r.mapeamento == {"data": "Data", "volume": "Volume (%)", "reservatorio": "Reservatório"}
    assert [x["motivo"] for x in r.rejeitadas] == ["reservatório fora do piloto"]


def test_csv_latin1_e_reservatorio_pelo_nome_do_arquivo():
    conteudo = "Data,Volume útil (%)\n2026-11-01,40.5\n2026-11-02,40.3\n".encode("cp1252")
    r = processar_arquivo(conteudo, "descoberto_novembro.csv", HOJE)
    assert [o["valor"] for o in r.obs] == [40.5, 40.3]
    assert {o["res"] for o in r.obs} == {"descoberto"}


def test_validacoes_e_duplicatas():
    conteudo = (
        "Data;Volume (%)\n10/11/2027;50\nxx;50\n01/11/2026;150\n02/11/2026;n/d\n03/11/2026;40\n03/11/2026;41\n"
    ).encode()
    r = processar_arquivo(conteudo, "x.csv", HOJE, reservatorio_fixo="santa_maria")
    assert [o["valor"] for o in r.obs] == [41.0]
    assert r.duplicadas == 1
    assert sorted(x["motivo"] for x in r.rejeitadas) == sorted(
        ["data no futuro", "data inválida", "volume fora de 0–100%", "volume não numérico"]
    )


def test_colunas_nao_identificadas():
    r = processar_arquivo(b"foo;bar\n1;2\n", "x.csv", HOJE)
    assert not r.obs and "colunas não identificadas" in r.rejeitadas[0]["motivo"]


def test_xlsx():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Reservatório", "Data", "Volume Útil (%)"])
    ws.append(["Santa Maria", date(2026, 11, 8), 70.5])
    buf = BytesIO()
    wb.save(buf)
    r = processar_arquivo(buf.getvalue(), "planilha.xlsx", HOJE)
    assert r.obs == [{"res": "santa_maria", "data": "2026-11-08", "valor": 70.5}]


def test_parsers():
    assert parse_num("1.234,5") == 1234.5 and parse_num("45,3 %") == 45.3 and parse_num("abc") is None
    assert parse_data("9/11/26") == date(2026, 11, 9)
    assert parse_data("31/02/2026") is None
    assert parse_data(46000) == date(2025, 12, 9)
