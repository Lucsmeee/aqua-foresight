"""Espanha · Demarcação Hidrográfica do Júcar — par de comparação do piloto do DF (decisão D-02: Júcar).

Duas fontes oficiais, ambas verificadas em 10/11/2026 pelo workflow "Diagnosticar fontes":

1. MITECO · Boletim Hidrológico — histórico semanal de reservas por represa (> 5 hm³) desde 1988:
   https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/evaluacion-de-los-recursos-hidricos/boletin-hidrologico/Historico-de-embalses/BD-Embalses.zip
   ZIP com banco Access (BD-Embalses.mdb), tabela "T_Datos Embalses 1988-2026":
   AMBITO_NOMBRE, EMBALSE_NOMBRE, FECHA (MM/DD/AA hh:mm:ss — mês/dia/ano), AGUA_TOTAL (capacidade, hm³),
   AGUA_ACTUAL (volume, hm³; vírgula decimal), ELECTRICO_FLAG (1 = uso hidrelétrico).
   Leitura do .mdb exige `mdbtools` (mdb-export). Dados provisórios, sujeitos a revisão pelo MITECO.

2. Confederação Hidrográfica do Júcar (CHJ) · "Informe de seguimiento de la sequía y la escasez", mensal:
   https://www.chj.es/es-es/medioambiente/gestionsequia/Documents/Informes%20Seguimiento/Informe_Sequias_AAMM.pdf
   Traz o Índice de Estado de Escassez (IEE, 0–1) das 9 Unidades Territoriais de Escassez (UTE) nos últimos
   12 meses (Tabla 7), o indicador global de escassez (Tabla 10) e o de seca prolongada (Tabla 9).
   Faixas do IEE (Tabla 2 do informe): Normalidad 1,00–0,50 · Prealerta 0,49–0,30 · Alerta 0,29–0,15 ·
   Emergencia 0,14–0,00. O CENÁRIO declarado depende também de regras de permanência do PES; aqui se mostra
   a FAIXA do índice, não o cenário oficial.
   Desde 16/06/2026 vale o PES revisado pela Orden TED/601/2026; meses anteriores seguem o PES de 2018.
"""

from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

URL_MITECO = ("https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/evaluacion-de-los-recursos-hidricos/"
              "boletin-hidrologico/Historico-de-embalses/BD-Embalses.zip")
URL_CHJ = "https://www.chj.es/es-es/medioambiente/gestionsequia/Documents/Informes%20Seguimiento/Informe_Sequias_{aamm}.pdf"
TABELA_MDB = "T_Datos Embalses 1988-2026"
SISTEMA_ACT = ("Alarcón", "Contreras", "Tous")  # indicador VE07 do PES do Júcar
MESES_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
UTES = {"01": "Cenia-Maestrazgo", "02": "Mijares-Plana de Castellón", "03": "Palancia-Los Valles", "04": "Turia",
        "05": "Júcar", "06": "Serpis", "07": "Marina Alta", "08": "Marina Baja", "09": "Vinalopó-Alacantí"}


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()


