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
from datetime import date, datetime, timezone
from pathlib import Path

from aqua_foresight.config import Settings
from aqua_foresight.db import init_db, make_engine, make_session_factory
from aqua_foresight.enso.phases import PontoENOS, classificar_fases
from aqua_foresight.ingestion import ana_hidrowebservice as ana
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


def etapa_volume(pasta: Path, hoje: date) -> tuple[dict, dict]:
    cargas, obs = [], {}
    for i, arq in enumerate(arquivos_de_volume(pasta), start=1):
        conteudo = arq.read_bytes()
        r = processar_arquivo(conteudo, arq.name, hoje)
        cargas.append({
            "id": i, "arquivo": arq.name, "sha256": provenance.sha256_bytes(conteudo), "lidas": r.lidas,
            "validas": len(r.obs), "rejeitadas": r.rejeitadas[:50], "n_rejeitadas": len(r.rejeitadas),
            "duplicadas": r.duplicadas, "mapeamento": r.mapeamento,
        })
        for o in r.obs:  # arquivos posteriores (ordem alfabética) prevalecem na visão vigente
            obs[(o["res"], o["data"])] = {**o, "carga": i}
    volume = {"gerado_em": _agora(), "cargas": cargas, "obs": sorted(obs.values(), key=lambda o: (o["res"], o["data"]))}
    status = {
        "id": "planilhas_volume", "nome": "Planilhas de volume útil (data/manual/volume)", "url": None,
        "verificado_em": _agora(), "status": "verificado" if obs else "sem_dados",
        "mensagem": f"{len(cargas)} arquivo(s), {len(obs)} observação(ões) válidas",
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
            out["reservatorios"][res] = {"ultima_observacao": u, "enquadramento": r.as_dict()}
    return out


def executar(raiz: Path, saida: Path, hoje: date | None = None, baixar: bool = True, settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    hoje = hoje or datetime.now(timezone.utc).date()
    raw_dir = raiz / "data" / "raw"

    enos, st_enos = etapa_enos(raw_dir, baixar, settings.http_timeout)
    volume, st_vol = etapa_volume(raiz / "data" / "manual" / "volume", hoje)
    telemetria, st_ana = etapa_ana(raw_dir) if baixar else ({}, [])
    indicadores = etapa_indicadores(volume, hoje, settings.max_defasagem_observacao_dias)
    status = {"gerado_em": _agora(), "fontes": [st_enos, st_vol, *st_ana]}

    dados = saida / "data"
    dados.mkdir(parents=True, exist_ok=True)
    for nome, conteudo in {"enos.json": enos, "volume.json": volume, "telemetria.json": telemetria,
                           "indicadores.json": indicadores, "status.json": status}.items():
        (dados / nome).write_text(json.dumps(conteudo, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    pagina = raiz / "web" / "index.html"
    if pagina.exists():
        shutil.copyfile(pagina, saida / "index.html")
    return status


def resumo(status: dict) -> str:
    return "\n".join(f"- {f['nome']}: {f['status']} — {f.get('mensagem', '')}" for f in status["fontes"])


__all__ = ["executar", "resumo"]
