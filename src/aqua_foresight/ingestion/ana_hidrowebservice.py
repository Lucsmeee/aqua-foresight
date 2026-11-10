"""Cliente da API HidroWebService da ANA (séries telemétricas).

Base documentada no "Tutorial de serviço para consumo de dados – API HidroWebService"
(ANA, versão 14.03.2025) e no Swagger https://www.ana.gov.br/hidrowebservice/swagger-ui/index.html:

- Acesso: e-mail a hidro@ana.gov.br, assunto "<CPF ou CNPJ> - Solicitação de acesso à API
  HidroWebService para consumo de dados"; o CPF/CNPJ vira o identificador e a senha chega por e-mail.
- Autenticação: GET /EstacoesTelemetricas/OAUth/v1 com cabeçalhos `Identificador` e `Senha`;
  resposta com `tokenautenticacao` (validade informada de 60 min). Autenticar com muita
  frequência pode bloquear o IP — por isso um único token por execução.
- Série: GET /EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v1 com
  `CodigoDaEstacao`, `TipoFiltroData=DATA_LEITURA`, `RangeIntervaloDeBusca=DIAS_30`
  e `Authorization: Bearer <token>`. Campos: Data_Hora_Medicao, Cota_Adotada, Vazao_Adotada,
  Chuva_Adotada e respectivos *_Status (0 = ok, 1 = suspeito, 2 = ruim).

LIMITAÇÕES (não verificadas por falta de credencial):
- Os parâmetros acima vêm do exemplo Java do tutorial; o Swagger pode exigir outros (o
  tutorial cita "Data de Busca" na rota detalhada). Erros HTTP são registrados com a mensagem.
- Os códigos das estações das barragens (60435500 Descoberto, 60477100 Santa Maria) vêm de
  Nota Técnica da ANA (Progestão, meta I.4) e precisam ser confirmados no inventário.
- A telemetria traz COTA (m), não volume útil (%). A conversão exige a curva cota-volume
  oficial do reservatório, que não está disponível no projeto.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

BASE = "https://www.ana.gov.br/hidrowebservice"
ROTA_TOKEN = "/EstacoesTelemetricas/OAUth/v1"
ROTA_SERIE = "/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaAdotada/v1"

ESTACOES_PILOTO = {
    # código: (reservatório, situação da verificação)
    "60435500": ("descoberto", "a_confirmar_no_inventario"),
    "60477100": ("santa_maria", "a_confirmar_no_inventario"),
}


class ErroANA(RuntimeError):
    pass


@dataclass
class Credenciais:
    identificador: str
    senha: str

    @classmethod
    def do_ambiente(cls) -> "Credenciais | None":
        ident, senha = os.environ.get("ANA_IDENTIFICADOR"), os.environ.get("ANA_SENHA")
        return cls(ident, senha) if ident and senha else None


class ClienteHidroWeb:
    def __init__(self, cred: Credenciais, timeout: float = 60.0, client: httpx.Client | None = None):
        self.cred = cred
        self.http = client or httpx.Client(base_url=BASE, timeout=timeout, follow_redirects=True)
        self._token: str | None = None

    def token(self) -> str:
        if self._token:
            return self._token
        r = self.http.get(ROTA_TOKEN, headers={"Identificador": self.cred.identificador, "Senha": self.cred.senha})
        if r.status_code != 200:
            raise ErroANA(f"autenticação falhou: HTTP {r.status_code} {r.text[:200]}")
        corpo = r.json()
        tok = (corpo.get("items") or {}).get("tokenautenticacao") if isinstance(corpo.get("items"), dict) else None
        tok = tok or corpo.get("tokenautenticacao")
        if not tok:
            raise ErroANA(f"resposta sem tokenautenticacao: {str(corpo)[:200]}")
        self._token = tok
        return tok

    def serie_adotada(self, codigo: str, range_busca: str = "DIAS_30") -> list[dict]:
        r = self.http.get(
            ROTA_SERIE,
            params={"CodigoDaEstacao": codigo, "TipoFiltroData": "DATA_LEITURA", "RangeIntervaloDeBusca": range_busca},
            headers={"Authorization": f"Bearer {self.token()}"},
        )
        if r.status_code != 200:
            raise ErroANA(f"série {codigo}: HTTP {r.status_code} {r.text[:300]}")
        corpo = r.json()
        itens = corpo.get("items")
        if not isinstance(itens, list):
            raise ErroANA(f"série {codigo}: resposta sem lista 'items' ({str(corpo)[:200]})")
        return itens


def cotas_validas(itens: list[dict]) -> list[dict]:
    """Extrai cota adotada com status 0 (ok). Valores suspeitos/ruins ficam fora, contados à parte."""
    out = []
    for it in itens:
        if str(it.get("Cota_Adotada_Status", "")) not in ("0", "0.0"):
            continue
        try:
            cota = float(str(it.get("Cota_Adotada")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        # Unidade não confirmada na documentação lida: registrar como veio, sem converter.
        out.append({"data_hora": it.get("Data_Hora_Medicao"), "cota": cota, "unidade": "a_confirmar"})
    return out
