import asyncio
from datetime import datetime
from .capture import AudioCapture
from .transcriber import WhisperTranscriber

class AudioSession:
    def __init__(self):
        self.capture = AudioCapture()
        self.transcriber = WhisperTranscriber(model_size="base")
        self.transcript: list = []
        self.is_active = False
        self._task = None

    async def start(self, broadcast=None):
        self.is_active = True
        self.capture.start()

        loop = asyncio.get_event_loop()

        while self.is_active:
            # Get audio chunk in thread pool (blocking call)
            chunk = await loop.run_in_executor(None, self.capture.get_chunk, 5)
            
            if chunk is None or not self.is_active:
                break

            # Transcribe in thread pool (CPU intensive)
            result = await loop.run_in_executor(
                None, self.transcriber.transcribe_chunk, chunk
            )

            if result["text"]:
                entry = {
                    "text": result["text"],
                    "confidence": result["confidence"],
                    "timestamp": datetime.utcnow().isoformat(),
                    "speaker": "unknown"   # diarization comes later
                }
                self.transcript.append(entry)

                if broadcast:
                    await broadcast({
                        "type": "transcript_chunk",
                        **entry
                    })

    def stop(self):
        self.is_active = False
        self.capture.stop()

    def get_transcript(self) -> list:
        return self.transcript
    
    def get_full_text(self) -> str:
        return " ".join([t["text"] for t in self.transcript])