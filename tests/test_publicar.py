"""Execução completa do publicador em diretório temporário (dados SINTÉTICOS, rede simulada)."""

import json
from datetime import date

from aqua_foresight import publicar
from aqua_foresight.config import Settings
from aqua_foresight.ingestion import ana_sar, provenance
from tests.conftest import texto_cpc_sintetico

HOJE = date(2026, 11, 10)


class SARFalso:
    """Substitui a API real do SAR nos testes (sem rede). Devolve uma medição por chamada."""

    def __init__(self, *a, **k):
        pass

    def grafico(self, res):
        return []

    def medicoes(self, d):
        return [ana_sar.Registro(d.isoformat(), "santa_maria", 1070.4, 49.9, 61.31, 81.39, "retornaMedicoes")]


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def sem_rede_sar(monkeypatch):
    from aqua_foresight import espanha

    monkeypatch.setattr(ana_sar, "ClienteSAR", SARFalso)
    monkeypatch.setattr(espanha, "atualizar_miteco", lambda pasta, forcar=False: {"id": "miteco_embalses", "nome": "x", "status": "verificado"})
    monkeypatch.setattr(espanha, "atualizar_chj", lambda pasta, meses: {"id": "chj_pes", "nome": "x", "status": "verificado"})


def _raiz(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<!DOCTYPE html><title>t</title>")
    vol = tmp_path / "data" / "manual" / "volume"
    vol.mkdir(parents=True)
    linhas = ['"Reservatório";"Volume (%)";"Data"']
    for d in range(1, 10):
        valor = f"{31 - 0.2 * d:.1f}".replace(".", ",")
        linhas.append(f'"Descoberto";"{valor}";"0{d}/11/2026"')
        linhas.append(f'"Santa Maria";"60,0";"0{d}/11/2026"')
    (vol / "sar_teste.csv").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return tmp_path


def test_execucao_completa(tmp_path, monkeypatch):
    raiz = _raiz(tmp_path)
    monkeypatch.setattr(provenance, "baixar", lambda url, timeout: texto_cpc_sintetico().encode())
    monkeypatch.delenv("ANA_IDENTIFICADOR", raising=False)
    status = publicar.executar(raiz, raiz / "site", HOJE, baixar=True, settings=Settings())

    estados = {f["id"]: f["status"] for f in status["fontes"]}
    assert estados == {"noaa_cpc_roni": "verificado", "ana_sar_df": "verificado", "planilhas_volume": "verificado",
                       "ana_hidrowebservice": "sem_credencial", "miteco_embalses": "verificado", "chj_pes": "verificado"}
    assert (raiz / "data" / "series" / "sar_df_diario.csv").exists()

    d = raiz / "site" / "data"
    enos = json.loads((d / "enos.json").read_text())
    assert enos["indicador"] == "RONI" and len(enos["serie"]) == 24
    assert [p["natureza"] for p in enos["serie"][-2:]] == ["estimado_provisorio"] * 2

    vol = json.loads((d / "volume.json").read_text())
    manuais = [o for o in vol["obs"] if o["metodo"] == "planilha_manual"]
    assert len(manuais) == 18  # planilha manual prevalece sobre o SAR na mesma data

    ind = json.loads((d / "indicadores.json").read_text())
    desc = ind["reservatorios"]["descoberto"]["enquadramento"]
    assert desc["estado_indicativo"] == "amarelo"  # 29,2% em novembro (< 30)
    assert desc["acoes_automaticas"] == [] and desc["requer_revisao_humana"] is True
    assert ind["reservatorios"]["santa_maria"]["enquadramento"]["estado_indicativo"] == "verde"
    assert (raiz / "site" / "index.html").exists()


def test_segunda_execucao_nao_duplica_bruto(tmp_path, monkeypatch):
    raiz = _raiz(tmp_path)
    monkeypatch.setattr(provenance, "baixar", lambda url, timeout: texto_cpc_sintetico().encode())
    publicar.executar(raiz, raiz / "site", HOJE, settings=Settings())
    publicar.executar(raiz, raiz / "site", HOJE, settings=Settings())
    assert len(provenance.brutos_da_fonte(raiz / "data" / "raw", "noaa_cpc_roni")) == 1


def test_falha_de_download_usa_ultimo_bruto_e_registra(tmp_path, monkeypatch):
    raiz = _raiz(tmp_path)
    monkeypatch.setattr(provenance, "baixar", lambda url, timeout: texto_cpc_sintetico().encode())
    publicar.executar(raiz, raiz / "site", HOJE, settings=Settings())

    def falha(url, timeout):
        raise ConnectionError("CPC fora do ar")

    monkeypatch.setattr(provenance, "baixar", falha)
    status = publicar.executar(raiz, raiz / "site", HOJE, settings=Settings())
    roni = next(f for f in status["fontes"] if f["id"] == "noaa_cpc_roni")
    assert roni["status"] == "falha" and "CPC fora do ar" in roni["mensagem"]
    enos = json.loads((raiz / "site" / "data" / "enos.json").read_text())
    assert enos["serie"]  # continua publicando o último vintage, com a falha visível no status


def test_arquivo_invalido_do_cpc_nao_e_preservado(tmp_path, monkeypatch):
    raiz = _raiz(tmp_path)
    monkeypatch.setattr(provenance, "baixar", lambda url, timeout: b"<html>manutencao</html>")
    status = publicar.executar(raiz, raiz / "site", HOJE, settings=Settings())
    assert next(f for f in status["fontes"] if f["id"] == "noaa_cpc_roni")["status"] == "falha"
    assert provenance.brutos_da_fonte(raiz / "data" / "raw", "noaa_cpc_roni") == []
