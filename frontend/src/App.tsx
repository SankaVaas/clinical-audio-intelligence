import { useState, useEffect, useRef } from "react";
import axios from "axios";

const API = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";

type TranscriptEntry = {
  text: string;
  confidence: number;
  timestamp: string;
  speaker: string;
};

export default function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const ws = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // WebSocket
  useEffect(() => {
    ws.current = new WebSocket(WS_URL);
    ws.current.onopen = () => setWsStatus("connected");
    ws.current.onclose = () => setWsStatus("disconnected");
    ws.current.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "transcript_chunk") {
        setTranscript((prev) => [...prev, {
          text: msg.text,
          confidence: msg.confidence,
          timestamp: msg.timestamp,
          speaker: msg.speaker
        }]);
      }
    };
    return () => ws.current?.close();
  }, []);

  // Auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [transcript]);

  const startSession = async () => {
    await axios.post(`${API}/session/start`);
    setIsRecording(true);
  };

  const stopSession = async () => {
    await axios.post(`${API}/session/stop`);
    setIsRecording(false);
  };

  const clearTranscript = () => setTranscript([]);

  const confidenceColor = (c: number) => {
    if (c > 0.7) return "#00ff88";
    if (c > 0.4) return "#ff9900";
    return "#ff4444";
  };

  const confidenceLabel = (c: number) => {
    if (c > 0.7) return "HIGH";
    if (c > 0.4) return "MED";
    return "LOW";
  };

  return (
    <div style={{
      fontFamily: "'JetBrains Mono', 'Courier New', monospace",
      background: "#080c12",
      minHeight: "100vh",
      color: "#c9d1d9"
    }}>
      {/* Header */}
      <div style={{
        background: "#0d1117",
        borderBottom: "1px solid #1e2a3a",
        padding: "14px 28px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{
            width: 10, height: 10, borderRadius: "50%",
            background: isRecording ? "#ff4444" : "#1e2a3a",
            boxShadow: isRecording ? "0 0 12px #ff4444" : "none",
            animation: isRecording ? "pulse 1s infinite" : "none"
          }} />
          <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: 3, color: "#e6edf3" }}>
            CLINICAL AUDIO INTELLIGENCE
          </span>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center", fontSize: 11 }}>
          <span style={{ color: wsStatus === "connected" ? "#00ff88" : "#ff4444", letterSpacing: 1 }}>
            ● WS {wsStatus.toUpperCase()}
          </span>
          <span style={{ color: "#444", letterSpacing: 1 }}>
            {transcript.length} SEGMENTS
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", height: "calc(100vh - 57px)" }}>
        {/* Main Transcript Panel */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {/* Controls */}
          <div style={{
            padding: "16px 28px",
            borderBottom: "1px solid #1e2a3a",
            background: "#0d1117",
            display: "flex",
            gap: 12,
            alignItems: "center"
          }}>
            <button
              onClick={isRecording ? stopSession : startSession}
              style={{
                background: isRecording ? "#ff000022" : "#00ff8822",
                border: `1px solid ${isRecording ? "#ff4444" : "#00ff88"}`,
                color: isRecording ? "#ff4444" : "#00ff88",
                padding: "10px 24px",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 700,
                fontFamily: "inherit",
                letterSpacing: 2
              }}
            >
              {isRecording ? "⏹ STOP SESSION" : "⏺ START SESSION"}
            </button>
            <button
              onClick={clearTranscript}
              style={{
                background: "transparent",
                border: "1px solid #1e2a3a",
                color: "#444",
                padding: "10px 20px",
                borderRadius: 4,
                cursor: "pointer",
                fontSize: 12,
                fontFamily: "inherit",
                letterSpacing: 1
              }}
            >
              CLEAR
            </button>
            {isRecording && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: 8 }}>
                <div style={{ display: "flex", gap: 3 }}>
                  {[1,2,3,4,5].map(i => (
                    <div key={i} style={{
                      width: 3,
                      background: "#ff4444",
                      borderRadius: 2,
                      animation: `waveform${i} ${0.4 + i * 0.1}s ease-in-out infinite alternate`,
                      height: `${8 + i * 4}px`
                    }} />
                  ))}
                </div>
                <span style={{ fontSize: 11, color: "#ff4444", letterSpacing: 2 }}>LISTENING</span>
              </div>
            )}
          </div>

          {/* Transcript */}
          <div style={{ flex: 1, overflow: "auto", padding: "24px 28px" }}>
            {transcript.length === 0 && (
              <div style={{ color: "#1e2a3a", fontSize: 14, marginTop: 40, textAlign: "center" }}>
                <div style={{ fontSize: 40, marginBottom: 16 }}>🎙️</div>
                <div>Press START SESSION and begin speaking</div>
                <div style={{ fontSize: 11, marginTop: 8, color: "#1a2233" }}>
                  Transcription will appear here in real time
                </div>
              </div>
            )}
            {transcript.map((entry, i) => (
              <div key={i} style={{
                marginBottom: 16,
                padding: "12px 16px",
                background: "#0d1117",
                borderRadius: 6,
                borderLeft: `3px solid ${confidenceColor(entry.confidence)}`,
                display: "flex",
                gap: 16,
                alignItems: "flex-start"
              }}>
                <div style={{ flexShrink: 0, textAlign: "center" }}>
                  <div style={{
                    fontSize: 10,
                    color: confidenceColor(entry.confidence),
                    letterSpacing: 1,
                    marginBottom: 2
                  }}>
                    {confidenceLabel(entry.confidence)}
                  </div>
                  <div style={{ fontSize: 10, color: "#444" }}>
                    {Math.round(entry.confidence * 100)}%
                  </div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, color: "#e6edf3", lineHeight: 1.6 }}>
                    {entry.text}
                  </div>
                  <div style={{ fontSize: 10, color: "#333", marginTop: 4 }}>
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Stats Sidebar */}
        <div style={{
          background: "#0d1117",
          borderLeft: "1px solid #1e2a3a",
          padding: 20,
          display: "flex",
          flexDirection: "column",
          gap: 24
        }}>
          {/* Session Stats */}
          <div>
            <div style={{ fontSize: 11, color: "#444", letterSpacing: 2, marginBottom: 14 }}>
              SESSION STATS
            </div>
            <StatRow label="SEGMENTS" value={transcript.length.toString()} />
            <StatRow
              label="AVG CONFIDENCE"
              value={transcript.length > 0
                ? Math.round(transcript.reduce((a, b) => a + b.confidence, 0) / transcript.length * 100) + "%"
                : "—"}
            />
            <StatRow
              label="WORD COUNT"
              value={transcript.reduce((a, b) => a + b.text.split(" ").length, 0).toString()}
            />
            <StatRow
              label="LOW CONF"
              value={transcript.filter(t => t.confidence < 0.4).length.toString()}
              valueColor="#ff4444"
            />
          </div>

          {/* Confidence Legend */}
          <div>
            <div style={{ fontSize: 11, color: "#444", letterSpacing: 2, marginBottom: 14 }}>
              CONFIDENCE
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { label: "HIGH >70%", color: "#00ff88" },
                { label: "MED 40-70%", color: "#ff9900" },
                { label: "LOW <40%", color: "#ff4444" },
              ].map(({ label, color }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div style={{ width: 3, height: 16, background: color, borderRadius: 2 }} />
                  <span style={{ fontSize: 11, color: "#555" }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Full text export */}
          <div style={{ marginTop: "auto" }}>
            <div style={{ fontSize: 11, color: "#444", letterSpacing: 2, marginBottom: 10 }}>
              FULL TEXT
            </div>
            <div style={{
              fontSize: 11,
              color: "#333",
              lineHeight: 1.6,
              maxHeight: 200,
              overflow: "auto",
              background: "#080c12",
              padding: 10,
              borderRadius: 4
            }}>
              {transcript.map(t => t.text).join(" ") || "—"}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        @keyframes waveform1 { from { height: 8px; } to { height: 20px; } }
        @keyframes waveform2 { from { height: 12px; } to { height: 6px; } }
        @keyframes waveform3 { from { height: 16px; } to { height: 24px; } }
        @keyframes waveform4 { from { height: 8px; } to { height: 18px; } }
        @keyframes waveform5 { from { height: 20px; } to { height: 10px; } }
      `}</style>
    </div>
  );
}

function StatRow({ label, value, valueColor = "#00ff88" }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10, fontSize: 12 }}>
      <span style={{ color: "#444", letterSpacing: 1 }}>{label}</span>
      <span style={{ color: valueColor, fontWeight: 700 }}>{value}</span>
    </div>
  );
}