"""Baixa geometrias para o Mapa de Bacias (RF-02) e grava GeoJSON simplificado em data/geo/.

Fontes:
- IBGE, API de malhas v3 — limite oficial do Distrito Federal (código 53).
  (com cópia da malha municipal do IBGE no GitHub como alternativa).
- OpenStreetMap via Overpass API (com espelhos) — espelhos d'água dos reservatórios (ODbL, © colaboradores do OSM).
- Províncias da Espanha por onde passa a bacia do Júcar (GeoJSON público no GitHub).

Cada fonte é opcional: se falhar, as demais continuam e a falha é registrada em data/geo/meta.json.
Uso: python scripts/baixar_geometrias.py [pasta_saida]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

IBGE_DF = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/53?formato=application/vnd.geo+json&qualidade=intermediaria"
# Cópia da malha municipal do IBGE (DF = município 5300108) mantida no GitHub; usada se a API do IBGE não responder.
IBGE_DF_ESPELHO = "https://raw.githubusercontent.com/tbrugz/geodata-br/master/geojson/geojs-53-mun.json"
ES_PROVINCIAS = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/spain-provinces.geojson"
PROVINCIAS_JUCAR = {"Cuenca", "Albacete", "València/Valencia", "Teruel", "Castelló/Castellón", "Alacant/Alicante",
                    "Tarragona", "Murcia"}
OVERPASS_ESPELHOS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

CONSULTAS = {
    "df_reservatorios": """[out:json][timeout:90];
(way["natural"="water"]["name"~"Descoberto|Santa Maria",i](-16.10,-48.35,-15.45,-47.75);
 relation["natural"="water"]["name"~"Descoberto|Santa Maria",i](-16.10,-48.35,-15.45,-47.75););
out geom;""",
    "es_reservatorios": """[out:json][timeout:90];
(way["natural"="water"]["name"~"Alarc|Contreras|Tous",i](38.90,-2.40,39.85,-0.40);
 relation["natural"="water"]["name"~"Alarc|Contreras|Tous",i](38.90,-2.40,39.85,-0.40););
