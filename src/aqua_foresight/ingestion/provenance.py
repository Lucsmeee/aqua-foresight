"""Preservação de arquivos brutos e registro de proveniência (Espec. §10.1)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import httpx


def sha256_bytes(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def preservar_bruto(conteudo: bytes, raw_dir: Path, fonte_id: str, nome: str) -> Path:
    """Grava o bruto em raw_dir/<fonte>/<AAAAMMDDTHHMMSSZ>_<sha8>_<nome>. Nunca sobrescreve.

    Idempotente por conteúdo: se já existe arquivo com o mesmo SHA-256 na pasta da fonte,
    devolve o caminho existente (evita cópias idênticas a cada execução agendada).
    """
    sha = sha256_bytes(conteudo)
    destino_dir = raw_dir / fonte_id
    destino_dir.mkdir(parents=True, exist_ok=True)
    for existente in sorted(destino_dir.glob(f"*_{sha[:8]}_*")):
        if sha256_bytes(existente.read_bytes()) == sha:
            return existente
    carimbo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = destino_dir / f"{carimbo}_{sha[:8]}_{nome}"
    destino.write_bytes(conteudo)
    return destino


def brutos_da_fonte(raw_dir: Path, fonte_id: str) -> list[Path]:
    """Arquivos brutos preservados de uma fonte, do mais antigo ao mais novo (pelo carimbo no nome)."""
    pasta = raw_dir / fonte_id
    return sorted(p for p in pasta.glob("*_*_*") if p.is_file()) if pasta.exists() else []


def baixar(url: str, timeout: float) -> bytes:
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def ler_local(caminho: Path) -> bytes:
    return Path(caminho).read_bytes()


__all__ = ["sha256_bytes", "preservar_bruto", "brutos_da_fonte", "baixar", "ler_local"]
