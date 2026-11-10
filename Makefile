.PHONY: install test api init-db ingest-enos up down

install:
	pip install -e ".[dev]"

test:
	pytest

init-db:
	aqua init-db

# Download direto do CPC (exige acesso de rede ao cpc.ncep.noaa.gov)
ingest-enos:
	aqua ingest-enos --indicador RONI

api:
	uvicorn aqua_foresight.api.main:app_factory --factory --reload

up:
	docker compose up -d --build

down:
	docker compose down
