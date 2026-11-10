"""CLI: `aqua init-db | seed | ingest-enos | enquadrar`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from aqua_foresight.config import get_settings
from aqua_foresight.db import init_db, make_engine, make_session_factory, session_scope
from aqua_foresight.ingestion import noaa_cpc
from aqua_foresight.legal.enquadramento import enquadrar
from aqua_foresight.legal.seed import carregar_base_normativa


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aqua", description="Aqua Foresight — utilitários de pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="Cria o esquema e carrega a base normativa do piloto")

    pe = sub.add_parser("ingest-enos", help="Ingere RONI/ONI do NOAA/CPC (download ou arquivo local)")
    pe.add_argument("--indicador", choices=["RONI", "ONI"], default="RONI")
    pe.add_argument("--arquivo", type=Path, help="Arquivo baixado manualmente do CPC")
    pe.add_argument("--sintetico", action="store_true", help="Marcar a carga como dado sintético de teste")

    pp = sub.add_parser("publicar", help="Executa o pipeline completo e gera o site estático com os dados")
    pp.add_argument("--saida", type=Path, default=Path("site"))
    pp.add_argument("--raiz", type=Path, default=Path("."))
    pp.add_argument("--sem-download", action="store_true", help="Não acessa a rede; usa só arquivos versionados")

    pq = sub.add_parser("enquadrar", help="Enquadramento indicativo (Res. ADASA 56/2025)")
    pq.add_argument("reservatorio", choices=["descoberto", "santa_maria"])
    pq.add_argument("valor_pct", type=float)
    pq.add_argument("--natureza", choices=["observado", "projetado"], required=True)
    pq.add_argument("--data-referencia", type=date.fromisoformat, default=date.today())
    pq.add_argument("--data-dado", type=date.fromisoformat)

    args = p.parse_args(argv)
    settings = get_settings()
    if args.cmd == "publicar":
        from aqua_foresight.publicar import executar, resumo

        status = executar(args.raiz, args.saida, baixar=not args.sem_download, settings=settings)
        print(resumo(status))
        return 0
    engine = make_engine()
    init_db(engine)
    factory = make_session_factory(engine)

    with session_scope(factory) as s:
        carregar_base_normativa(s)
        if args.cmd == "init-db":
            print(json.dumps({"status": "ok", "database_url": settings.database_url}))
            return 0
        if args.cmd == "ingest-enos":
            r = noaa_cpc.ingerir_indice_cpc(s, settings, args.indicador, args.arquivo, args.sintetico)
            print(json.dumps(r.__dict__, ensure_ascii=False, default=str, indent=2))
            return 0 if r.status == "sucesso" else 2
        if args.cmd == "enquadrar":
            r = enquadrar(
                s,
                args.reservatorio,
                args.data_referencia,
                args.valor_pct,
                args.natureza,
                args.data_dado,
                settings.max_defasagem_observacao_dias,
                ator="cli",
            )
            print(json.dumps(r.as_dict(), ensure_ascii=False, default=str, indent=2))
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
