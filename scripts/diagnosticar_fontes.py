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