out geom;""",
}


def _dist_seg(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** 0.5


def simplificar(pts: list, tol: float) -> list:
    """Douglas–Peucker iterativo."""
    if len(pts) < 3:
        return pts
    manter = [False] * len(pts)
    manter[0] = manter[-1] = True
    pilha = [(0, len(pts) - 1)]
    while pilha:
        i, j = pilha.pop()
        dmax, k = 0.0, None
        for m in range(i + 1, j):
            d = _dist_seg(pts[m], pts[i], pts[j])
            if d > dmax:
                dmax, k = d, m
        if k is not None and dmax > tol:
            manter[k] = True
            pilha += [(i, k), (k, j)]
    return [[round(x, 5), round(y, 5)] for (x, y), f in zip(pts, manter) if f]


def costurar(linhas: list[list]) -> list[list]:
    """Une segmentos (membros de relação OSM) em anéis pelos pontos extremos."""
    restantes = [list(l) for l in linhas if len(l) >= 2]
    aneis = []
    while restantes:
        anel = restantes.pop(0)
        mudou = True
        while anel[0] != anel[-1] and mudou:
            mudou = False
            for idx, l in enumerate(restantes):
                if l[0] == anel[-1]:
                    anel += l[1:]
                elif l[-1] == anel[-1]:
                    anel += l[-2::-1]
                elif l[-1] == anel[0]:
                    anel = l[:-1] + anel
                elif l[0] == anel[0]:
                    anel = l[::-1][:-1] + anel
                else:
                    continue
                restantes.pop(idx)
                mudou = True
                break
        aneis.append(anel)
    return aneis


def osm_para_geojson(dados: dict, tol: float) -> dict:
    feats = []
    for el in dados.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            linhas = [[[g["lon"], g["lat"]] for g in el["geometry"]]]
        elif el["type"] == "relation":
            linhas = [[[g["lon"], g["lat"]] for g in m["geometry"]]
                      for m in el.get("members", []) if m.get("role") in ("outer", "") and "geometry" in m]
            linhas = costurar(linhas)
        else:
            continue
        aneis = [simplificar(l, tol) for l in linhas if len(l) >= 4]
        aneis = [a for a in aneis if len(a) >= 4]
        if not aneis:
            continue
        feats.append({"type": "Feature",
                      "properties": {"nome": tags.get("name"), "osm": f"{el['type']}/{el['id']}"},
                      "geometry": {"type": "MultiPolygon", "coordinates": [[a] for a in aneis]}})
    return {"type": "FeatureCollection", "features": feats}


def simplificar_geojson(gj: dict, tol: float) -> dict:
    for f in gj.get("features", []):
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        g["type"], g["coordinates"] = "MultiPolygon", [[simplificar(r, tol) for r in p] for p in polys]
    return gj


def _overpass(c: httpx.Client, consulta: str) -> tuple[dict, str]:
    erros = []
    for url in OVERPASS_ESPELHOS:
        for tentativa in range(2):
            try:
                r = c.post(url, data={"data": consulta})
                r.raise_for_status()
                return r.json(), url
            except Exception as e:  # noqa: BLE001
                erros.append(f"{url} #{tentativa + 1}: {type(e).__name__}")
                time.sleep(5)
    raise RuntimeError("; ".join(erros))


def main(saida: Path) -> int:
    saida.mkdir(parents=True, exist_ok=True)
    meta = {"gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fontes": {}}
    with httpx.Client(timeout=200, headers={"User-Agent": "aqua-foresight/0.5 (pesquisa academica)"}, follow_redirects=True) as c:
        erros = []
        for url, rotulo in ((IBGE_DF, "IBGE — API de malhas v3"),
                            (IBGE_DF_ESPELHO, "IBGE, malha municipal (cópia tbrugz/geodata-br no GitHub)")):
            try:
                r = c.get(url, timeout=60)
                r.raise_for_status()
                gj = simplificar_geojson(r.json(), 0.002)
                (saida / "df_limite.geojson").write_text(json.dumps(gj, separators=(",", ":")), encoding="utf-8")
                meta["fontes"]["df_limite"] = {"status": "ok", "url": url, "fonte": rotulo, "feicoes": len(gj.get("features", []))}
                break
            except Exception as e:  # noqa: BLE001
                erros.append(f"{url}: {e!r}"[:200])
        else:
            meta["fontes"]["df_limite"] = {"status": "falha", "erro": " | ".join(erros)}
        try:
            r = c.get(ES_PROVINCIAS, timeout=120)
            r.raise_for_status()
            gj = r.json()
            gj["features"] = [{"type": "Feature", "properties": {"nome": f["properties"].get("name")}, "geometry": f["geometry"]}
                              for f in gj["features"] if f["properties"].get("name") in PROVINCIAS_JUCAR]
            gj = simplificar_geojson(gj, 0.01)
            (saida / "es_provincias.geojson").write_text(json.dumps(gj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
            meta["fontes"]["es_provincias"] = {"status": "ok", "url": ES_PROVINCIAS,
                                               "fonte": "Províncias da Espanha (codeforgermany/click_that_hood, base IGN/CartoDB)",
                                               "feicoes": len(gj["features"]), "nomes": sorted(f["properties"]["nome"] for f in gj["features"])}
        except Exception as e:  # noqa: BLE001
            meta["fontes"]["es_provincias"] = {"status": "falha", "url": ES_PROVINCIAS, "erro": repr(e)[:300]}
        for nome, q in CONSULTAS.items():
            try:
                dados, url = _overpass(c, q)
                gj = osm_para_geojson(dados, 0.0004)
                (saida / f"{nome}.geojson").write_text(json.dumps(gj, separators=(",", ":"), ensure_ascii=False),
                                                       encoding="utf-8")
                meta["fontes"][nome] = {"status": "ok", "url": url, "fonte": "OpenStreetMap (ODbL) via Overpass",
                                        "feicoes": len(gj["features"]),
                                        "nomes": sorted({f["properties"]["nome"] or "?" for f in gj["features"]})}
            except Exception as e:  # noqa: BLE001
                meta["fontes"][nome] = {"status": "falha", "erro": str(e)[:600]}
    (saida / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/geo")))
