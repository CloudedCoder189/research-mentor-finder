"""Budgeted AI regeneration for the 51 repaired records in the private stage.

Default is a no-call preflight. --run uses the human-approved $0.05 job cap.
No key values, request bodies or account information are written to evidence.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import math
import os
import sqlite3
from types import SimpleNamespace

from scripts.real_acceptance_snapshot import ROOT, SOURCE

STAGE = ROOT / "test-runtime/ucla-expanded-repairs-20261005.db"
EVIDENCE = ROOT / "evidence/ucla-expanded-repair-2026-10-05"
CAP = Decimal("0.05")
TEXT_INPUT_RATE = Decimal("0.25") / 1_000_000
TEXT_OUTPUT_RATE = Decimal("2") / 1_000_000
EMBEDDING_RATE = Decimal("0.02") / 1_000_000


class BudgetError(RuntimeError):
    pass


class Budget:
    def __init__(self, path, cap=CAP):
        self.path = path
        self.cap = Decimal(str(cap))
        if not Decimal("0") < self.cap <= CAP:
            raise ValueError("Cap exceeds the approved job limit")
        self.entries = []
        self.blocked = False
        if path.exists():
            raise BudgetError("Existing ledger must be reviewed before resuming; refusing a fresh budget")
        self.write()

    @property
    def charged(self):
        return sum((Decimal(entry["charge_usd"]) for entry in self.entries), Decimal("0"))

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"approved_cap_usd": str(self.cap), "charged_or_reserved_usd": str(self.charged),
                                        "automatic_retries": 0, "entries": self.entries}, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def request(self, endpoint, kwargs):
        if self.blocked:
            raise BudgetError("An earlier response has unconfirmed usage; no additional calls allowed")
        kind = "text" if kwargs["model"] == "gpt-5-mini" else "embedding"
        if kind == "text":
            if not isinstance(kwargs["input"], str):
                raise ValueError("Only the reviewed text prompt form is supported")
            kwargs = kwargs | {"max_output_tokens": 2048, "reasoning": {"effort": "minimal"}, "store": False}
            input_bound = len(kwargs["input"].encode("utf-8")) + 1024
            reserve = input_bound * TEXT_INPUT_RATE + 2048 * TEXT_OUTPUT_RATE
        elif kwargs["model"] == "text-embedding-3-small":
            if not isinstance(kwargs["input"], list) or not all(isinstance(text, str) for text in kwargs["input"]):
                raise ValueError("Only the reviewed embedding input form is supported")
            input_bound = sum(len(text.encode("utf-8")) for text in kwargs["input"])
            reserve = input_bound * EMBEDDING_RATE
        else:
            raise ValueError("Model outside reviewed pricing scope")
        if self.charged + reserve > self.cap:
            raise BudgetError("Stopping before a request could exceed the approved cap")
        entry = {"kind": kind, "model": kwargs["model"], "input_token_bound": input_bound,
                 "max_output_tokens": 2048 if kind == "text" else 0,
                 "charge_usd": str(reserve), "status": "reserved_before_request"}
        self.entries.append(entry)
        self.write()
        try:
            response = endpoint(**kwargs)
            usage = response.usage
            input_tokens = int(usage.input_tokens if kind == "text" else usage.prompt_tokens)
            output_tokens = int(usage.output_tokens) if kind == "text" else 0
            if input_tokens < 0 or output_tokens < 0 or input_tokens > input_bound or output_tokens > entry["max_output_tokens"]:
                raise BudgetError("Usage fell outside the reserved bounds")
            charge = (input_tokens * TEXT_INPUT_RATE + output_tokens * TEXT_OUTPUT_RATE) if kind == "text" else input_tokens * EMBEDDING_RATE
            entry.update(input_tokens=input_tokens, output_tokens=output_tokens, charge_usd=str(charge), status="usage_confirmed")
            self.write()
            return response
        except Exception as exc:
            # No automatic retry: the full reservation remains charged when
            # usage could not be confirmed. The ledger must be reviewed first.
            self.blocked = True
            entry.update(status="error_usage_unconfirmed", error_type=type(exc).__name__)
            self.write()
            raise BudgetError("Provider call stopped; conservative reservation retained") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(STAGE.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        records = [dict(row) for row in connection.execute("SELECT * FROM professors WHERE embedding_json = '' ORDER BY id")]
    assert len(records) == 51
    allowed_ids = {record["id"] for record in records}
    if not args.run:
        print(json.dumps({"preflight_records": len(records), "approved_cap_usd": str(CAP), "paid_calls": 0}))
        return
    os.environ.update(PROFESSOR_DB_PATH=str(STAGE), OPENAI_TEXT_MODEL="gpt-5-mini", OPENAI_EMBEDDING_MODEL="text-embedding-3-small")
    from dotenv import dotenv_values
    key = dotenv_values(SOURCE.parents[1] / ".env").get("OPENAI_API_KEY", "")
    if not key:
        raise SystemExit("API key unavailable; no provider calls made")
    os.environ["OPENAI_API_KEY"] = key
    from openai import OpenAI
    from services import ai_enrichment
    from services.taxonomy import infer_taxonomy

    budget = Budget(EVIDENCE / "ai-regeneration-ledger.json")
    client = OpenAI(api_key=key, max_retries=0, timeout=45)
    wrapped = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: budget.request(client.responses.create, kwargs)),
        embeddings=SimpleNamespace(create=lambda **kwargs: budget.request(client.embeddings.create, kwargs)),
    )
    ai_enrichment._new_client = lambda: wrapped
    placeholders = ",".join("?" for _ in allowed_ids)
    with sqlite3.connect(STAGE) as connection:
        before_other = connection.execute(f"SELECT * FROM professors WHERE id NOT IN ({placeholders}) ORDER BY id", tuple(sorted(allowed_ids))).fetchall()
        backup = ROOT / "test-runtime/ucla-expanded-before-ai-20261005.db"
        if backup.exists():
            raise SystemExit("AI backup already exists; refusing an unreviewed rerun")
        with sqlite3.connect(backup) as saved:
            connection.backup(saved)
            assert saved.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def save_records(rows):
        rows = list(rows)
        if any(int(row["id"]) not in allowed_ids for row in rows):
            raise ValueError("Provider results attempted to leave the approved record scope")
        with sqlite3.connect(STAGE) as connection:
            for row in rows:
                taxonomy = infer_taxonomy(university=row["university"], department=row["department"],
                                          categories=row["categories"], ai_categories=row["ai_categories"])
                connection.execute("""UPDATE professors SET ai_categories=?, ai_summary=?, embedding_json=?,
                    embedding_model=?, embedding_source_hash=?, ai_enriched_at=?,
                    school_or_college=?, discipline=?, field=?, subfield=? WHERE id=?""",
                    (row["ai_categories"], row["ai_summary"], row["embedding_json"], row["embedding_model"],
                     row["embedding_source_hash"], row["ai_enriched_at"], *taxonomy, row["id"]))
        return len(rows)

    ai_enrichment.update_ai_enrichment = save_records
    try:
        result = ai_enrichment.enrich_records_with_openai(records, max_records=51,
            progress_callback=lambda message: print(message, flush=True))
        assert result["embedded"] == result["saved"] == 51
        with sqlite3.connect(STAGE) as connection:
            after_other = connection.execute(f"SELECT * FROM professors WHERE id NOT IN ({placeholders}) ORDER BY id", tuple(sorted(allowed_ids))).fetchall()
            assert before_other == after_other
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            connection.row_factory = sqlite3.Row
            enriched = [dict(row) for row in connection.execute(f"SELECT * FROM professors WHERE id IN ({placeholders}) ORDER BY id", tuple(sorted(allowed_ids)))]
            for row in enriched:
                vector = ai_enrichment.parse_embedding(row["embedding_json"])
                assert vector and len(vector) == 1536 and all(math.isfinite(value) for value in vector)
                assert row["embedding_source_hash"] == ai_enrichment.source_hash(row)
                assert row["ai_summary"] and row["ai_categories"]
        report = {"status": "completed", "records": sorted(allowed_ids), "result": result,
                  "charged_usd": str(budget.charged), "cap_usd": str(CAP), "other_professor_rows_unchanged": True,
                  "original_and_active_databases": "Not opened for writes", "fallback_summary_count": 51 - result["text_enriched"]}
        (EVIDENCE / "ai-regeneration-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"regenerated": 51, "ai_text_records": result["text_enriched"], "charged_usd": str(budget.charged)}))
    except Exception as exc:
        (EVIDENCE / "ai-regeneration-results.json").write_text(json.dumps({"status": "stopped", "error_type": type(exc).__name__,
            "charged_or_reserved_usd": str(budget.charged), "cap_usd": str(CAP)}, indent=2), encoding="utf-8")
        raise SystemExit("Regeneration stopped; inspect the redacted spending ledger and preserved checkpoints") from None
    finally:
        client.close()
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    main()
