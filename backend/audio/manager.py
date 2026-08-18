"""
In-memory session registry: session_id -> AudioSession.

Deliberately in-memory, not Redis/Kafka-backed, for this change -- see
docs/ARCHITECTURE.md's note on deferring Kafka/PubSub until a concrete
throughput driver exists. The consequence that comes with that choice:
a session is pinned to whichever pod accepted its WebSocket connection.
That's fine for a single long-lived conversation (the normal case), but it
means the Ingress/Service must not load-balance a reconnect to a different
pod mid-session, and a pod restart loses any sessions it was holding.
Both are acceptable for now and are the concrete trigger for introducing
Kafka/PubSub later: the moment a session needs to survive a pod restart or
be resumable from a different pod, state has to move out of process memory.
"""
import uuid
from backend.audio.session import AudioSession
from backend.audio.transcriber import WhisperTranscriber
from backend.observability.metrics import active_sessions


class SessionManager:
    def __init__(self, transcriber: WhisperTranscriber):
        self._transcriber = transcriber
        self._sessions: dict[str, AudioSession] = {}

    def create(self, tenant_id: str) -> AudioSession:
        session_id = str(uuid.uuid4())
        session = AudioSession(session_id, tenant_id, self._transcriber)
        self._sessions[session_id] = session
        active_sessions.labels(tenant_id=tenant_id).inc()
        return session

    def get(self, session_id: str) -> AudioSession | None:
        return self._sessions.get(session_id)

    async def close(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session:
            await session.stop()
            active_sessions.labels(tenant_id=session.tenant_id).dec()
