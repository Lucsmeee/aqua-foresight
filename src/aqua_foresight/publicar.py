"""Orquestrador da execução agendada: coleta → processa → indicadores → site estático.

Pensado para o GitHub Actions (rede liberada para as fontes oficiais) e para rodar local:

    aqua publicar --saida site            # baixa RONI, lê planilhas, consulta ANA se houver credencial
    aqua publicar --saida site --sem-download

Entradas versionadas no repositório (fonte de verdade da proveniência):
- data/raw/noaa_cpc_roni/          brutos do RONI, um arquivo por conteúdo distinto (SHA-256)
- data/manual/volume/*.csv|xlsx    exportações do SAR/ANA ou séries obtidas da ADASA
- data/raw/ana_hidrowebservice_*/  respostas da API da ANA (se houver credencial)

Saída (não versionada; publicada no GitHub Pages):
- <saida>/index.html               pipeline no navegador (web/index.html)
- <saida>/data/enos.json, volume.json, indicadores.json, status.json
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aqua_foresight.config import Settings
from aqua_foresight.db import init_db, make_engine, make_session_factory
from aqua_foresight.enso.phases import PontoENOS, classificar_fases
from aqua_foresight import conversao_adasa
from aqua_foresight.espanha import etapa_espanha
from aqua_foresight.ingestion import ana_hidrowebservice as ana
from aqua_foresight.ingestion import ana_sar
from aqua_foresight.ingestion import provenance
from aqua_foresight.ingestion.noaa_cpc import FONTES_CPC, N_ESTACOES_PROVISORIAS, parse_cpc_ascii
from aqua_foresight.ingestion.volume_arquivo import arquivos_de_volume, processar_arquivo
from aqua_foresight.legal.enquadramento import enquadrar
from aqua_foresight.legal.seed import carregar_base_normativa

FONTE_RONI = FONTES_CPC["RONI"]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _carimbo_do_nome(p: Path) -> str | None:
    try:
        return datetime.strptime(p.name.split("_", 1)[0], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return None


def etapa_enos(raw_dir: Path, baixar: bool, timeout: float) -> tuple[dict | None, dict]:
    status = {"id": FONTE_RONI["id"], "nome": FONTE_RONI["nome"], "url": FONTE_RONI["url"], "verificado_em": _agora()}
    if baixar:
        try:
            conteudo = provenance.baixar(FONTE_RONI["url"], timeout)
            parse_cpc_ascii(conteudo.decode("utf-8"))  # valida antes de preservar
            caminho = provenance.preservar_bruto(conteudo, raw_dir, FONTE_RONI["id"], FONTE_RONI["arquivo"])
            status.update(status="verificado", mensagem=f"download ok; bruto {caminho.name}")
        except Exception as exc:  # noqa: BLE001 — falha registrada, nunca silenciosa
            status.update(status="falha", mensagem=f"{type(exc).__name__}: {exc}"[:300])
    else:
        status.update(status="nao_verificado", mensagem="execução sem download")

    brutos = provenance.brutos_da_fonte(raw_dir, FONTE_RONI["id"])
    if not brutos:
        return None, status
    ultimo = brutos[-1]
    conteudo = ultimo.read_bytes()
    linhas = parse_cpc_ascii(conteudo.decode("utf-8"))
    fases = classificar_fases([PontoENOS(l.ano, l.estacao, l.anomalia) for l in linhas])
    corte = len(linhas) - N_ESTACOES_PROVISORIAS
    serie = [
        {
            "ano": f.ano, "estacao": f.estacao, "mes": PontoENOS(f.ano, f.estacao, f.valor).mes_central, "valor": f.valor,
            "natureza": "estimado_provisorio" if i >= corte else "observado",
            "condicao": f.condicao, "episodio": f.episodio, "confirmado": f.episodio_confirmado,
        }
        for i, f in enumerate(fases)
    ]
    enos = {
        "indicador": "RONI", "fonte_url": FONTE_RONI["url"], "arquivo": ultimo.name,
        "sha256": provenance.sha256_bytes(conteudo), "obtido_em": _carimbo_do_nome(ultimo),
        "periodo_base": FONTE_RONI["periodo_base"], "versoes_preservadas": len(brutos), "serie": serie,
    }
    return enos, status


def etapa_sar(raiz: Path, baixar: bool, hoje: date) -> tuple[list[dict], dict, dict]:
    """Atualiza data/series/sar_df_diario.csv (últimos 5 anos + últimos dias) e converte para a base ADASA."""
    caminho = raiz / "data" / "series" / "sar_df_diario.csv"
    serie = ana_sar.ler_serie(caminho)
    status = {"id": "ana_sar_df", "nome": "ANA · SAR, Distrito Federal (restportal)", "url": "https://www.ana.gov.br/sar/outros-sistemas-hidricos/df",
              "verificado_em": _agora()}
    if baixar:
        try:
            cliente = ana_sar.ClienteSAR()
            n = sum(ana_sar.mesclar(serie, cliente.grafico(r)) for r in ana_sar.CODIGOS)
            for d in (hoje - timedelta(days=k) for k in range(3, -1, -1)):
                n += ana_sar.mesclar(serie, cliente.medicoes(d))
            ana_sar.gravar_serie(caminho, serie)
            status.update(status="verificado", mensagem=f"{n} registro(s) novo(s) ou atualizado(s); {len(serie)} no total")
        except Exception as exc:  # noqa: BLE001
            status.update(status="falha", mensagem=f"{type(exc).__name__}: {exc}"[:300])
    else:
        status.update(status="nao_verificado", mensagem="execução sem download")
    obs, meta = conversao_adasa.converter_serie(sorted(serie.values(), key=lambda l: (l["data"], l["reservatorio"])))
    if not serie:
        status["mensagem"] = (status.get("mensagem", "") + "; série vazia").strip("; ")
    return obs, meta, status


def etapa_volume(pasta: Path, hoje: date, obs_sar: list[dict] | None = None, meta_sar: dict | None = None) -> tuple[dict, dict]:
    cargas = []
    obs = {(o["res"], o["data"]): {**o, "carga": 0} for o in (obs_sar or [])}
    for i, arq in enumerate(arquivos_de_volume(pasta), start=1):
        conteudo = arq.read_bytes()
        r = processar_arquivo(conteudo, arq.name, hoje)
        cargas.append({
            "id": i, "arquivo": arq.name, "sha256": provenance.sha256_bytes(conteudo), "lidas": r.lidas,
            "validas": len(r.obs), "rejeitadas": r.rejeitadas[:50], "n_rejeitadas": len(r.rejeitadas),
            "duplicadas": r.duplicadas, "mapeamento": r.mapeamento,
        })
        for o in r.obs:  # arquivos posteriores (ordem alfabética) prevalecem na visão vigente
            obs[(o["res"], o["data"])] = {**o, "carga": i, "natureza": "observado", "metodo": "planilha_manual"}
    if obs_sar:
        cargas.insert(0, {"id": 0, "arquivo": "data/series/sar_df_diario.csv (ANA · SAR)", "sha256": None, "lidas": len(obs_sar),
                          "validas": len(obs_sar), "rejeitadas": [], "n_rejeitadas": 0, "duplicadas": 0,
                          "mapeamento": {"metodo": "API restportal do SAR; Descoberto convertido para base ADASA (estimado)"}})
    volume = {"gerado_em": _agora(), "conversao": meta_sar or {}, "cargas": cargas,
              "obs": sorted(obs.values(), key=lambda o: (o["res"], o["data"]))}
    status = {
        "id": "planilhas_volume", "nome": "Volume útil consolidado (SAR + planilhas)", "url": None,
        "verificado_em": _agora(), "status": "verificado" if obs else "sem_dados",
        "mensagem": f"{len(cargas) - (1 if obs_sar else 0)} planilha(s) manual(is); {len(obs)} observação(ões) no total",
    }
    return volume, status


def etapa_ana(raw_dir: Path) -> tuple[dict, list[dict]]:
    cred = ana.Credenciais.do_ambiente()
    if cred is None:
        st = {"id": "ana_hidrowebservice", "nome": "ANA HidroWebService (telemetria)", "url": ana.BASE,
              "verificado_em": _agora(), "status": "sem_credencial",
              "mensagem": "defina os secrets ANA_IDENTIFICADOR e ANA_SENHA para ativar"}
        return {}, [st]
    cliente = ana.ClienteHidroWeb(cred)
    saida, status = {}, []
    for codigo, (res, verif) in ana.ESTACOES_PILOTO.items():
        st = {"id": f"ana_hidrowebservice_{codigo}", "nome": f"ANA telemetria {codigo} ({res})", "url": ana.BASE,
              "verificado_em": _agora()}
        try:
            itens = cliente.serie_adotada(codigo)
            bruto = json.dumps(itens, ensure_ascii=False, sort_keys=True).encode()
            provenance.preservar_bruto(bruto, raw_dir, f"ana_hidrowebservice_{codigo}", "serie_adotada.json")
            cotas = ana.cotas_validas(itens)
            saida[codigo] = {"reservatorio": res, "verificacao_estacao": verif, "cotas": cotas, "n_itens": len(itens)}
            st.update(status="verificado", mensagem=f"{len(itens)} registros; {len(cotas)} cotas com status ok")
        except Exception as exc:  # noqa: BLE001
            st.update(status="falha", mensagem=f"{type(exc).__name__}: {exc}"[:300])
        status.append(st)
    return saida, status


def etapa_indicadores(volume: dict, hoje: date, max_defasagem: int) -> dict:
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    out = {"gerado_em": _agora(), "data_referencia": hoje.isoformat(), "reservatorios": {}}
    with factory() as s:
        carregar_base_normativa(s)
        for res in ("descoberto", "santa_maria"):
            serie = [o for o in volume["obs"] if o["res"] == res]
            if not serie:
                continue
            u = serie[-1]
            r = enquadrar(s, res, hoje, u["valor"], "observado", date.fromisoformat(u["data"]), max_defasagem, ator="publicador")
            d = r.as_dict()
            if u.get("natureza") == "estimado":
                d["ressalvas"].insert(0, "Volume útil ESTIMADO na base ADASA a partir da cota publicada pelo SAR/ANA "
                                         "(conversão calibrada em 6 datas divulgadas pela ADASA; ver conversao_adasa.py). "
                                         "Confirmar com o valor oficial da ADASA antes de qualquer encaminhamento.")
            out["reservatorios"][res] = {"ultima_observacao": u, "enquadramento": d}
    return out


def montar_painel(enos: dict | None, volume: dict, indicadores: dict, status: dict) -> dict:
    """Arquivo compacto para o painel público: séries por reservatório, ENOS recente e indicadores."""
    series = {}
    for res in ("descoberto", "santa_maria"):
        obs = [o for o in volume["obs"] if o["res"] == res]
        series[res] = {
            "d": [o["data"] for o in obs],
            "v": [o["valor"] for o in obs],
            "s": [o.get("valor_sar") for o in obs],
            "natureza": obs[-1].get("natureza") if obs else None,
        }
    enos_recente = None
    if enos:
        enos_recente = {k: enos[k] for k in ("indicador", "fonte_url", "obtido_em", "periodo_base")}
        enos_recente["serie"] = [{k: p[k] for k in ("ano", "estacao", "mes", "valor", "condicao", "episodio", "confirmado", "natureza")}
                                 for p in enos["serie"][-60:]]
    return {"gerado_em": _agora(), "series": series, "enos": enos_recente, "indicadores": indicadores,
            "fontes": status["fontes"], "conversao": {"descoberto": {k: volume.get("conversao", {}).get("descoberto", {}).get(k)
                                                                       for k in ("A", "B")}}}


def executar(raiz: Path, saida: Path, hoje: date | None = None, baixar: bool = True, settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    hoje = hoje or datetime.now(timezone.utc).date()
    raw_dir = raiz / "data" / "raw"

    enos, st_enos = etapa_enos(raw_dir, baixar, settings.http_timeout)
    obs_sar, meta_sar, st_sar = etapa_sar(raiz, baixar, hoje)
    volume, st_vol = etapa_volume(raiz / "data" / "manual" / "volume", hoje, obs_sar, meta_sar)
    telemetria, st_ana = etapa_ana(raw_dir) if baixar else ({}, [])
    indicadores = etapa_indicadores(volume, hoje, settings.max_defasagem_observacao_dias)
    espanha, st_es = etapa_espanha(raiz, baixar, hoje)
    status = {"gerado_em": _agora(), "fontes": [st_enos, st_sar, st_vol, *st_ana, *st_es]}

    dados = saida / "data"
    dados.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in {"enos.json": enos, "volume.json": volume, "telemetria.json": telemetria,
                           "indicadores.json": indicadores, "status.json": status}.items():
        (dados / nome).write_text(json.dumps(conteudo, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    painel = montar_painel(enos, volume, indicadores, status)
    painel["espanha"] = espanha
    (dados / "painel.json").write_text(json.dumps(painel, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for pagina in sorted((raiz / "web").glob("*.html")):
        shutil.copyfile(pagina, saida / pagina.name)
    return status


def resumo(status: dict) -> str:
    return "\n".join(f"- {f['nome']}: {f['status']} — {f.get('mensagem', '')}" for f in status["fontes"])


__all__ = ["executar", "resumo"]
