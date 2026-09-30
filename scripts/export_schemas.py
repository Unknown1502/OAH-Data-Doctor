"""Export JSON Schemas for the public data contract (docs/05_DATA_AND_SCHEMAS.md) from the Pydantic models."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from datadoctor.audit.service import AuditResult  # noqa: E402
from datadoctor.domain.models import (  # noqa: E402
    ClaimResult,
    Comparison,
    Finding,
    Provenance,
    StructuredClaim,
)

MODELS = {"finding": Finding, "comparison": Comparison, "claim": StructuredClaim, "claim_result": ClaimResult,
          "provenance": Provenance, "audit_result": AuditResult}


def main() -> None:
    out = ROOT / "schemas"
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"https://github.com/oah-data-doctor/oah-data-doctor/schemas/{name}.schema.json"
        (out / f"{name}.schema.json").write_text(json.dumps(schema, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    from datadoctor.cli import utf8_output

    utf8_output()  # readable output when redirected on Windows
    main()
