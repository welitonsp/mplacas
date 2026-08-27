"""Invariantes de custo zero do Mplacas.

O projeto é de **uso pessoal, sem orçamento**, e o dono declarou não ter
interesse em pagar por infraestrutura (ver `docs/POLITICA_CUSTO_ZERO.md` e
`docs/ESTUDO_CUSTO_NEON_2026-08-27.md`). Isso não é preferência de momento: é
restrição de projeto, e decisões técnicas precisam respeitá-la.

O histórico justifica travar por teste em vez de confiar em disciplina. Duas
cobranças/interrupções em um mês, ambas pelo mesmo mecanismo — algo passou a
rodar com frequência alta o bastante para nunca deixar o recurso hibernar:

- 2026-08-21: dois jobs em `*/5 * * * *` mantiveram o Neon acordado ~730 h/mês,
  182 CU-horas contra uma franquia de 100. Sistema parado por 4 dias.
- 2026-08-26: cobrança do Google Cloud sem orçamento, que levou à saída do
  provedor (ADR-076).

Cada asserção aqui corresponde a um jeito conhecido de reintroduzir custo.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# Intervalo mínimo entre execuções agendadas, em horas.
#
# O limite existe porque o custo não vem do número de consultas: vem do tempo
# ACORDADO. O Neon hiberna 5 min após a última consulta e o Render após 15 min
# sem tráfego, então o que importa é quantas vezes por dia algo os desperta.
# Agenda de 6 em 6 horas custa ~30 h/mês de instância; de 5 em 5 minutos mantém
# tudo acordado o mês inteiro.
INTERVALO_MINIMO_HORAS = 6


def _agendas(texto: str) -> list[str]:
    documento = yaml.safe_load(texto)
    # `on:` é interpretado como booleano True pelo YAML 1.1.
    gatilhos = documento.get(True) or documento.get("on") or {}
    if not isinstance(gatilhos, dict):
        return []
    return [entrada["cron"] for entrada in gatilhos.get("schedule", []) or []]


def _intervalo_horas(cron: str) -> float:
    """Menor intervalo, em horas, entre duas execuções desta expressão cron."""
    minuto, hora = cron.split()[0], cron.split()[1]

    if minuto == "*" or minuto.startswith("*/"):
        # Roda várias vezes por hora — foi exatamente este o padrão do incidente.
        passo = 1 if minuto == "*" else int(minuto.split("/")[1])
        return passo / 60

    if hora == "*":
        return 1.0
    if hora.startswith("*/"):
        return float(hora.split("/")[1])
    return 24.0


@pytest.mark.parametrize("caminho", WORKFLOWS, ids=lambda p: p.name)
def test_nenhuma_agenda_roda_com_frequencia_que_impede_hibernacao(caminho: Path) -> None:
    for cron in _agendas(caminho.read_text(encoding="utf-8")):
        intervalo = _intervalo_horas(cron)
        assert intervalo >= INTERVALO_MINIMO_HORAS, (
            f"{caminho.name}: cron {cron!r} roda a cada {intervalo:.2f} h, abaixo do mínimo de "
            f"{INTERVALO_MINIMO_HORAS} h. Agenda frequente impede a hibernação do Neon e do "
            f"Render e é o mecanismo exato do incidente de 2026-08-21. "
            f"Ver docs/POLITICA_CUSTO_ZERO.md antes de alterar este limite."
        )


def test_health_nao_consulta_o_banco() -> None:
    """`/health` é o alvo do vigia a cada 6 h — se tocar o banco, vira custo recorrente.

    Enquanto ele devolve estado estático, o ping do watchdog acorda apenas o
    serviço no Render e consome ZERO compute do Neon. Adicionar uma consulta aqui
    transformaria o próprio monitoramento numa fonte de consumo — que é o
    contrassenso que este teste evita. Verificação de dependência é papel de
    `/ready`, que ninguém agenda.
    """
    fonte = (ROOT / "src" / "mplacas" / "main.py").read_text(encoding="utf-8")
    inicio = fonte.index('@app.get("/health"')
    corpo = fonte[inicio : fonte.index("@app.get", inicio + 10)]

    for termo in ("session", "execute", "SessionFactory", "await "):
        assert termo not in corpo, (
            f"/health passou a usar {termo!r}. O vigia bate nesse endpoint a cada 6 h; "
            "consulta ao banco aqui vira consumo recorrente de CU-horas."
        )


def test_render_permanece_no_plano_gratuito() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    servicos = blueprint["services"]

    assert [s["plan"] for s in servicos] == ["free"] * len(servicos)


def test_nenhum_keepalive_contra_a_hibernacao() -> None:
    """Manter o serviço acordado de propósito estoura a franquia do Render.

    São 750 h de instância por mês contra as ~730 h que o mês tem — praticamente
    sem folga. Um keep-alive periódico consome tudo e ainda mantém o Neon
    acordado, reproduzindo o incidente de 2026-08-21 por outro caminho. O cold
    start de 30 a 60 s é o preço aceito do custo zero, não um defeito a corrigir.
    """
    for caminho in WORKFLOWS:
        texto = caminho.read_text(encoding="utf-8").lower()
        for termo in ("keep-alive", "keepalive", "warm-up", "warmup", "keep_warm"):
            assert termo not in texto, f"{caminho.name} contém {termo!r}"
