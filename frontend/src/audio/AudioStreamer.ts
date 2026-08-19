/**
 * Client-side microphone capture. This is the piece that makes the
 * "Audio Ingestion" stage of the architecture actually work as designed --
 * the backend no longer opens a microphone (it has none, running in a
 * pod); this class captures it here and streams PCM frames out over a
 * caller-supplied send function (WebSocket.send).
 */
export class AudioStreamer {
  private audioContext: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private stream: MediaStream | null = null;

  async start(onPCMChunk: (chunk: ArrayBuffer) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.audioContext = new AudioContext();
    await this.audioContext.audioWorklet.addModule("/audio-processor.js");

    this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);
    this.workletNode = new AudioWorkletNode(this.audioContext, "pcm-worklet-processor", {
      processorOptions: { targetSampleRate: 16000 },
    });

    this.workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      onPCMChunk(event.data);
    };

    this.sourceNode.connect(this.workletNode);
    // Deliberately NOT connected to audioContext.destination -- we don't
    // want to play the user's own mic input back to them as an echo.
  }

  stop(): void {
    this.workletNode?.disconnect();
    this.sourceNode?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    this.audioContext?.close();
    this.workletNode = null;
    this.sourceNode = null;
    this.stream = null;
    this.audioContext = null;
  }
}
