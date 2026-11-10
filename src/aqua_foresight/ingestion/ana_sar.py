"""Adaptador ANA · SAR (Sistema de Acompanhamento de Reservatórios), módulo Distrito Federal.

Endpoints identificados no próprio portal do SAR (páginas sarportal/grafico-por-reservatorio.html e
sarportal/outras-modulo-1.html?tipoSistema=4, que os chamam via AJAX) e verificados em 10/11/2026
pelo workflow "Diagnosticar fontes":

- GET https://www.ana.gov.br/sar/restportal/api/retornaMedicoes?data=MM/dd/yyyy&siglaUf=&tipoSistema=4
  → lista com DESCOBERTO, SANTA MARIA, LAGO PARANOÁ e TOTAL: capacidade (hm³), cota (m), volume (hm³),
    volumeUtil (% = volume/capacidade) e data (dd/MM/yyyy).
  ATENÇÃO: o parâmetro `data` é lido como MÊS/DIA/ANO (verificado: 11/09/2026 → 09/11/2026).
- GET https://www.ana.gov.br/sar/restportal/api/retornaGrafico?codigo=40001|40002
  → serie1..serie5 (um ano cada, `listaAno`), itens {data: "MM-dd", volume (hm³), cota (m)}; "NaN" = sem dado.

Não há documentação pública dessa API; ela pode mudar sem aviso. Falhas ficam registradas no status.
Valores "-" ou "NaN" são tratados como ausentes, nunca como zero.
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx

BASE = "https://www.ana.gov.br/sar/restportal/api"
CODIGOS = {"descoberto": 40001, "santa_maria": 40002}
NOMES_API = {"DESCOBERTO": "descoberto", "SANTA MARIA": "santa_maria"}
CAMPOS = ["data", "reservatorio", "cota_m", "volume_hm3", "capacidade_hm3", "pct_sar", "endpoint"]
USER_AGENT = "aqua-foresight/0.3 (pesquisa academica; github.com/Lucsmeee/aqua-foresight)"


def _num(v: object) -> float | None:
    s = str(v if v is not None else "").strip()
    if s in {"", "-", "NaN", "nan", "null", "None"}:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


@dataclass
class Registro:
    data: str  # ISO
    reservatorio: str
    cota_m: float | None
    volume_hm3: float | None
    capacidade_hm3: float | None
    pct_sar: float | None
    endpoint: str

    def linha(self) -> dict:
        return {k: ("" if getattr(self, k) is None else getattr(self, k)) for k in CAMPOS}


def parse_medicoes(itens: list[dict], data_pedida: date) -> list[Registro]:
    out = []
    for it in itens:
        res = NOMES_API.get(str(it.get("reservatorio") or "").strip().upper())
        if not res:
            continue
        d = str(it.get("data") or "")
        if d in ("", "-"):
            continue  # sem medição nesta data
        dia, mes, ano = (int(x) for x in d.split("/"))
        devolvida = date(ano, mes, dia)
        if devolvida != data_pedida:
            raise ValueError(f"API devolveu {devolvida} para a data pedida {data_pedida}: formato de data mudou?")
        cap, vol = _num(it.get("capacidade")), _num(it.get("volume"))
        pct = _num(it.get("volumeUtil"))
        if pct is None and cap and vol is not None:
            pct = round(vol / cap * 100, 2)
        out.append(Registro(devolvida.isoformat(), res, _num(it.get("cota")), vol, cap, pct, "retornaMedicoes"))
    return out


def parse_grafico(corpo: dict, reservatorio: str) -> list[Registro]:
    anos = [int(a) for a in corpo.get("listaAno") or []]
    cap = _num(corpo.get("capacidade"))
    out = []
    for i, ano in enumerate(anos, start=1):
        for it in corpo.get(f"serie{i}") or []:
            mes, dia = (int(x) for x in str(it["data"]).split("-"))
            try:
                d = date(ano, mes, dia)
            except ValueError:
                continue
            vol, cota = _num(it.get("volume")), _num(it.get("cota"))
            if vol is None and cota is None:
                continue
            pct = round(vol / cap * 100, 2) if (cap and vol is not None) else None
            out.append(Registro(d.isoformat(), reservatorio, cota, vol, cap, pct, "retornaGrafico"))
    return out


class ClienteSAR:
    def __init__(self, timeout: float = 40.0, pausa: float = 0.15, client: httpx.Client | None = None):
        self.http = client or httpx.Client(base_url=BASE, timeout=timeout, headers={"User-Agent": USER_AGENT})
        self.pausa = pausa

    def _get(self, rota: str, params: dict) -> object:
        for tentativa in range(3):
            try:
                r = self.http.get(rota, params=params)
                if r.status_code == 200:
                    return r.json()
                if r.status_code < 500:
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}: {r.text[:200]}", request=r.request, response=r)
            except (httpx.TransportError, ValueError):
                if tentativa == 2:
                    raise
            time.sleep(2 * (tentativa + 1))
        raise RuntimeError(f"{rota} falhou após 3 tentativas")

    def medicoes(self, d: date) -> list[Registro]:
        itens = self._get("/retornaMedicoes", {"data": d.strftime("%m/%d/%Y"), "siglaUf": "", "tipoSistema": 4})
        time.sleep(self.pausa)
        return parse_medicoes(itens, d)  # type: ignore[arg-type]

    def grafico(self, reservatorio: str) -> list[Registro]:
        corpo = self._get("/retornaGrafico", {"codigo": CODIGOS[reservatorio]})
        return parse_grafico(corpo, reservatorio)  # type: ignore[arg-type]


# ---------- armazenamento canônico (CSV versionado) ----------

def ler_serie(caminho: Path) -> dict[tuple[str, str], dict]:
    if not caminho.exists():
        return {}
    with caminho.open(encoding="utf-8") as f:
        return {(r["data"], r["reservatorio"]): r for r in csv.DictReader(f)}


def gravar_serie(caminho: Path, linhas: dict[tuple[str, str], dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS, lineterminator="\n")
        w.writeheader()
        for k in sorted(linhas):
            w.writerow({c: linhas[k].get(c, "") for c in CAMPOS})
    tmp.replace(caminho)


def mesclar(existente: dict, novos: list[Registro]) -> int:
    """Insere/atualiza. Dado de retornaMedicoes (consulta do dia) prevalece sobre retornaGrafico."""
    alterados = 0
    for r in novos:
        k = (r.data, r.reservatorio)
        nova = {c: str(v) for c, v in r.linha().items()}
        atual = existente.get(k)
        if atual == nova:
            continue
        if atual and atual.get("endpoint") == "retornaMedicoes" and r.endpoint == "retornaGrafico":
            continue
        existente[k] = nova
        alterados += 1
    return alterados


def dias_faltantes(existente: dict, inicio: date, fim: date) -> list[date]:
    tem = {d for d, _ in existente}
    out, d = [], inicio
    while d <= fim:
        if d.isoformat() not in tem:
            out.append(d)
        d += timedelta(days=1)
    return out
