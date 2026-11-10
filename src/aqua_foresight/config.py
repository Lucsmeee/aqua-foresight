"""Configuração via variáveis de ambiente (prefixo AQUA_)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AQUA_", env_file=".env", extra="ignore")

    # SQLite por padrão para desenvolvimento/testes; PostgreSQL/PostGIS via docker-compose.
    database_url: str = "sqlite:///./data/aqua_foresight.db"

    # Onde os arquivos brutos são preservados (checksum + metadados), Espec. v2.0 §10.1.
    raw_dir: Path = Path("./data/raw")

    # Timeout de rede para adaptadores (segundos).
    http_timeout: float = 30.0

    # Parâmetro de SISTEMA (não é norma): idade máxima, em dias, de uma observação de
    # volume útil para que o enquadramento seja exibido sem ressalva de defasagem.
    # Valor provisório — deve ser pactuado na decisão D-04 da Especificação.
    max_defasagem_observacao_dias: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
