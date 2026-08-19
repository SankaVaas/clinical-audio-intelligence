import asyncio
import os
import logging
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Response, status
)
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "info").upper())
logger = logging.getLogger(__name__)

from backend.audio.manager import SessionManager
from backend.audio.transcriber import WhisperTranscriber
from backend.nlp.extractor import extract_clinical_entities
from backend.soap.generator import generate_soap_note
from backend.risk.engine import RiskEngine

from backend.auth.dependencies import get_current_principal, require_role, decode_token, Principal
from backend.tenancy.middleware import require_tenant_match
from backend.tenancy.db import acquire_tenant_conn
from backend.audit.models import AuditEntry
from backend.cost.tracker import BudgetExceeded
from backend.observability.metrics import metrics_response
from backend.observability.tracing import configure_tracing
import backend.db as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    # Loaded once per pod, shared read-only across every concurrent
    # session -- see backend/audio/session.py for why this isn't owned
    # per-session. This is also why startupProbe in infra/k8s/base has a
    # generous failureThreshold: this load is the dominant cold-start cost.
    app.state.transcriber = WhisperTranscriber(model_size=os.getenv("WHISPER_MODEL", "base"))
    app.state.sessions = SessionManager(app.state.transcriber)
    yield
    await db.close_db()


app = FastAPI(title="Clinical Audio Intelligence", lifespan=lifespan)
configure_tracing(app)

# CORS is scoped to real origins in every environment. "*" is only used
# as a local-dev fallback when ALLOWED_ORIGINS isn't set.
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: tenant context is set by the get_current_principal / decode_token
# dependency itself (backend/auth/dependencies.py), not by HTTP middleware
# -- see the docstring in backend/tenancy/middleware.py for why.

risk_engine = RiskEngine()
# Analysis results are keyed by session_id now, not a single global dict --
# each client's finalized note is independent of every other's.
analyses: dict[str, dict] = {}

AUTH_TIMEOUT_SECONDS = 10


@app.get("/health")
async def health():
    """Unauthenticated by design -- used by k8s readiness/liveness probes,
    which don't carry a bearer token."""
    return {"status": "online", "service": "clinical-audio-intelligence"}


@app.get("/metrics")
async def metrics():
    """Unauthenticated by design -- scraped in-cluster only; NetworkPolicy
    (infra/security/network-policy.yaml) restricts who can reach this port,
    not app-level auth."""
    return Response(metrics_response(), media_type="text/plain")


@app.websocket("/ws/audio")
async def audio_ingest(websocket: WebSocket):
    """
    Replaces the old server-side-microphone flow entirely. Protocol:

    1. Client opens the WebSocket and, as its FIRST message, sends
       {"type": "auth", "token": "<bearer JWT>"} -- browsers can't set an
       Authorization header on a WS handshake, so first-message auth is the
       standard workaround. Connection is closed if this doesn't arrive
       and validate within AUTH_TIMEOUT_SECONDS.
    2. Server creates a new AudioSession, tagged to the token's tenant_id,
       and replies {"type": "session_created", "session_id": "..."}.
    3. Client streams raw 16-bit PCM / 16kHz / mono audio as binary WS
       frames, in whatever chunk size its capture API produces --
       backend/audio/ingest.py handles reassembly.
    4. Server pushes {"type": "transcript_chunk", ...} messages back as
       segments are transcribed.
    5. Client sends {"type": "stop"} (or disconnects) to end the session;
       server flushes remaining audio, finalizes, and closes.
    """
    await websocket.accept()

    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=4401, reason="auth timeout")
        return

    if auth_msg.get("type") != "auth" or "token" not in auth_msg:
        await websocket.close(code=4401, reason="first message must be {type: auth, token: ...}")
        return

    try:
        principal = await decode_token(auth_msg["token"])
    except (HTTPException, JWTError):
        await websocket.close(code=4401, reason="invalid token")
        return

    try:
        principal.require_role("clinician")
    except HTTPException:
        await websocket.close(code=4403, reason="requires clinician role")
        return

    sessions: SessionManager = websocket.app.state.sessions
    session = sessions.create(principal.tenant_id)

    await db.audit_service.record(AuditEntry(
        tenant_id=principal.tenant_id, actor_id=principal.user_id,
        action="session.start", resource_type="audio_session", resource_id=session.session_id,
        metadata={},
    ))

    async def push_transcript_chunk(entry: dict):
        await websocket.send_json({"type": "transcript_chunk", **entry})

    session.start(on_chunk=push_transcript_chunk)
    await websocket.send_json({"type": "session_created", "session_id": session.session_id})

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"] is not None:
                session.ingest.push_bytes(message["bytes"])
            elif "text" in message and message["text"] is not None:
                import json as _json
                try:
                    control = _json.loads(message["text"])
                except _json.JSONDecodeError:
                    continue
                if control.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await sessions.close(session.session_id)
        await db.audit_service.record(AuditEntry(
            tenant_id=principal.tenant_id, actor_id=principal.user_id,
            action="session.stop", resource_type="audio_session", resource_id=session.session_id,
            metadata={"segments": len(session.transcript)},
        ))


