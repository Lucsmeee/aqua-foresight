import pytest

from aqua_foresight.ingestion.noaa_cpc import ErroFormatoCPC, parse_cpc_ascii
from tests.conftest import VALORES_SINTETICOS, texto_cpc_sintetico


def test_parse_tres_colunas_roni():
    linhas = parse_cpc_ascii(texto_cpc_sintetico())
    assert len(linhas) == len(VALORES_SINTETICOS)
    assert (linhas[0].estacao, linhas[0].ano, linhas[0].anomalia) == ("DJF", 2000, 0.1)
    assert (linhas[12].estacao, linhas[12].ano) == ("DJF", 2001)


def test_parse_quatro_colunas_oni_usa_ultima_coluna_como_anomalia():
    linhas = parse_cpc_ascii(texto_cpc_sintetico(quatro_colunas=True))
    assert [l.anomalia for l in linhas] == VALORES_SINTETICOS


def test_estacao_invalida():
    txt = texto_cpc_sintetico() + "  XYZ 2002  0.10\n"
    with pytest.raises(ErroFormatoCPC, match="estação inválida"):
        parse_cpc_ascii(txt)


def test_lacuna_temporal_detectada():
    txt = "SEAS YR ANOM\n DJF 2000 0.1\n FMA 2000 0.2\n"
    with pytest.raises(ErroFormatoCPC, match="descontinuidade"):
        parse_cpc_ascii(txt)


def test_valor_implausivel():
    with pytest.raises(ErroFormatoCPC, match="implausível"):
        parse_cpc_ascii("SEAS YR ANOM\n DJF 2000 -99.9\n")


def test_arquivo_vazio():
    with pytest.raises(ErroFormatoCPC):
        parse_cpc_ascii("SEAS YR ANOM\n")
