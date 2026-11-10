import pytest

from aqua_foresight.enso.phases import ESTACOES, PontoENOS, classificar_fases
from tests.conftest import VALORES_SINTETICOS


def _pontos(valores, ano0=2000):
    return [PontoENOS(ano0 + i // 12, ESTACOES[i % 12], v) for i, v in enumerate(valores)]


def test_episodios_pelo_criterio_de_cinco_estacoes():
    f = classificar_fases(_pontos(VALORES_SINTETICOS))
    # índices 4..9: seis estações >= 0,5 -> episódio El Niño
    assert all(x.episodio == "el_nino" for x in f[4:10])
    # índices 15..18: quatro estações <= -0,5 -> condição fria, mas NÃO é episódio
    assert all(x.condicao == "la_nina" for x in f[15:19])
    assert all(x.episodio == "neutro" for x in f[15:19])
    assert all(x.episodio_confirmado for x in f[15:19])


def test_sequencia_no_fim_da_serie_nao_confirmada():
    f = classificar_fases(_pontos(VALORES_SINTETICOS))
    assert [x.condicao for x in f[-2:]] == ["el_nino", "el_nino"]
    assert [x.episodio for x in f[-2:]] == ["neutro", "neutro"]
    assert [x.episodio_confirmado for x in f[-2:]] == [False, False]


def test_limiar_inclusivo():
    f = classificar_fases(_pontos([0.5] * 5))
    assert {x.episodio for x in f} == {"el_nino"}


def test_lacuna_rejeitada():
    pts = [PontoENOS(2000, "DJF", 0.1), PontoENOS(2000, "FMA", 0.2)]
    with pytest.raises(ValueError, match="lacuna"):
        classificar_fases(pts)
