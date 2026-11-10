"""Leitura de planilhas de volume útil (CSV/XLSX), ex.: exportação do SAR/ANA, módulo Distrito Federal.

Mesmas regras do pipeline no navegador (web/index.html), para que os dois caminhos
produzam o mesmo resultado:
- detecta delimitador (; , tab), vírgula decimal e datas dd/mm/aaaa ou aaaa-mm-dd;
- identifica colunas de data, volume útil (%) e reservatório pelo cabeçalho;
- rejeita, com motivo: data inválida/futura, reservatório fora do piloto, valor não
  numérico ou fora de 0–100%; duplicatas no mesmo arquivo: vale a última.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


def _norm(s: object) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def identificar_reservatorio(v: object) -> str | None:
    s = _norm(v)
    if "descoberto" in s:
        return "descoberto"
    if "santa maria" in s or "santa_maria" in s:
        return "santa_maria"
    return None


def parse_num(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[%\s]", "", str(v or ""))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", s):
        return None
    return float(s)


def parse_data(v: object) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # série do Excel
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v or "").strip()
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
    try:
        if m:
            y = int(m.group(3))
            return date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
        m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def ler_linhas(conteudo: bytes, nome: str) -> list[list[object]]:
    if nome.lower().endswith(".xlsx"):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        return [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("cp1252")
    amostra = "\n".join(texto.splitlines()[:15])
    delim = max([";", "\t", ","], key=amostra.count)
    return [r for r in csv.reader(io.StringIO(texto), delimiter=delim) if any(str(c).strip() for c in r)]


def achar_cabecalho(rows: list[list[object]]) -> int:
    for i, r in enumerate(rows[:20]):
        if sum(1 for c in r if isinstance(c, str) and re.search(r"[A-Za-zÀ-ú]", c)) >= 2:
            return i
    return 0


def adivinhar_colunas(headers: list[object]) -> dict[str, int]:
    norm = [_norm(h) for h in headers]

    def achar(padrao: str) -> int:
        return next((i for i, h in enumerate(norm) if re.search(padrao, h)), -1)

    vol = achar(r"(volume|vol\.?).*(%|percent|util)|(%|percent).*(vol|util)|v\.?u\.?\s*\(?%")
    if vol < 0:
        vol = achar(r"%|percent")
    return {"data": achar(r"data|date|dia"), "vol": vol, "res": achar(r"reservat|barragem|manancial|nome")}


@dataclass
class ResultadoArquivo:
    obs: list[dict] = field(default_factory=list)  # {res, data(iso), valor}
    lidas: int = 0
    rejeitadas: list[dict] = field(default_factory=list)
    duplicadas: int = 0
    mapeamento: dict = field(default_factory=dict)


def processar_arquivo(conteudo: bytes, nome: str, hoje: date, reservatorio_fixo: str | None = None) -> ResultadoArquivo:
    rows = ler_linhas(conteudo, nome)
    out = ResultadoArquivo()
    if not rows:
        out.rejeitadas.append({"linha": "—", "motivo": "arquivo vazio"})
        return out
    hi = achar_cabecalho(rows)
    headers = [str(h) if h is not None else "" for h in rows[hi]]
    g = adivinhar_colunas(headers)
    if reservatorio_fixo is None and g["res"] < 0:
        reservatorio_fixo = identificar_reservatorio(nome)  # ex.: "descoberto_2025.csv"
    out.mapeamento = {
        "data": headers[g["data"]] if g["data"] >= 0 else None,
        "volume": headers[g["vol"]] if g["vol"] >= 0 else None,
        "reservatorio": reservatorio_fixo or (headers[g["res"]] if g["res"] >= 0 else None),
    }
    if g["data"] < 0 or g["vol"] < 0 or (g["res"] < 0 and not reservatorio_fixo):
        out.rejeitadas.append({"linha": "—", "motivo": f"colunas não identificadas no cabeçalho: {headers}"})
        return out

    validas: dict[tuple[str, str], dict] = {}
    for i, r in enumerate(rows[hi + 1 :], start=hi + 2):
        out.lidas += 1
        cel = lambda j: r[j] if j < len(r) else None  # noqa: E731
        d = parse_data(cel(g["data"]))
        if d is None:
            out.rejeitadas.append({"linha": i, "motivo": "data inválida"})
            continue
        if d > hoje:
            out.rejeitadas.append({"linha": i, "motivo": "data no futuro"})
            continue
        res = reservatorio_fixo or identificar_reservatorio(cel(g["res"]))
        if res is None:
            out.rejeitadas.append({"linha": i, "motivo": "reservatório fora do piloto"})
            continue
        v = parse_num(cel(g["vol"]))
        if v is None:
            out.rejeitadas.append({"linha": i, "motivo": "volume não numérico"})
            continue
        if not 0 <= v <= 100:
            out.rejeitadas.append({"linha": i, "motivo": "volume fora de 0–100%"})
            continue
        k = (res, d.isoformat())
        if k in validas:
            out.duplicadas += 1
        validas[k] = {"res": res, "data": d.isoformat(), "valor": v}
    out.obs = sorted(validas.values(), key=lambda o: (o["res"], o["data"]))
    return out


def arquivos_de_volume(pasta: Path) -> list[Path]:
    if not pasta.exists():
        return []
    return sorted(p for p in pasta.iterdir() if p.suffix.lower() in {".csv", ".txt", ".xlsx"} and p.is_file())
