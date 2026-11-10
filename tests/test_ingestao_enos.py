from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from aqua_foresight.db.models import FonteDado, IndiceENOS, Ingestao
from aqua_foresight.ingestion import noaa_cpc, provenance
from tests.conftest import VALORES_SINTETICOS, texto_cpc_sintetico


def test_ingestao_local_preserva_bruto_e_marca_natureza(session, settings, arquivo_sintetico):
    r = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=True)
    assert r.status == "sucesso" and r.n_registros == len(VALORES_SINTETICOS)
    ing = session.get(Ingestao, r.ingestao_id)
    bruto = Path(ing.caminho_bruto)
    assert bruto.exists() and provenance.sha256_bytes(bruto.read_bytes()) == ing.sha256
    naturezas = {l.natureza for l in session.scalars(select(IndiceENOS))}
    assert naturezas == {"sintetico"}


def test_ultimas_estacoes_provisorias_quando_nao_sintetico(session, settings, arquivo_sintetico):
    r = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=False)
    linhas = noaa_cpc.carregar_serie(session, r.ingestao_id)
    assert [l.natureza for l in linhas[-2:]] == ["estimado_provisorio"] * 2
    assert {l.natureza for l in linhas[:-2]} == {"observado"}
    assert linhas[0].periodo_base == "1991-2020"


def test_conteudo_identico_nao_duplica(session, settings, arquivo_sintetico):
    r1 = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=True)
    r2 = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=True)
    assert r2.n_registros == 0 and r2.duplicado_de == r1.ingestao_id
    assert len(session.scalars(select(IndiceENOS)).all()) == len(VALORES_SINTETICOS)


def test_revisao_retroativa_cria_vintage_sem_apagar_o_anterior(session, settings, tmp_path, arquivo_sintetico):
    r1 = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=True)
    corte = datetime.now(timezone.utc)
    revisado = list(VALORES_SINTETICOS)
    revisado[-1] = 1.3  # revisão da estação mais recente
    p2 = tmp_path / "RONI_SINTETICO_v2.txt"
    p2.write_text(texto_cpc_sintetico(revisado))
    r2 = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", p2, sintetico=True)
    assert r2.ingestao_id != r1.ingestao_id and r2.n_registros == len(revisado)
    assert noaa_cpc.contar_vintages(session) == 2
    # visão point-in-time: até o corte, vale o vintage 1
    assert noaa_cpc.vintage_vigente(session, ate=corte, incluir_sintetico=True) == r1.ingestao_id
    assert noaa_cpc.vintage_vigente(session, incluir_sintetico=True) == r2.ingestao_id
    assert noaa_cpc.carregar_serie(session, r1.ingestao_id)[-1].valor == VALORES_SINTETICOS[-1]


def test_sintetico_nao_aparece_como_vigente_por_padrao(session, settings, arquivo_sintetico):
    noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", arquivo_sintetico, sintetico=True)
    assert noaa_cpc.vintage_vigente(session) is None


def test_falha_de_arquivo_registrada(session, settings, tmp_path):
    r = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", tmp_path / "nao_existe.txt")
    assert r.status == "falha" and "FileNotFoundError" in r.mensagem
    # arquivo local não testa o conector
    assert session.get(FonteDado, "noaa_cpc_roni").status_conector == "nao_verificado"


def test_falha_de_download_marca_conector(session, settings, monkeypatch):
    def _boom(url, timeout):
        raise ConnectionError("sem rota")

    monkeypatch.setattr(provenance, "baixar", _boom)
    r = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI")
    assert r.status == "falha"
    assert session.get(FonteDado, "noaa_cpc_roni").status_conector == "falha"


def test_download_bem_sucedido_verifica_conector(session, settings, monkeypatch):
    monkeypatch.setattr(provenance, "baixar", lambda url, timeout: texto_cpc_sintetico().encode())
    r = noaa_cpc.ingerir_indice_cpc(session, settings, "RONI", sintetico=True)
    assert r.status == "sucesso"
    assert session.get(FonteDado, "noaa_cpc_roni").status_conector == "verificado"
