"""
Replaces backend/audio/capture.py's role. The client (browser/mobile), not
the server, owns the microphone -- it captures audio and streams raw PCM
frames to this buffer over the WebSocket connection established in
backend/audio/manager.py. This is the fix for the issue flagged repeatedly
in docs/ARCHITECTURE.md: a k8s pod has no microphone and no relationship to
whichever end user is speaking.

Wire format: client sends 16-bit signed PCM, mono, 16kHz, as binary
WebSocket frames of any size -- this buffer handles reassembly into
fixed-duration chunks regardless of how the client chooses to chunk its
sends (every browser's MediaRecorder/AudioWorklet does this slightly
differently, so the buffer, not the client, owns chunk-size correctness).
"""
import asyncio
import numpy as np

SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHUNK_DURATION = 5   # seconds per chunk, matches CHUNK_SAMPLES below
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_DURATION
BYTES_PER_SAMPLE = 2  # 16-bit PCM


class AudioIngestBuffer:
    def __init__(self):
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._pending = bytearray()
        self.is_active = False

    def start(self):
        self.is_active = True

    def stop(self):
        self.is_active = False
        # Flush whatever's left, even if it's short of a full chunk --
        # dropping the trailing few seconds of a clinical conversation on
        # disconnect is a data-loss bug, not an acceptable edge case.
        if len(self._pending) >= BYTES_PER_SAMPLE:
            self._queue.put_nowait(self._pcm_bytes_to_float32(bytes(self._pending)))
            self._pending.clear()

    def push_bytes(self, data: bytes):
        """Called from the WebSocket receive loop for every binary frame
        the client sends."""
        self._pending.extend(data)
        chunk_bytes = CHUNK_SAMPLES * BYTES_PER_SAMPLE
        while len(self._pending) >= chunk_bytes:
            chunk = bytes(self._pending[:chunk_bytes])
            del self._pending[:chunk_bytes]
            self._queue.put_nowait(self._pcm_bytes_to_float32(chunk))

    async def get_chunk(self, timeout: float = 5.0):
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    @staticmethod
    def _pcm_bytes_to_float32(data: bytes) -> np.ndarray:
        # int16 PCM -> float32 in [-1, 1], the format Whisper expects.
        return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
