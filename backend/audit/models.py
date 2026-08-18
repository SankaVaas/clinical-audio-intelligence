"""
Append-only, hash-chained audit log.

Every entry includes the hash of the previous entry, so any retroactive edit
or deletion breaks the chain and is detectable on verification. This is the
standard "blockchain-lite" pattern for tamper-evident logs -- no need for an
actual distributed ledger, just a hash chain plus a database that enforces
append-only via permissions (see infra/audit/postgres-audit-schema.sql).
"""
import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


@dataclass
class AuditEntry:
    tenant_id: str
    actor_id: str            # user or service principal
    action: str               # e.g. "session.finalize", "risk.flag_raised", "soap.exported"
    resource_type: str        # e.g. "audio_session", "patient_note"
    resource_id: str
    metadata: dict            # non-PHI structured detail only
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    prev_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self) -> str:
        payload = {k: v for k, v in asdict(self).items() if k != "entry_hash"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
