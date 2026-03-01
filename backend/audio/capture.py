import sounddevice as sd
import numpy as np
import queue
import threading

SAMPLE_RATE = 16000  # Whisper expects 16kHz
CHUNK_DURATION = 5   # seconds per chunk
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_DURATION

class AudioCapture:
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self._thread = None

    def _callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        # Convert to mono float32
        audio_chunk = indata[:, 0].copy().astype(np.float32)
        self.audio_queue.put(audio_chunk)

    def start(self):
        self.is_recording = True
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32,
            blocksize=CHUNK_SAMPLES,
            callback=self._callback
        )
        self.stream.start()
        print("🎙️ Audio capture started")

    def stop(self):
        self.is_recording = False
        if hasattr(self, "stream"):
            self.stream.stop()
            self.stream.close()
        print("🎙️ Audio capture stopped")

    def get_chunk(self, timeout=5):
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None