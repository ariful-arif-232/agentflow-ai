"""Tamper-evident audit trail for simulated approvals (prototype).

Each record carries ``previous_hash`` and ``record_hash = SHA-256(previous_hash + canonical JSON of the
record's immutable fields)``, so changing, removing or reordering any stored record breaks verification.
Records also carry a deterministic ``approval_fingerprint``; submitting the same approval again returns
the original record instead of writing a duplicate (replay guard).

Storage is in memory by default (lost on restart). If ``AGENTFLOW_AUDIT_LOG_PATH`` is set, every record is
also appended to that JSONL file (flushed and fsynced) and the file is re-read and verified at start-up.
This is **tamper-evident, not tamper-proof**: anyone who can rewrite the whole file can recompute the chain,
and a container without a persistent volume loses the file on redeploy. Production needs an external,
governed, append-only audit store. Approvals here only ever record simulations; no money moves.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("agentflow.audit")

GENESIS_HASH = "0" * 64
HASH_FIELDS_EXCLUDED = ("record_hash",)
MAX_IN_MEMORY = 5_000
STORAGE_IN_MEMORY = "in-memory, process-local (resets when the API restarts)"
STORAGE_FILE = ("append-only JSONL file, process-local (survives restarts only on a persistent volume; "
                "not an external governed audit store)")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(payload: dict) -> str:
    """Deterministic identity of *what* is approved (not who or when)."""
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def record_hash(record: dict) -> str:
    body = {k: v for k, v in record.items() if k not in HASH_FIELDS_EXCLUDED}
    return hashlib.sha256((record["previous_hash"] + canonical(body)).encode()).hexdigest()


def verify_chain(records: list[dict], anchor: str = GENESIS_HASH) -> dict:
    """Verify records in append order. Returns {"verified", "records", "first_bad_sequence", "reason"}."""
    prev = anchor
    for i, r in enumerate(records):
        if r.get("previous_hash") != prev:
            return {"verified": False, "records": len(records), "first_bad_sequence": r.get("sequence", i),
                    "reason": "previous_hash does not match the preceding record"}
        if r.get("record_hash") != record_hash(r):
            return {"verified": False, "records": len(records), "first_bad_sequence": r.get("sequence", i),
                    "reason": "record_hash does not match the record contents"}
        prev = r["record_hash"]
    return {"verified": True, "records": len(records), "first_bad_sequence": None, "reason": None}


class AuditChain:
    """Hash-chained, append-only (by API) audit log shared by the intraday and Morning Plan simulations."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._records: list[dict] = []     # append order
        self._anchor = GENESIS_HASH        # previous_hash of the first record held in memory
        self._by_fp: dict[str, dict] = {}
        self.load_error: str | None = None
        if self.path is not None:
            self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self) -> None:
        if not self.path.exists():
            return
        records = []
        try:
            for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    records.append(json.loads(line))
        except (ValueError, OSError) as e:
            self.load_error = f"audit file unreadable at line {n}: {type(e).__name__}"
            log.error(self.load_error)
            return
        res = verify_chain(records)
        if not res["verified"]:
            self.load_error = f"audit file failed verification at sequence {res['first_bad_sequence']}: {res['reason']}"
            log.error(self.load_error)
        self._records = records[-MAX_IN_MEMORY:]
        if len(records) > MAX_IN_MEMORY:
            self._anchor = self._records[0]["previous_hash"]
        self._by_fp = {r["approval_fingerprint"]: r for r in self._records if "approval_fingerprint" in r}

    def _append_file(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(canonical(record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # ---------------------------------------------------------------- API
    @property
    def writable(self) -> bool:
        """Fail closed: no new approvals are recorded on top of a chain that failed verification."""
        return self.load_error is None and self.verify()["verified"]

    def find(self, fp: str) -> dict | None:
        with self._lock:
            return self._by_fp.get(fp)

    def append(self, kind: str, fields: dict, fp: str) -> tuple[dict, bool]:
        """Append a record, or return the existing one for the same fingerprint. Returns (record, created)."""
        with self._lock:
            if fp in self._by_fp:
                return self._by_fp[fp], False
            prev = self._records[-1]["record_hash"] if self._records else self._anchor
            last_seq = self._records[-1]["sequence"] if self._records else 0
            rec = {**fields, "kind": kind, "sequence": last_seq + 1, "approval_fingerprint": fp, "previous_hash": prev}
            rec["record_hash"] = record_hash(rec)
            if self.path is not None:
                self._append_file(rec)  # write first: a failed write raises and nothing is recorded in memory
            self._records.append(rec)
            self._by_fp[fp] = rec
            if len(self._records) > MAX_IN_MEMORY:
                dropped = self._records.pop(0)
                self._anchor = dropped["record_hash"]
                self._by_fp.pop(dropped.get("approval_fingerprint"), None)
            return rec, True

    def entries(self, kind: str | None = None, limit: int = 200) -> list[dict]:
        """Newest first (the order the dashboard shows)."""
        with self._lock:
            rows = [r for r in reversed(self._records) if kind is None or r["kind"] == kind]
        return [dict(r) for r in rows[:limit]]

    def verify(self) -> dict:
        with self._lock:
            res = verify_chain(list(self._records), self._anchor)
        if self.load_error:
            res = {**res, "verified": False, "reason": self.load_error}
        return res

    def status(self) -> dict:
        v = self.verify()
        with self._lock:
            head = self._records[-1]["record_hash"] if self._records else self._anchor
        return {"tamper_evident": True, "algorithm": "SHA-256 hash chain", "verified": v["verified"],
                "records": v["records"], "head_hash": head, "reason": v["reason"],
                "storage": STORAGE_FILE if self.path is not None else STORAGE_IN_MEMORY,
                "note": ("Prototype safeguard: tamper-evident, not tamper-proof or production-grade immutable "
                         "storage. Records describe simulations only; no money moves.")}


_chain: AuditChain | None = None
_chain_lock = threading.Lock()


def get_audit_chain() -> AuditChain:
    global _chain
    with _chain_lock:
        if _chain is None:
            _chain = AuditChain(os.getenv("AGENTFLOW_AUDIT_LOG_PATH", "").strip() or None)
        return _chain
