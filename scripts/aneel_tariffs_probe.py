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
AGENT_HINT = re.compile(r"equatorial|celg|goi", re.IGNORECASE)


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
        if r.get("DscSubgrupo", "").upper().startswith("B"):
            combos[
                (
                    r.get("DscSubgrupo", ""),
                    r.get("DscModalidadeTarifaria", ""),
                    r.get("DscClasse", ""),
                    r.get("DscSubClasse", ""),
                    r.get("DscDetalhe", ""),
                    r.get("NomPostoTarifario", ""),
                    r.get("DscBaseTarifa", ""),
                )
            ] += 1
    notice("combinacoes-grupo-b", [f"{n} x {c}" for c, n in combos.most_common(45)])

    target = [
        r
        for r in rows
        if AGENT_HINT.search(r.get("SigAgente", ""))
        and r.get("DscSubgrupo", "") == "B1"
        and r.get("DatInicioVigencia", "") >= "2023"
    ]
    target.sort(key=lambda r: (r.get("DatInicioVigencia", ""), r.get("DscSubClasse", "")))
    notice(
        "equatorial-b1-desde-2023",
        [
            " | ".join(
                r.get(k, "")
                for k in (
                    "SigAgente",
                    "DscResolucaoHomologatoria",
                    "DatInicioVigencia",
                    "DatFimVigencia",
                    "DscBaseTarifa",
                    "DscModalidadeTarifaria",
                    "DscClasse",
                    "DscSubClasse",
                    "DscDetalhe",
                    "NomPostoTarifario",
                    "DscUnidade",
                    "SigAgenteAcessante",
                    "VlrTusd",
                    "VlrTe",
                )
            )
            for r in target[:60]
        ],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
