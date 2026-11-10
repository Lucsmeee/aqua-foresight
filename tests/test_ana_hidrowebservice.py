"""Cliente ANA com transporte simulado (sem rede, sem credencial real)."""

import httpx
import pytest

from aqua_foresight.ingestion import ana_hidrowebservice as ana


def _cliente(handler):
    http = httpx.Client(base_url=ana.BASE, transport=httpx.MockTransport(handler))
    return ana.ClienteHidroWeb(ana.Credenciais("00000000000", "senha-teste"), client=http)


def test_autentica_uma_vez_e_usa_bearer():
    chamadas = []

    def handler(req: httpx.Request):
        chamadas.append(req.url.path)
        if req.url.path.endswith("/OAUth/v1"):
            assert req.headers["Identificador"] == "00000000000" and req.headers["Senha"] == "senha-teste"
            return httpx.Response(200, json={"status": "OK", "items": {"tokenautenticacao": "tok123"}})
        assert req.headers["Authorization"] == "Bearer tok123"
        assert req.url.params["CodigoDaEstacao"] == "60435500"
        assert req.url.params["TipoFiltroData"] == "DATA_LEITURA"
        return httpx.Response(200, json={"items": [
            {"Data_Hora_Medicao": "2026-11-09 07:00:00.0", "Cota_Adotada": "1029.1", "Cota_Adotada_Status": "0"},
            {"Data_Hora_Medicao": "2026-11-09 08:00:00.0", "Cota_Adotada": "9999", "Cota_Adotada_Status": "2"},
        ]})

    c = _cliente(handler)
    itens = c.serie_adotada("60435500")
    c.serie_adotada("60435500")
    assert chamadas.count(ana.BASE.split(".br")[1] + ana.ROTA_TOKEN) == 1
    cotas = ana.cotas_validas(itens)
    assert cotas == [{"data_hora": "2026-11-09 07:00:00.0", "cota": 1029.1, "unidade": "a_confirmar"}]


def test_erro_http_vira_erro_ana_com_mensagem():
    c = _cliente(lambda req: httpx.Response(401, text="credencial inválida"))
    with pytest.raises(ana.ErroANA, match="401"):
        c.serie_adotada("60435500")


def test_sem_credencial_no_ambiente(monkeypatch):
    monkeypatch.delenv("ANA_IDENTIFICADOR", raising=False)
    monkeypatch.delenv("ANA_SENHA", raising=False)
    assert ana.Credenciais.do_ambiente() is None
