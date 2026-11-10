"""Diagnóstico das fontes externas: acessibilidade, formato e links de dados.

Uso (roda no GitHub Actions, onde a rede alcança as fontes oficiais):
    python scripts/diagnosticar_fontes.py [URL ...]

Sem argumentos, testa a lista padrão abaixo. Para páginas HTML, lista links que parecem
levar a dados; para JSON de portais ArcGIS, lista itens/serviços. Não grava nada no banco:
é ferramenta de investigação, para confirmar endpoints antes de codificar um adaptador.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urljoin

import httpx

PADRAO = [
    "https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt",
    # SIRH-DF (ADASA) é um portal ArcGIS; /sharing/rest/search e /rest/services são APIs padrão do ArcGIS.
    "https://gis.adasa.df.gov.br/portal/sharing/rest/search?q=reservatorio&f=json&num=100",
    "https://gis.adasa.df.gov.br/portal/sharing/rest/search?q=Descoberto&f=json&num=100",
    "https://gis.adasa.df.gov.br/portal/sharing/rest/search?q=volume&f=json&num=100",
    "https://gis.adasa.df.gov.br/server/rest/services?f=json",
    "https://gis.adasa.df.gov.br/arcgis/rest/services?f=json",
    "https://gis.adasa.df.gov.br/portal/home/index.html",
    "https://www.adasa.df.gov.br/17-pagina/1317-relatorio-dos-reservatorios",
    "https://www.adasa.df.gov.br/29-nivel-de-reservatorio",
    "https://www.ana.gov.br/sar/",
]

CHAVES = re.compile(r"reserv|descoberto|santa|barragem|sar|dashboard|arcgis|rest/services|csv|xls|json|download|serie|histor|nivel|volume|monitor", re.I)


def resumir_json(dados: object) -> None:
    if isinstance(dados, dict) and "results" in dados:  # busca do portal ArcGIS
        print(f"  total={dados.get('total')}")
        for it in dados["results"][:100]:
            print(f"  · [{it.get('type')}] {it.get('title')} | id={it.get('id')} | url={it.get('url')} | owner={it.get('owner')}")
        return
    if isinstance(dados, dict) and ("services" in dados or "folders" in dados):  # ArcGIS Server
        print(f"  folders={dados.get('folders')}")
        for s in dados.get("services", [])[:200]:
            print(f"  · {s.get('type')}: {s.get('name')}")
        return
    texto = json.dumps(dados, ensure_ascii=False)
    print("  json:", texto[:1500])


def listar_formularios(html: str) -> None:
    for fm in re.finditer(r"(?is)<form\b([^>]*)>(.*?)</form>", html):
        attrs, corpo = fm.group(1), fm.group(2)
        print("  form:", re.sub(r"\s+", " ", attrs.strip())[:200])
        for inp in re.findall(r"(?is)<input\b[^>]*>", corpo):
            nome = re.search(r'name=["\']([^"\']+)', inp)
            if nome:
                valor = re.search(r'value=["\']([^"\']*)', inp)
                tipo_inp = re.search(r'type=["\']([^"\']+)', inp)
                print(f"    input {nome.group(1)} type={tipo_inp.group(1) if tipo_inp else '?'} value={valor.group(1)[:40] if valor else ''}")
        for sel in re.finditer(r"(?is)<select\b([^>]*)>(.*?)</select>", corpo):
            nome = re.search(r'(?:name|id)=["\']([^"\']+)', sel.group(1))
            opcoes = re.findall(r'(?is)<option[^>]*value=["\']([^"\']*)["\'][^>]*>(.*?)</option>', sel.group(2))
            print(f"    select {nome.group(1) if nome else '?'}: {len(opcoes)} opções")
            for v, t in opcoes[:400]:
                t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
                if len(opcoes) <= 40 or re.search(r"(?i)descoberto|santa maria|df|distrito|paranoa|paranoá", t):
                    print(f"      {v} = {t}")


def diagnosticar(url: str, cliente: httpx.Client) -> None:
    print(f"\n=== {url}")
    try:
        r = cliente.get(url)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERRO {type(exc).__name__}: {exc}")
        return
    tipo = r.headers.get("content-type", "")
    print(f"  HTTP {r.status_code} | {tipo} | {len(r.content)} bytes | final={r.url}")
    if r.status_code >= 400:
        print("  corpo:", r.text[:300].replace("\n", " "))
        return
    if "json" in tipo or r.text.lstrip().startswith(("{", "[")):
        try:
            resumir_json(r.json())
            return
        except ValueError:
            pass
    if "html" in tipo:
        listar_formularios(r.text)
        for m in re.finditer(r"(?i)descoberto|santa\s*maria|distrito\s*federal", r.text):
            trecho = re.sub(r"\s+", " ", r.text[max(0, m.start() - 160): m.end() + 160])
            print("  menção:", trecho)
        for m in re.findall(r"acessar\([^)]*\)", r.text)[:20]:
            print("  js:", m)
        links = sorted(set(re.findall(r"""(?:href|src|action)=["']([^"'#]+)["']""", r.text)))
        alvo = [urljoin(str(r.url), l) for l in links if CHAVES.search(l)]
        print(f"  links relevantes ({len(alvo)} de {len(links)}):")
        for l in alvo[:80]:
            print("  ·", l)
        urls_js = sorted(set(re.findall(r"https?://[^\s\"'<>]+", r.text)))
        extras = [u for u in urls_js if CHAVES.search(u) and u not in alvo][:40]
        if extras:
            print("  urls no código da página:")
            for u in extras:
                print("  ·", u)
        return
    linhas = r.text.splitlines()
    print("  início:", " | ".join(linhas[:4]))
    print("  fim:   ", " | ".join(linhas[-3:]))


def main(urls: list[str]) -> None:
    with httpx.Client(timeout=40, follow_redirects=True, headers={"User-Agent": "aqua-foresight-diagnostico/0.2 (+github.com/Lucsmeee/aqua-foresight)"}) as c:
        for u in urls or PADRAO:
            diagnosticar(u, c)


if __name__ == "__main__":
    main(sys.argv[1:])
