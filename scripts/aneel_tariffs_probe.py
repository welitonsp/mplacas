"""Sonda da base aberta de tarifas da ANEEL (ADR-088, preparação).

Baixa o CSV público "tarifas-homologadas-distribuidoras-energia-eletrica" e
imprime um RESUMO como anotações do GitHub Actions (``::notice``): formato do
arquivo, siglas de distribuidora e as linhas B1 da Equatorial Goiás. Não toca
banco nem usa segredo — só dado público. Serve para desenhar o importador com
o formato real, em vez de presumir.
"""

from __future__ import annotations

import collections
import csv
import io
import re
import sys

import httpx

URL = (
    "https://dadosabertos.aneel.gov.br/dataset/5a583f3e-1646-4f67-bf0f-69db4203e89e/"
    "resource/fcf2906c-7c32-4b9b-a637-054e7a5234f4/download/"
    "tarifas-homologadas-distribuidoras-energia-eletrica.csv"
)
AGENT_HINT = re.compile(r"^EQUATORIAL GO$")


def notice(title: str, lines: list[str]) -> None:
    body = "%0A".join(line.replace("%", "%25").replace("\n", " ") for line in lines)
    print(f"::notice title={title}::{body}")


def main() -> int:
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        response = client.get(URL)
        response.raise_for_status()
    raw = response.content
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    first = text.splitlines()[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    notice(
        "formato",
        [
            f"bytes={len(raw)} encoding={encoding} delimitador={delimiter!r} linhas={len(rows)}",
            f"colunas={reader.fieldnames}",
            f"exemplo={rows[0] if rows else None}",
        ],
    )

    agents = collections.Counter(r.get("SigAgente", "") for r in rows)
    notice("siglas-goias", [f"{a}: {n}" for a, n in agents.items() if AGENT_HINT.search(a)][:40])

    combos: collections.Counter[tuple[str, ...]] = collections.Counter()
    for r in rows:
        recent = r.get("DatInicioVigencia", "") >= "2025"
        if recent and r.get("DscSubGrupo", "").upper().startswith("B"):
            combos[
                (
                    r.get("DscSubGrupo", ""),
                    r.get("DscModalidadeTarifaria", ""),
                    r.get("DscClasse", ""),
                    r.get("DscSubClasse", ""),
                    r.get("DscDetalhe", ""),
                    r.get("NomPostoTarifario", ""),
                    r.get("DscBaseTarifaria", ""),
                )
            ] += 1
    notice("combinacoes-grupo-b-2025", [f"{n} x {c}" for c, n in combos.most_common(60)])

    aplicacao = [r for r in rows if r.get("DscBaseTarifaria", "") == "Tarifa de Aplicação"]
    vig: dict[tuple[str, ...], tuple[str, str]] = {}
    for r in aplicacao:
        if (
            AGENT_HINT.search(r.get("SigAgente", ""))
            and r.get("DscSubGrupo", "") == "B1"
            and r.get("DscModalidadeTarifaria", "") == "Convencional"
            and r.get("DscSubClasse", "") == "Residencial"
            and r.get("DatInicioVigencia", "") >= "2022"
        ):
            reh = re.search(r"N[ºo°]\s*([\d.]+)", r.get("DscREH", ""))
            key = (
                r.get("DatInicioVigencia", ""),
                r.get("DatFimVigencia", ""),
                reh.group(1) if reh else "?",
                r.get("DscDetalhe", ""),
            )
            vig[key] = (r.get("VlrTUSD", ""), r.get("VlrTE", ""))
    notice(
        "equatorial-b1-residencial-convencional",
        [
            f"{k[0]}..{k[1]} REH {k[2]} {k[3]}: TUSD {v[0]} TE {v[1]}"
            for k, v in sorted(vig.items())
        ],
    )
    classes: collections.Counter[tuple[str, ...]] = collections.Counter()
    for r in aplicacao:
        if (
            r.get("DscSubGrupo", "") in {"B1", "B2", "B3", "B4a", "B4b", "B4A", "B4B"}
            and r.get("DscModalidadeTarifaria", "") == "Convencional"
            and r.get("DscDetalhe", "") == "Não se aplica"
            and r.get("DatInicioVigencia", "") >= "2025"
        ):
            classes[
                (r.get("DscSubGrupo", ""), r.get("DscClasse", ""), r.get("DscSubClasse", ""))
            ] += 1
    notice("classes-grupo-b", [f"{n} x {c}" for c, n in classes.most_common(70)])
    detalhes = collections.Counter(
        r.get("DscDetalhe", "")
        for r in aplicacao
        if r.get("DscSubGrupo", "").startswith("B") and r.get("DatInicioVigencia", "") >= "2025"
    )
    notice("detalhes-grupo-b", [f"{d}: {n}" for d, n in detalhes.most_common(30)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
