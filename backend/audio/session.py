"""
One AudioSession per client connection/tenant, not the single process-global
instance the original design used. This is what makes multi-tenancy actually
correct at the session-state level, not just at the auth/audit/cost level
wired in the previous change.

The Whisper model itself is NOT owned by AudioSession -- it's loaded once
per pod (backend/main.py lifespan) and shared read-only across every
concurrent session, since a Whisper model instance is large and expensive
to duplicate. AudioSession only owns per-client state: the ingest buffer
and the growing transcript.
"""
import asyncio
from datetime import datetime, timezone

from backend.audio.ingest import AudioIngestBuffer
from backend.audio.transcriber import WhisperTranscriber

CHUNK_DURATION_GRACE = 8  # seconds; slightly more than one transcription chunk


class AudioSession:
    def __init__(self, session_id: str, tenant_id: str, transcriber: WhisperTranscriber):
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.transcriber = transcriber   # shared, not owned
        self.ingest = AudioIngestBuffer()
        self.transcript: list = []
        self.is_active = False
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._pump_task: asyncio.Task | None = None

    def start(self, on_chunk=None):
        """Starts the background loop that pulls buffered audio and
        transcribes it. `on_chunk(entry)` is called for each new transcript
        entry, typically wired to push over the same WebSocket."""
        self.is_active = True
        self.ingest.start()
        self._pump_task = asyncio.create_task(self._pump(on_chunk))

    async def _pump(self, on_chunk):
        loop = asyncio.get_event_loop()
        while self.is_active:
            chunk = await self.ingest.get_chunk(timeout=5)
            if chunk is None:
                continue  # no audio yet, keep waiting -- not a disconnect

            # Transcription is CPU-bound; run off the event loop so one
            # session's inference doesn't stall every other session's I/O
            # on this pod.
            result = await loop.run_in_executor(None, self.transcriber.transcribe_chunk, chunk)

            if result["text"]:
                entry = {
                    "text": result["text"],
                    "confidence": result["confidence"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "speaker": "unknown",   # diarization comes later
                }
                self.transcript.append(entry)
                if on_chunk:
                    await on_chunk(entry)

    async def stop(self):
        self.is_active = False
        self.ingest.stop()
        if self._pump_task:
            # Let the pump drain whatever stop() just flushed into the
            # queue before cancelling, so the last few seconds of audio
            # aren't silently dropped on disconnect.
            try:
                await asyncio.wait_for(self._pump_task, timeout=CHUNK_DURATION_GRACE)
            except asyncio.TimeoutError:
                self._pump_task.cancel()

    def get_transcript(self) -> list:
        return self.transcript

    def get_full_text(self) -> str:
        return " ".join(t["text"] for t in self.transcript)
