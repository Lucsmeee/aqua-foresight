"""Carga histórica diária do SAR/ANA (DF) para data/series/sar_df_diario.csv.

Retomável: só consulta datas que ainda não estão no CSV. Grava a cada 200 dias para não
perder progresso. Educado com o servidor: uma requisição por vez, com pausa.

    python scripts/carga_historica_sar.py --inicio 1990-01-01 --fim 2026-11-10 [--max-dias 20000]
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aqua_foresight.ingestion import ana_sar  # noqa: E402

SERIE = Path("data/series/sar_df_diario.csv")
CONSULTADOS = Path("data/series/sar_df_dias_consultados.txt")  # dias já pedidos (inclusive sem medição própria)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicio", type=date.fromisoformat, default=date(1990, 1, 1))
    ap.add_argument("--fim", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    ap.add_argument("--max-dias", type=int, default=20000)
    ap.add_argument("--pausa", type=float, default=0.15)
    ap.add_argument("--paralelo", type=int, default=3, help="requisições simultâneas (seja educado: ≤ 3)")
    a = ap.parse_args()

    serie = ana_sar.ler_serie(SERIE)
    cliente = ana_sar.ClienteSAR(pausa=a.pausa)

    # 1) últimos ~5 anos em duas chamadas
    for res in ana_sar.CODIGOS:
        try:
            n = ana_sar.mesclar(serie, cliente.grafico(res))
            print(f"retornaGrafico {res}: {n} registros novos/alterados")
        except Exception as exc:  # noqa: BLE001
            print(f"retornaGrafico {res}: FALHA {type(exc).__name__}: {exc}")
    ana_sar.gravar_serie(SERIE, serie)

    # 2) dias restantes, um a um
    consultados = ana_sar.ler_consultados(CONSULTADOS)
    faltam = ana_sar.dias_faltantes(serie, a.inicio, a.fim, consultados)[: a.max_dias]
    print(f"{len(faltam)} dia(s) a consultar em retornaMedicoes")
    falhas, sem_dado, t0, feitos = 0, 0, time.time(), 0
    pendentes = list(faltam)
    while pendentes:
        lote, pendentes = pendentes[:200], pendentes[200:]
        with ThreadPoolExecutor(max_workers=min(a.paralelo, 3)) as ex:
            futuros = {ex.submit(cliente.medicoes, d): d for d in lote}
            for fu in as_completed(futuros):
                d = futuros[fu]
                try:
                    regs = fu.result()
                    if not regs:
                        sem_dado += 1
                    ana_sar.mesclar(serie, regs)
                    consultados.add(d.isoformat())
                    # dias entre o pedido e a medição devolvida não têm medição própria
                    for r in regs:
                        dev = date.fromisoformat(r.data)
                        k = d
                        while k < dev:
                            consultados.add(k.isoformat())
                            k += timedelta(days=1)
                except Exception as exc:  # noqa: BLE001
                    falhas += 1
                    print(f"{d}: FALHA {type(exc).__name__}: {str(exc)[:160]}")
        feitos += len(lote)
        pendentes = [d for d in pendentes if d.isoformat() not in consultados]
        ana_sar.gravar_serie(SERIE, serie)
        ana_sar.gravar_consultados(CONSULTADOS, consultados)
        print(f"{feitos} consultados · {len(pendentes)} pendentes · {time.time() - t0:.0f}s · sem dado {sem_dado} · falhas {falhas}", flush=True)
        if falhas > 50:
            print("muitas falhas; interrompendo para não sobrecarregar o servidor")
            break
    ana_sar.gravar_serie(SERIE, serie)
    print(f"concluído: {len(serie)} linhas no CSV · sem dado {sem_dado} · falhas {falhas}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
