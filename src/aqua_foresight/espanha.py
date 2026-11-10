"""Etapa Espanha (Júcar) do pipeline: coleta, versionamento em data/series e resumo para o painel."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from aqua_foresight.ingestion import es_jucar as es

CAMPOS_SEMANAL = ["data", "ambito", "capacidade_hm3", "volume_hm3", "pct", "n_represas"]
CAMPOS_PES = ["mes", "ute", "nome", "iee", "informe"]


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meses_anteriores(hoje: date, n: int) -> list[str]:
    out, a, m = [], hoje.year, hoje.month
    for _ in range(n):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        out.append(f"{a % 100:02d}{m:02d}")
    return out


def atualizar_miteco(pasta: Path, forcar: bool = False) -> dict:
    meta_p = pasta / "es_miteco_meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    st = {"id": "miteco_embalses", "nome": "MITECO · Boletim Hidrológico (reservas semanais, Júcar)", "url": es.URL_MITECO,
          "verificado_em": _agora()}
    try:
        h = httpx.head(es.URL_MITECO, timeout=60, follow_redirects=True)
        assinatura = h.headers.get("etag") or h.headers.get("last-modified")
        if not forcar and assinatura and assinatura == meta.get("assinatura") and (pasta / "es_jucar_semanal.csv").exists():
            st.update(status="verificado", mensagem="sem atualização desde a última coleta")
            return st
        r = httpx.get(es.URL_MITECO, timeout=300, follow_redirects=True)
        r.raise_for_status()
        linhas = es.agregar_jucar(es.extrair_csv_do_zip(r.content))
        if not linhas:
            raise ValueError("nenhuma linha do Júcar encontrada no banco")
        es.gravar_csv(pasta / "es_jucar_semanal.csv", linhas, CAMPOS_SEMANAL)
        from aqua_foresight.ingestion.provenance import sha256_bytes

        meta = {"assinatura": assinatura, "sha256_zip": sha256_bytes(r.content), "bytes": len(r.content), "coletado_em": _agora(),
                "ultima_semana": linhas[-1]["data"]}
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        st.update(status="verificado", mensagem=f"{len(linhas)} registros semanais; última semana {linhas[-1]['data']}")
    except Exception as exc:  # noqa: BLE001
        st.update(status="falha", mensagem=f"{type(exc).__name__}: {exc}"[:300])
    return st


def atualizar_chj(pasta: Path, meses: list[str]) -> dict:
    """Baixa e lê os informes da CHJ (AAMM), do mais antigo ao mais novo; o mais novo prevalece."""
    caminho = pasta / "es_jucar_pes_mensal.csv"
    atuais = {(l["mes"], l["ute"]): l for l in es.ler_csv(caminho)}
    st = {"id": "chj_pes", "nome": "CHJ · Informe mensal de seca e escassez (PES)", "url": es.URL_CHJ.format(aamm="AAMM"),
          "verificado_em": _agora()}
    lidos, ausentes, erros = [], [], []
    for aamm in sorted(meses):
        try:
            pdf = es.baixar_informe(aamm)
            if pdf is None:
                ausentes.append(aamm)
                continue
            r = es.parse_informe_chj(es._texto_pdf(pdf))
            if not r["iee_ute"]:
                erros.append(f"{aamm}: tabela não reconhecida")
                continue
            for x in r["iee_ute"]:
                atuais[(x["mes"], x["ute"])] = {**x, "informe": aamm}
            mes = r["mes_referencia"]
            for chave in ("global_escasez", "global_sequia", "ve07"):
                if r.get(chave) is not None:
                    atuais[(mes, chave)] = {"mes": mes, "ute": chave, "nome": chave, "iee": r[chave], "informe": aamm}
            lidos.append(aamm)
        except Exception as exc:  # noqa: BLE001
            erros.append(f"{aamm}: {type(exc).__name__}: {exc}"[:120])
    es.gravar_csv(caminho, sorted(atuais.values(), key=lambda l: (l["mes"], l["ute"])), CAMPOS_PES)
    status = "verificado" if lidos else ("falha" if erros else "sem_dados")
    st.update(status=status, mensagem=f"lidos {lidos or '—'}; não publicados {ausentes or '—'}; erros {erros or '—'}"[:300])
    return st


def etapa_espanha(raiz: Path, baixar: bool, hoje: date) -> tuple[dict, list[dict]]:
    pasta = raiz / "data" / "series"
    status = []
    if baixar:
        status.append(atualizar_miteco(pasta))
        status.append(atualizar_chj(pasta, _meses_anteriores(hoje, 3)))
    return resumo_painel(pasta), status


def resumo_painel(pasta: Path) -> dict:
    sem = es.ler_csv(pasta / "es_jucar_semanal.csv")
    pes = es.ler_csv(pasta / "es_jucar_pes_mensal.csv")
    series = {}
    for amb in ("sistema_act", "demarcacion"):
        ls = [l for l in sem if l["ambito"] == amb]
        series[amb] = {"d": [l["data"] for l in ls], "v": [float(l["pct"]) for l in ls],
                       "cap": float(ls[-1]["capacidade_hm3"]) if ls else None}
    iee = {}
    for chave in ("05", "global_escasez", "global_sequia", "ve07"):
        ls = sorted((l for l in pes if l["ute"] == chave), key=lambda l: l["mes"])
        iee[chave] = {"m": [l["mes"] for l in ls], "v": [float(l["iee"]) for l in ls], "informe": ls[-1]["informe"] if ls else None}
    utes_ultimo = {}
    if pes:
        ultimo = max(l["mes"] for l in pes if l["ute"].isdigit()) if any(l["ute"].isdigit() for l in pes) else None
        utes_ultimo = {l["ute"]: {"nome": l["nome"], "iee": float(l["iee"]), "faixa": es.faixa_iee(float(l["iee"]))}
                       for l in pes if l["mes"] == ultimo and l["ute"].isdigit()}
    return {"series": series, "iee": iee, "utes_ultimo_mes": utes_ultimo}
