from datetime import date

from sqlalchemy import delete, func, select

from aqua_foresight.db.models import LimiarEstadoHidrologico, RegistroAuditoria
from aqua_foresight.legal import adasa_56_2025 as adasa
from aqua_foresight.legal.enquadramento import enquadrar
from aqua_foresight.legal.seed import carregar_base_normativa

NOV = date(2026, 11, 10)


def test_seed_completo_e_idempotente(session):
    assert session.scalar(select(func.count()).select_from(LimiarEstadoHidrologico)) == 2 * 2 * 12
    assert carregar_base_normativa(session) == {"reservatorios": 0, "normas": 0, "limiares": 0}


def test_novembro_bate_com_especificacao_v2():
    # Espec. v2.0 §7.2: Descoberto 30/20, Santa Maria 25/15 em novembro.
    assert adasa.TABELA_1["descoberto"]["amarelo"][10] == 30
    assert adasa.TABELA_1["descoberto"]["vermelho"][10] == 20
    assert adasa.TABELA_1["santa_maria"]["amarelo"][10] == 25
    assert adasa.TABELA_1["santa_maria"]["vermelho"][10] == 15


def test_vermelho_sempre_abaixo_do_amarelo():
    for r in adasa.TABELA_1.values():
        assert all(v < a for v, a in zip(r["vermelho"], r["amarelo"]))


def test_limites_estritos_novembro_descoberto(session):
    kw = dict(natureza="observado", data_dado=NOV)
    assert enquadrar(session, "descoberto", NOV, 30.0, **kw).estado_indicativo == "verde"
    assert enquadrar(session, "descoberto", NOV, 29.9, **kw).estado_indicativo == "amarelo"
    assert enquadrar(session, "descoberto", NOV, 20.0, **kw).estado_indicativo == "amarelo"
    assert enquadrar(session, "descoberto", NOV, 19.9, **kw).estado_indicativo == "vermelho"


def test_mesmo_valor_estados_diferentes_por_reservatorio_e_mes(session):
    # Teste de aceitação §13.1: limiares mudam por mês e por reservatório.
    v = 27.0
    assert enquadrar(session, "descoberto", NOV, v, "observado", NOV).estado_indicativo == "amarelo"
    assert enquadrar(session, "santa_maria", NOV, v, "observado", NOV).estado_indicativo == "verde"
    abril = date(2026, 4, 15)
    assert enquadrar(session, "santa_maria", abril, v, "observado", abril).estado_indicativo == "vermelho"


def test_projetado_vira_apenas_alerta_antecipatorio(session):
    r = enquadrar(session, "descoberto", NOV, 15.0, "projetado")
    assert r.estado_indicativo == "vermelho"
    assert r.tipo_saida == "alerta_antecipatorio"
    assert "condicao_de_uso_que_se_aplicaria_se_confirmada_em_observacao_oficial" in r.fundamentacao
    assert any("não estado hidrológico observado" in x for x in r.ressalvas)


def test_nenhuma_acao_automatica_e_revisao_humana_sempre(session):
    for nat in ("observado", "projetado"):
        r = enquadrar(session, "descoberto", NOV, 5.0, nat, NOV)
        assert r.acoes_automaticas == []
        assert r.requer_revisao_humana is True
        assert "Não constitui ato administrativo" in r.aviso


def test_fundamentacao_cita_norma_fontes_e_autoridade(session):
    r = enquadrar(session, "santa_maria", NOV, 24.0, "observado", NOV)
    f = r.fundamentacao
    assert f["norma_id"] == "adasa_res_56_2025"
    assert "ADASA" in f["autoridade_competente"]
    assert any("sinj.df.gov.br" in u for u in f["fontes"])
    assert any("adasa.df.gov.br" in u for u in f["fontes"])
    assert any("Vigência" in x for x in r.ressalvas)  # vigência ainda não conferida


def test_bloqueio_sem_limiar(session):
    session.execute(delete(LimiarEstadoHidrologico).where(LimiarEstadoHidrologico.mes == 11))
    r = enquadrar(session, "descoberto", NOV, 10.0, "observado", NOV)
    assert r.status == "bloqueado"
    assert r.estado_indicativo is None
    assert r.tipo_saida == "revisao_humana_obrigatoria"


def test_bloqueio_reservatorio_desconhecido(session):
    assert enquadrar(session, "paranoa", NOV, 10.0, "observado", NOV).status == "bloqueado"


def test_bloqueio_valor_fisicamente_invalido(session):
    assert enquadrar(session, "descoberto", NOV, 101.0, "observado", NOV).status == "bloqueado"
    assert enquadrar(session, "descoberto", NOV, -1.0, "observado", NOV).status == "bloqueado"


def test_observacao_defasada_gera_ressalva(session):
    r = enquadrar(session, "descoberto", NOV, 40.0, "observado", date(2026, 10, 20), max_defasagem_dias=7)
    assert r.status == "enquadrado_indicativo"
    assert any("defasada" in x for x in r.ressalvas)
    assert any("mês diferente" in x for x in r.ressalvas)


def test_observacao_no_futuro_bloqueia(session):
    assert enquadrar(session, "descoberto", NOV, 40.0, "observado", date(2026, 11, 20)).status == "bloqueado"


def test_toda_avaliacao_e_auditada(session):
    antes = session.scalar(select(func.count()).select_from(RegistroAuditoria))
    enquadrar(session, "descoberto", NOV, 40.0, "observado", NOV)
    enquadrar(session, "descoberto", NOV, 101.0, "observado", NOV)
    session.flush()
    depois = session.scalar(select(func.count()).select_from(RegistroAuditoria))
    assert depois - antes == 2