@app.get("/sessions/{session_id}/transcript")
async def get_transcript(session_id: str, principal: Principal = Depends(get_current_principal)):
    session = _get_owned_session(session_id, principal)
    return {
        "entries": session.get_transcript(),
        "full_text": session.get_full_text(),
        "is_active": session.is_active,
    }


@app.post("/sessions/{session_id}/analyze")
async def analyze(session_id: str, principal: Principal = Depends(require_role("clinician"))):
    """Run full clinical analysis on a session's transcript."""
    session = _get_owned_session(session_id, principal)
    full_text = session.get_full_text()
    if not full_text.strip():
        return {"error": "No transcript available"}

    try:
        # Run extraction + SOAP in parallel -- both LLM calls are budget-checked
        # and metered independently via cost_tracker inside each function.
        entities, soap = await asyncio.gather(
            extract_clinical_entities(full_text, principal.tenant_id, db.cost_tracker),
            generate_soap_note(full_text, {}, principal.tenant_id, db.cost_tracker),
        )
        risk = risk_engine.analyze(entities, full_text)
        # Re-generate with entities included for a better note, matching
        # the original implementation's two-pass approach.
        soap = await generate_soap_note(full_text, entities, principal.tenant_id, db.cost_tracker)
    except BudgetExceeded as e:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(e))

    result = {
        "entities": entities,
        "soap": soap,
        "risk": risk,
        "transcript_length": len(full_text.split()),
        "segments": len(session.transcript),
    }
    analyses[session_id] = result

    await db.audit_service.record(AuditEntry(
        tenant_id=principal.tenant_id, actor_id=principal.user_id,
        action="analysis.complete", resource_type="audio_session", resource_id=session_id,
        metadata={
            "risk_flags": len(risk["flags"]),
            "highest_severity": risk["highest_severity"],
            "requires_immediate_action": risk["requires_immediate_action"],
        },
    ))

    # A critical flag is a distinct, higher-priority audit event from the
    # analysis completing at all -- makes chart review / compliance queries
    # ("show me every critical flag last quarter") a direct filter on
    # `action`, not a JSONB metadata scan.
    if risk["requires_immediate_action"]:
        await db.audit_service.record(AuditEntry(
            tenant_id=principal.tenant_id, actor_id=principal.user_id,
            action="risk.critical_flag_raised", resource_type="audio_session", resource_id=session_id,
            metadata={"flags": [f["flag"] for f in risk["flags"] if f["severity"] == "critical"]},
        ))

    return result


@app.get("/sessions/{session_id}/analysis")
async def get_analysis(session_id: str, principal: Principal = Depends(get_current_principal)):
    _get_owned_session(session_id, principal)
    return analyses.get(session_id) or {"error": "No analysis run yet. Call POST /sessions/{id}/analyze first."}


@app.get("/audit")
async def get_audit(principal: Principal = Depends(require_role("reviewer"))):
    """Audit access is restricted to the reviewer/admin role. The explicit
    WHERE clause and the RLS policy (infra/multi-tenancy/postgres-rls.sql)
    both scope this to the caller's tenant independently -- either one
    failing alone still can't leak across tenants."""
    async with acquire_tenant_conn(db.get_pool(), principal.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT action, resource_type, resource_id, metadata, timestamp "
            "FROM audit_log WHERE tenant_id = $1 ORDER BY id DESC LIMIT 200",
            principal.tenant_id,
        )
    return [dict(r) for r in rows]


def _get_owned_session(session_id: str, principal: Principal):
    session = app.state.sessions.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    require_tenant_match(session.tenant_id)  # 404s rather than 403s on mismatch, by design
    return session
