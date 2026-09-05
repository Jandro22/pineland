"""Acquire an aggregated, reproducible CNMH/OMC event panel for Colombia.

The query deliberately retains municipality-year event and victim totals rather
than downloading an unbounded feature layer. The query itself is part of the
provenance record; this is a violence/civilian-harm source, not a territorial
control proxy.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / "studies" / "colombia_1984_2016"
OUT = STUDY / "data" / "processed"
ENDPOINT = "https://serviciosgiscnmh.centrodememoriahistorica.gov.co/agccnmh/rest/services/OMC/Hechos_violencia/MapServer/0/query"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    statistics = [
        {"statisticType": "count", "onStatisticField": "IdCaso", "outStatisticFieldName": "event_count"},
        {"statisticType": "sum", "onStatisticField": "Total_victimas_Caso", "outStatisticFieldName": "victim_count"},
        {"statisticType": "sum", "onStatisticField": "Total_victimas_civiles", "outStatisticFieldName": "civilian_victim_count"},
    ]
    query = {
        "where": "Fecha_Hecho >= DATE '1984-01-01' AND Fecha_Hecho <= DATE '2016-12-31'",
        "outFields": "Geo_municipio,Nombre_Municipio,Nombre_Departamento,Anio_hecho",
        "outStatistics": json.dumps(statistics, separators=(",", ":")),
        "groupByFieldsForStatistics": "Geo_municipio,Nombre_Municipio,Nombre_Departamento,Anio_hecho",
        "orderByFields": "Anio_hecho,Geo_municipio",
        "returnGeometry": "false",
        "f": "json",
    }
    url = ENDPOINT + "?" + urlencode(query)
    with urlopen(url, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "error" in payload:
        raise RuntimeError(payload["error"])
    features = payload.get("features", [])
    if not features:
        raise RuntimeError("OMC aggregate query returned no features")
    rows = [feature["attributes"] for feature in features]
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / "cnmh_omc_municipality_year_1984_2016.json"
    output.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "case_id": "colombia_1984_2016",
        "source": "Centro Nacional de Memoria Histórica Observatorio de Memoria y Conflicto",
        "endpoint": ENDPOINT,
        "query": query,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "output": output.relative_to(STUDY).as_posix(),
        "sha256": sha256(output),
        "interpretation": "violence and civilian-harm aggregate; not a control proxy",
    }
    (OUT / "cnmh_omc_municipality_year_1984_2016_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
