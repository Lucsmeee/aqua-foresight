import pytest
from fastapi.testclient import TestClient

from aqua_foresight.api.main import create_app
from aqua_foresight.ingestion import noaa_cpc


@pytest.fixture
def client(factory):
    return TestClient(create_app(factory))


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_limiares_descoberto(client):
    d = client.get("/limiares/descoberto").json()
    nov = next(m for m in d["meses"] if m["mes"] == 11)
    assert nov == {"mes": 11, "amarelo": 30.0, "vermelho": 20.0}
    assert len(d["meses"]) == 12


def test_limiares_inexistente(client):
    assert client.get("/limiares/paranoa").status_code == 404


def test_enquadramento_endpoint(client):
    r = client.post(
        "/enquadramento",
        json={"reservatorio_id": "santa_maria", "data_referencia": "2026-11-10", "valor_pct": 14.0, "natureza": "projetado"},
    ).json()
    assert r["estado_indicativo"] == "vermelho"
    assert r["tipo_saida"] == "alerta_antecipatorio"
    assert r["acoes_automaticas"] == []
    trilha = client.get("/auditoria?limite=1").json()[0]
    assert trilha["acao"] == "enquadramento_avaliado" and trilha["ator"] == "api"


def test_enos_404_sem_dados_reais_e_com_sintetico_explicito(client, factory, settings, arquivo_sintetico):
    assert client.get("/enos/RONI").status_code == 404
    with factory() as s:
        noaa_cpc.ingerir_indice_cpc(s, settings, "RONI", arquivo_sintetico, sintetico=True)
        s.commit()
    assert client.get("/enos/RONI").status_code == 404  # sintético não vira "vigente"
    d = client.get("/enos/RONI?incluir_sintetico=true&ultimos=3").json()
    assert d["sintetico"] is True and len(d["serie"]) == 3
    assert d["serie"][-1]["episodio_confirmado"] is False


def test_fontes_mostra_status_do_conector(client, factory, settings, arquivo_sintetico):
    with factory() as s:
        noaa_cpc.ingerir_indice_cpc(s, settings, "RONI", arquivo_sintetico, sintetico=True)
        s.commit()
    f = client.get("/fontes").json()[0]
    assert f["id"] == "noaa_cpc_roni"
    assert f["status_conector"] == "nao_verificado"
    assert f["ultima_ingestao"]["sintetico"] is True
