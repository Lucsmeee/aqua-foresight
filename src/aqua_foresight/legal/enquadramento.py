"""Motor de enquadramento hidrológico — versão mínima, determinística e auditável.

Regras de segurança implementadas (Espec. v2.0, §3.1, §7.4, §8.1, RF-07, RNF-07):
1. O limiar depende do reservatório E do mês — não há gatilho uniforme de 30%.
2. Valor PROJETADO gera no máximo "alerta antecipatório"; nunca estado observado.
3. Valor OBSERVADO gera "encaminhamento para análise"; o sistema não declara estado
   oficial, não notifica e não restringe usos. `acoes_automaticas` é sempre vazio.
4. Sem limiar cadastrado, valor fora de [0, 100] ou observação defasada: a conclusão
   categórica é bloqueada/ressalvada e a revisão humana é exigida.
5. Fora de escopo nesta versão: regras de transição/saída de estado (permanência
   mínima prevista na norma) — exigem histórico de observações e leitura jurídica
   do texto integral.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from aqua_foresight.db.models import LimiarEstadoHidrologico, NormaJuridica, RegistroAuditoria
from aqua_foresight.legal import adasa_56_2025 as adasa

Natureza = Literal["observado", "projetado"]

AVISO_PADRAO = (
    "Resultado indicativo gerado por sistema de apoio à decisão. Não constitui ato administrativo, "
    "declaração oficial de estado hidrológico, notificação ou restrição de uso. Exige verificação "
    "da fonte do dado, da vigência da norma e da competência da autoridade, e revisão humana."
)


@dataclass
class ResultadoEnquadramento:
    reservatorio_id: str
    mes_referencia: int
    valor_pct: float
    natureza: Natureza
    status: str  # enquadrado_indicativo | bloqueado
    estado_indicativo: str | None  # verde | amarelo | vermelho | None
    tipo_saida: str  # alerta_antecipatorio | encaminhamento_para_analise | revisao_humana_obrigatoria
    limiares: dict[str, float] = field(default_factory=dict)
    fundamentacao: dict = field(default_factory=dict)
    ressalvas: list[str] = field(default_factory=list)
    requer_revisao_humana: bool = True
    acoes_automaticas: list[str] = field(default_factory=list)  # deve permanecer vazio
    aviso: str = AVISO_PADRAO

    def as_dict(self) -> dict:
        return asdict(self)


def enquadrar(
    session: Session,
    reservatorio_id: str,
    data_referencia: date,
    valor_pct: float,
    natureza: Natureza,
    data_dado: date | None = None,
    max_defasagem_dias: int = 7,
    norma_id: str = adasa.NORMA_ID,
    ator: str = "sistema",
) -> ResultadoEnquadramento:
    mes = data_referencia.month
    ressalvas: list[str] = []

    norma = session.get(NormaJuridica, norma_id)
    limiares = {
        l.estado: l.limite_pct
        for l in session.scalars(
            select(LimiarEstadoHidrologico).where(
                LimiarEstadoHidrologico.norma_id == norma_id,
                LimiarEstadoHidrologico.reservatorio_id == reservatorio_id,
                LimiarEstadoHidrologico.mes == mes,
            )
        )
    }

    def bloquear(motivo: str) -> ResultadoEnquadramento:
        res = ResultadoEnquadramento(
            reservatorio_id=reservatorio_id,
            mes_referencia=mes,
            valor_pct=valor_pct,
            natureza=natureza,
            status="bloqueado",
            estado_indicativo=None,
            tipo_saida="revisao_humana_obrigatoria",
            limiares=limiares,
            fundamentacao=_fundamentacao(norma),
            ressalvas=ressalvas + [motivo],
        )
        _auditar(session, ator, res, data_referencia, data_dado)
        return res

    if norma is None:
        return bloquear(f"Norma {norma_id!r} não cadastrada na base normativa.")
    if set(limiares) != {"amarelo", "vermelho"}:
        return bloquear(
            f"Limiares de {reservatorio_id!r} para o mês {mes} ausentes ou incompletos: conclusão categórica bloqueada."
        )
    if not (0.0 <= valor_pct <= 100.0):
        return bloquear(f"Volume útil {valor_pct}% fora do intervalo físico [0, 100]: verificar o dado de entrada.")

    if norma.vigencia_status != "conferida":
        ressalvas.append("Vigência da norma ainda não conferida por revisão jurídica.")

    if natureza == "observado":
        if data_dado is None:
            ressalvas.append("Data da observação não informada: frescor do dado não verificável.")
        else:
            defasagem = (data_referencia - data_dado).days
            if defasagem < 0:
                return bloquear("Data da observação posterior à data de referência.")
            if defasagem > max_defasagem_dias:
                ressalvas.append(
                    f"Observação defasada em {defasagem} dias (> {max_defasagem_dias}, parâmetro de sistema): "
                    "não usar como retrato da situação atual."
                )
            if data_dado.month != mes:
                ressalvas.append("Observação de mês diferente do mês de referência: limiar pode não ser aplicável.")

    if valor_pct < limiares["vermelho"]:
        estado = "vermelho"
    elif valor_pct < limiares["amarelo"]:
        estado = "amarelo"
    else:
        estado = "verde"

    if natureza == "projetado":
        tipo = "alerta_antecipatorio"
        ressalvas.append(
            "Valor projetado: indica possível trajetória, não estado hidrológico observado. "
            "A previsão ainda não possui modelo validado nesta versão do sistema."
        )
    else:
        tipo = "encaminhamento_para_analise"

    fund = _fundamentacao(norma)
    chave = (
        "condicao_de_uso_associada_ao_estado"
        if natureza == "observado"
        else "condicao_de_uso_que_se_aplicaria_se_confirmada_em_observacao_oficial"
    )
    fund[chave] = adasa.CONDICOES_DE_USO[estado]

    res = ResultadoEnquadramento(
        reservatorio_id=reservatorio_id,
        mes_referencia=mes,
        valor_pct=valor_pct,
        natureza=natureza,
        status="enquadrado_indicativo",
        estado_indicativo=estado,
        tipo_saida=tipo,
        limiares=limiares,
        fundamentacao=fund,
        ressalvas=ressalvas,
    )
    _auditar(session, ator, res, data_referencia, data_dado)
    return res


def _fundamentacao(norma: NormaJuridica | None) -> dict:
    if norma is None:
        return {}
    return {
        "norma_id": norma.id,
        "norma": norma.titulo,
        "dispositivos": [adasa.DISPOSITIVOS["estados"], adasa.DISPOSITIVOS["condicoes_de_uso"]],
        "autoridade_competente": norma.orgao_emissor,
        "publicacao": norma.publicacao,
        "fontes": norma.fontes,
        "status_verificacao": norma.status_verificacao,
        "vigencia_status": norma.vigencia_status,
    }


def _auditar(session: Session, ator: str, res: ResultadoEnquadramento, data_ref: date, data_dado: date | None) -> None:
    session.add(
        RegistroAuditoria(
            ator=ator,
            acao="enquadramento_avaliado",
            entidade="reservatorio",
            entidade_id=res.reservatorio_id,
            detalhes={
                "data_referencia": data_ref.isoformat(),
                "data_dado": data_dado.isoformat() if data_dado else None,
                "valor_pct": res.valor_pct,
                "natureza": res.natureza,
                "status": res.status,
                "estado_indicativo": res.estado_indicativo,
                "tipo_saida": res.tipo_saida,
                "limiares": res.limiares,
                "ressalvas": res.ressalvas,
            },
        )
    )
