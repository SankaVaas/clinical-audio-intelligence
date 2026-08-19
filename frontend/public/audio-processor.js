// AudioWorkletProcessor runs on the audio rendering thread, off the main
// thread -- required because ScriptProcessorNode (the old API) is
// deprecated and runs on the main thread, which stutters the UI during
// capture. This file is loaded via audioContext.audioWorklet.addModule()
// from src/audio/AudioStreamer.ts and cannot be bundled by webpack, hence
// living in public/ as plain JS rather than in src/.
//
// Resampling: browsers typically run the audio graph at 44.1kHz or 48kHz;
// the backend's Whisper pipeline expects 16kHz. `sampleRate` below is a
// global provided by the AudioWorkletGlobalScope, reflecting the actual
// context rate (not necessarily what was requested), so this is correct
// regardless of what the browser actually gives us.
//
// This uses nearest-neighbor decimation, not a proper polyphase/sinc
// resampler -- adequate for speech intelligibility and Whisper's own
// robustness to minor aliasing, but a known quality trade-off. A
// production system with stringent transcription-accuracy requirements
// should replace this with a proper resampling library.
class PCMWorkletProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const targetSampleRate = (options.processorOptions && options.processorOptions.targetSampleRate) || 16000;
    this.ratio = sampleRate / targetSampleRate;
    this._carry = 0;       // fractional sample position carried between process() calls
    this._outBuffer = [];
    // Batch ~0.5s of resampled audio per postMessage to keep message-passing
    // overhead low without adding much latency to the transcript.
    this._chunkSamples = Math.floor(targetSampleRate * 0.5);
  }

  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0];
    if (!channel || channel.length === 0) return true;

    let pos = this._carry;
    while (pos < channel.length) {
      this._outBuffer.push(channel[Math.floor(pos)]);
      pos += this.ratio;
    }
    this._carry = pos - channel.length;

    if (this._outBuffer.length >= this._chunkSamples) {
      const floatChunk = this._outBuffer.splice(0, this._outBuffer.length);
      const pcm16 = new Int16Array(floatChunk.length);
      for (let i = 0; i < floatChunk.length; i++) {
        const s = Math.max(-1, Math.min(1, floatChunk[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm-worklet-processor", PCMWorkletProcessor);
