import whisper
import numpy as np
import torch

class WhisperTranscriber:
    def __init__(self, model_size="base"):
        print(f"Loading Whisper {model_size} model...")
        self.model = whisper.load_model(model_size)
        self.sample_rate = 16000
        # Sliding window buffer for context
        self.context_buffer = np.array([], dtype=np.float32)
        self.max_context_seconds = 30
        print("✅ Whisper ready")

    def transcribe_chunk(self, audio_chunk: np.ndarray) -> dict:
        # Append to context buffer
        self.context_buffer = np.concatenate([self.context_buffer, audio_chunk])
        
        # Keep only last 30 seconds to avoid memory bloat
        max_samples = self.sample_rate * self.max_context_seconds
        if len(self.context_buffer) > max_samples:
            self.context_buffer = self.context_buffer[-max_samples:]

        # Whisper needs at least 1 second of audio
        if len(audio_chunk) < self.sample_rate:
            return {"text": "", "confidence": 0.0, "language": "en"}

        # Run inference
        result = self.model.transcribe(
            audio_chunk,
            language="en",
            fp16=False,          # CPU safe
            condition_on_previous_text=True,
            no_speech_threshold=0.3,
            logprob_threshold=-1.0
        )

        # Extract confidence from segments
        segments = result.get("segments", [])
        if segments:
            avg_logprob = np.mean([s.get("avg_logprob", -1) for s in segments])
            # Convert log probability to 0-1 confidence
            confidence = float(np.exp(avg_logprob))
        else:
            confidence = 0.0

        return {
            "text": result["text"].strip(),
            "confidence": round(min(max(confidence, 0.0), 1.0), 3),
            "language": result.get("language", "en"),
            "segments": segments
        }

    def clear_context(self):
        self.context_buffer = np.array([], dtype=np.float32)