def _num(s: str) -> float | None:
    s = (s or "").strip().replace(".", "").replace(",", ".") if "," in (s or "") else (s or "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def faixa_iee(v: float) -> str:
    """Faixa do IEE pela Tabla 2 do informe da CHJ (não é o cenário declarado)."""
    if v >= 0.50:
        return "normalidad"
    if v >= 0.30:
        return "prealerta"
    if v >= 0.15:
        return "alerta"
    return "emergencia"


# ---------------- MITECO: reservas semanais ----------------

def extrair_csv_do_zip(conteudo_zip: bytes) -> str:
    if not shutil.which("mdb-export"):
        raise RuntimeError("mdbtools não instalado (apt-get install mdbtools)")
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        nome = next(n for n in z.namelist() if n.lower().endswith(".mdb"))
        with tempfile.NamedTemporaryFile(suffix=".mdb") as f:
            f.write(z.read(nome))
            f.flush()
            r = subprocess.run(["mdb-export", f.name, TABELA_MDB], capture_output=True, text=True, check=True)
    return r.stdout


def agregar_jucar(csv_texto: str) -> list[dict]:
    """Soma semanal para a demarcação do Júcar e para o sistema Alarcón+Contreras+Tous."""
    acc: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    alvo = {_norm(n) for n in SISTEMA_ACT}
    for row in csv.DictReader(io.StringIO(csv_texto)):
        if _norm(row["AMBITO_NOMBRE"]) != "jucar":
            continue
        m = re.match(r"(\d{2})/(\d{2})/(\d{2})", row["FECHA"])
        if not m:
            continue
        mes, dia, aa = (int(x) for x in m.groups())
        ano = 1900 + aa if aa >= 80 else 2000 + aa
        try:
            d = date(ano, mes, dia).isoformat()
        except ValueError:
            continue
        cap, vol = _num(row["AGUA_TOTAL"]), _num(row["AGUA_ACTUAL"])
        if cap is None or vol is None or cap <= 0:
            continue
        for chave in ("demarcacion", *(["sistema_act"] if _norm(row["EMBALSE_NOMBRE"]) in alvo else [])):
            a = acc[(d, chave)]
            a[0] += cap
            a[1] += vol
            a[2] += 1
    out = []
    for (d, chave), (cap, vol, n) in sorted(acc.items()):
        if chave == "sistema_act" and n < len(SISTEMA_ACT):
            continue  # semana sem as três represas: não comparável
        out.append({"data": d, "ambito": chave, "capacidade_hm3": round(cap, 1), "volume_hm3": round(vol, 1),
                    "pct": round(vol / cap * 100, 2), "n_represas": n})
    return out


# ---------------- CHJ: índices mensais do PES ----------------

def _texto_pdf(conteudo: bytes, paginas: tuple[int, int] = (6, 14)) -> str:
    from pypdf import PdfReader

    leitor = PdfReader(io.BytesIO(conteudo))
    return "\n".join((leitor.pages[i].extract_text() or "") for i in range(paginas[0] - 1, min(paginas[1], len(leitor.pages))))


def parse_informe_chj(texto: str) -> dict:
    """Extrai IEE por UTE (12 meses), indicador global de escassez e de seca prolongada do mês."""
    plano = re.sub(r"\s+", " ", texto)
    out: dict = {"iee_ute": [], "global_escasez": None, "global_sequia": None, "mes_referencia": None}

    # Tabla 7: cabeçalho "UTE sep- 25 oct- 25 … ago- 26" seguido de 9 linhas com 12 valores
    cab = re.search(r"UTE\s+((?:[a-z]{3}-\s*\d{2}\s+){11}[a-z]{3}-\s*\d{2})", plano)
    fim7 = plano.find("Tabla 7")
    if cab and fim7 > cab.end():
        meses = [(2000 + int(a), MESES_ES[m]) for m, a in re.findall(r"([a-z]{3})-\s*(\d{2})", cab.group(1))]
        corpo = plano[cab.end():fim7]
        for cod, nums in re.findall(r"UTE (\d{2})\.\s*[^\d]+?((?:\d,\d{2}\s+){11}\d,\d{2})", corpo):
            vals = [float(x.replace(",", ".")) for x in nums.split()]
            for (ano, mes), v in zip(meses, vals):
                out["iee_ute"].append({"mes": f"{ano}-{mes:02d}", "ute": cod, "nome": UTES.get(cod, cod), "iee": v})
        out["mes_referencia"] = f"{meses[-1][0]}-{meses[-1][1]:02d}"

    # Tabla 10: 9 IEE das UTE, global, e zonas norte/central/sul (global = média das zonas, ou mínimo se < 0,3)
    m10 = re.search(r"IES ((?:\d,\d{2}\s+){12}\d,\d{2})\s*Tabla 10", plano)
    if m10:
        v = [float(x.replace(",", ".")) for x in m10.group(1).split()]
        glob, zonas = v[9], v[10:13]
        esperado = min(zonas) if min(zonas) < 0.3 else sum(zonas) / 3
        if abs(esperado - glob) <= 0.015:
            out["global_escasez"] = glob
            out["zonas_escasez"] = dict(zip(("norte", "central", "sur"), zonas))

    # Tabla 9: 13 coeficientes de área, global, 13 IES das UTS (global = soma ponderada)
    m9 = re.search(r"Coef\. ((?:\d,\d{2}\s+){13})(\d,\d{2}) IES ((?:\d,\d{2}\s+){12}\d,\d{2})", plano)
    if m9:
        coef = [float(x.replace(",", ".")) for x in m9.group(1).split()]
        ies = [float(x.replace(",", ".")) for x in m9.group(3).split()]
        glob = float(m9.group(2).replace(",", "."))
        if abs(sum(c * i for c, i in zip(coef, ies)) - glob) <= 0.02:
            out["global_sequia"] = glob

    m7 = re.search(r"VE07 Volumen embalsado en Alarc[oó]n, Contreras y Tous (\d,\d{2})", plano)
    if m7:
        out["ve07"] = float(m7.group(1).replace(",", "."))
    return out


def baixar_informe(aamm: str, timeout: float = 90.0) -> bytes | None:
    import httpx

    r = httpx.get(URL_CHJ.format(aamm=aamm), timeout=timeout, follow_redirects=True,
                  headers={"User-Agent": "aqua-foresight/0.4 (pesquisa academica)"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    if "pdf" not in r.headers.get("content-type", ""):
        return None
    return r.content


# ---------------- armazenamento ----------------

def gravar_csv(caminho: Path, linhas: list[dict], campos: list[str]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, lineterminator="\n")
        w.writeheader()
        for l in linhas:
            w.writerow({c: l.get(c, "") for c in campos})


def ler_csv(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    with caminho.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))
