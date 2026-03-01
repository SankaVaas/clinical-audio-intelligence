import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";

const API = "http://localhost:8080";
const WS_URL = "ws://localhost:8080/ws";

type TranscriptEntry = { text: string; confidence: number; timestamp: string; speaker: string };
type Analysis = { entities: any; soap: any; risk: any; transcript_length: number; segments: number };

export default function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [activeTab, setActiveTab] = useState<"entities" | "soap" | "risk">("entities");
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const [timer, setTimer] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const ws = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // WebSocket
  useEffect(() => {
    ws.current = new WebSocket(WS_URL);
    ws.current.onopen = () => setWsStatus("connected");
    ws.current.onclose = () => setWsStatus("disconnected");
    ws.current.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "transcript_chunk") {
        setTranscript((prev) => [...prev, msg]);
      }
      if (msg.type === "analysis_complete") {
        setAnalysis(msg);
        setIsAnalyzing(false);
        setActiveTab("risk");
      }
    };
    return () => ws.current?.close();
  }, []);

  // Auto scroll transcript
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [transcript]);

  // Session timer
  useEffect(() => {
    if (isRecording) {
      setTimer(0);
      timerRef.current = setInterval(() => setTimer((t) => t + 1), 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [isRecording]);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const formatTime = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const startSession = async () => {
    await axios.post(`${API}/session/start`);
    setIsRecording(true);
    setTranscript([]);
    setAnalysis(null);
  };

  const stopSession = async () => {
    await axios.post(`${API}/session/stop`);
    setIsRecording(false);
  };

  const clearSession = async () => {
    if (isRecording) await stopSession();
    setTranscript([]);
    setAnalysis(null);
    setTimer(0);
    showToast("Session cleared");
  };

  const runAnalysis = async () => {
    if (transcript.length === 0) { showToast("No transcript to analyze"); return; }
    setIsAnalyzing(true);
    setActiveTab("entities");
    try {
      const res = await axios.post(`${API}/analyze`);
      setAnalysis(res.data);
      setActiveTab("risk");
    } catch {
      showToast("Analysis failed — check backend");
    }
    setIsAnalyzing(false);
  };

  const copySOAP = () => {
    if (!analysis?.soap) return;
    const { subjective, objective, assessment, plan } = analysis.soap;
    const text = `SOAP NOTE\n\nS — SUBJECTIVE\n${subjective}\n\nO — OBJECTIVE\n${objective}\n\nA — ASSESSMENT\n${assessment}\n\nP — PLAN\n${plan}`;
    navigator.clipboard.writeText(text);
    showToast("SOAP note copied to clipboard");
  };

  const exportTranscript = () => {
    if (transcript.length === 0) { showToast("No transcript to export"); return; }
    const text = transcript.map((e) => `[${new Date(e.timestamp).toLocaleTimeString()}] ${e.text}`).join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Transcript exported");
  };

  const exportAnalysis = () => {
    if (!analysis) { showToast("No analysis to export"); return; }
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `analysis_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast("Analysis exported as JSON");
  };

  const severityColor = (s: string) =>
    ({ critical: "#ff2244", high: "#ff6600", medium: "#ff9900", low: "#ffcc00", none: "#00ff88" }[s] || "#888");
  const confidenceColor = (c: number) => c > 0.7 ? "#00ff88" : c > 0.4 ? "#ff9900" : "#ff4444";
  const completenessColor = (c: string) =>
    ({ complete: "#00ff88", adequate: "#ff9900", partial: "#ff4444" }[c] || "#888");

  const avgConfidence = transcript.length > 0
    ? Math.round(transcript.reduce((a, b) => a + b.confidence, 0) / transcript.length * 100)
    : 0;

  return (
    <div style={{ fontFamily: "'JetBrains Mono', 'Courier New', monospace", background: "#060910", minHeight: "100vh", color: "#c9d1d9", position: "relative" }}>

      {/* Toast */}
      {toast && (
        <div style={{ position: "fixed", bottom: 24, left: "50%", transform: "translateX(-50%)", background: "#0d1117", border: "1px solid #1e2a3a", color: "#e6edf3", padding: "10px 20px", borderRadius: 6, fontSize: 12, letterSpacing: 1, zIndex: 9999, boxShadow: "0 4px 20px #00000088" }}>
          {toast}
        </div>
      )}

      {/* Header */}
      <div style={{ background: "#0d1117", borderBottom: "1px solid #1e2a3a", padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 9, height: 9, borderRadius: "50%", background: isRecording ? "#ff4444" : "#00ff88", boxShadow: isRecording ? "0 0 10px #ff4444" : "0 0 8px #00ff88", animation: isRecording ? "blink 1s infinite" : "none" }} />
          <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: 3, color: "#e6edf3" }}>CLINICAL AUDIO INTELLIGENCE</span>
          <span style={{ fontSize: 10, color: "#333", letterSpacing: 1 }}>v2.0</span>
        </div>
        <div style={{ display: "flex", gap: 20, fontSize: 11, alignItems: "center" }}>
          {isRecording && (
            <span style={{ color: "#ff4444", letterSpacing: 1, fontWeight: 700 }}>⏺ {formatTime(timer)}</span>
          )}
          {analysis?.risk && (
            <span style={{ color: severityColor(analysis.risk.highest_severity), letterSpacing: 1 }}>
              ● RISK: {analysis.risk.highest_severity.toUpperCase()}
            </span>
          )}
          <span style={{ color: wsStatus === "connected" ? "#00ff88" : "#ff4444", letterSpacing: 1 }}>
            ● WS {wsStatus.toUpperCase()}
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", height: "calc(100vh - 53px)" }}>

        {/* LEFT PANEL */}
        <div style={{ borderRight: "1px solid #1e2a3a", display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
          {/* Primary Controls */}
          <div style={{ padding: "14px 16px", borderBottom: "1px solid #1e2a3a", background: "#0d1117" }}>
            <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 10 }}>SESSION</div>
            <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
              <button onClick={isRecording ? stopSession : startSession}
                style={{ flex: 1, background: isRecording ? "#ff000018" : "#00ff8818", border: `1px solid ${isRecording ? "#ff4444" : "#00ff88"}`, color: isRecording ? "#ff4444" : "#00ff88", padding: "9px 0", borderRadius: 4, cursor: "pointer", fontSize: 11, fontWeight: 700, fontFamily: "inherit", letterSpacing: 2, transition: "all 0.2s" }}>
                {isRecording ? "⏹ STOP" : "⏺ RECORD"}
              </button>
              <button onClick={runAnalysis} disabled={isAnalyzing || transcript.length === 0}
                style={{ flex: 1, background: isAnalyzing ? "#111" : transcript.length === 0 ? "#0a0a0f" : "#0044ff18", border: `1px solid ${isAnalyzing ? "#333" : transcript.length === 0 ? "#1a1a2e" : "#4488ff"}`, color: isAnalyzing ? "#333" : transcript.length === 0 ? "#2a2a3e" : "#4488ff", padding: "9px 0", borderRadius: 4, cursor: transcript.length === 0 ? "not-allowed" : "pointer", fontSize: 11, fontWeight: 700, fontFamily: "inherit", letterSpacing: 2 }}>
                {isAnalyzing ? "..." : "⚡ ANALYZE"}
              </button>
            </div>

            {/* Secondary Controls */}
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={clearSession}
                style={{ flex: 1, background: "transparent", border: "1px solid #1e2a3a", color: "#444", padding: "6px 0", borderRadius: 4, cursor: "pointer", fontSize: 10, fontFamily: "inherit", letterSpacing: 1 }}>
                🗑 CLEAR
              </button>
              <button onClick={exportTranscript} disabled={transcript.length === 0}
                style={{ flex: 1, background: "transparent", border: "1px solid #1e2a3a", color: transcript.length === 0 ? "#222" : "#555", padding: "6px 0", borderRadius: 4, cursor: transcript.length === 0 ? "not-allowed" : "pointer", fontSize: 10, fontFamily: "inherit", letterSpacing: 1 }}>
                ↓ TRANSCRIPT
              </button>
              <button onClick={exportAnalysis} disabled={!analysis}
                style={{ flex: 1, background: "transparent", border: "1px solid #1e2a3a", color: !analysis ? "#222" : "#555", padding: "6px 0", borderRadius: 4, cursor: !analysis ? "not-allowed" : "pointer", fontSize: 10, fontFamily: "inherit", letterSpacing: 1 }}>
                ↓ ANALYSIS
              </button>
            </div>

            {/* Recording waveform */}
            {isRecording && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, padding: "8px 10px", background: "#ff000010", border: "1px solid #ff444422", borderRadius: 4 }}>
                <div style={{ display: "flex", gap: 2, alignItems: "center" }}>
                  {[6, 12, 18, 12, 8, 16, 10].map((h, i) => (
                    <div key={i} style={{ width: 2, height: h, background: "#ff4444", borderRadius: 2, animation: `wave ${0.3 + i * 0.08}s ease-in-out infinite alternate` }} />
                  ))}
                </div>
                <span style={{ fontSize: 10, color: "#ff6666", letterSpacing: 2 }}>CAPTURING AUDIO</span>
              </div>
            )}
          </div>

          {/* Session Stats */}
          <div style={{ padding: "10px 16px", borderBottom: "1px solid #3c56bc", display: "flex", gap: 0 }}>
            {[
              { label: "SEGMENTS", value: transcript.length.toString() },
              { label: "WORDS", value: transcript.reduce((a, b) => a + b.text.split(" ").length, 0).toString() },
              { label: "AVG CONF", value: transcript.length > 0 ? `${avgConfidence}%` : "—" },
              { label: "DURATION", value: formatTime(timer) },
            ].map(({ label, value }) => (
              <div key={label} style={{ flex: 1, textAlign: "center", borderRight: "1px solid #f38225", padding: "4px 0" }}>
                <div style={{ fontSize: 13, color: "#e6edf3", fontWeight: 700 }}>{value}</div>
                <div style={{ fontSize: 9, color: "#696d05", letterSpacing: 1, marginTop: 2 }}>{label}</div>
              </div>
            ))}
          </div>

          {/* Transcript */}
          <div style={{ fontSize: 10, color: "#5a6b9d", letterSpacing: 2, padding: "10px 16px 4px" }}>
            LIVE TRANSCRIPT
            {transcript.length > 0 && <span style={{ marginLeft: 8, color: "#1e2a3a" }}>— {transcript.length} segments</span>}
          </div>
          <div style={{ flex: 1, overflow: "auto", padding: "8px 12px", maxHeight: "calc(100vh - 220px)", overflowY: "scroll" }}>
            {transcript.length === 0 && !isRecording && (
              <div style={{ color: "#1a2233", fontSize: 12, textAlign: "center", marginTop: 48, lineHeight: 2 }}>
                <div style={{ fontSize: 28, marginBottom: 12, opacity: 0.3 }}>🎙</div>
                Press RECORD<br />then speak clearly
              </div>
            )}
            {transcript.length === 0 && isRecording && (
              <div style={{ color: "#333", fontSize: 11, textAlign: "center", marginTop: 48, lineHeight: 2 }}>
                Listening...<br />speak now
              </div>
            )}
            {transcript.map((entry, i) => (
              <div key={i} style={{ marginBottom: 8, padding: "9px 11px", background: "#0d1117", borderRadius: 4, borderLeft: `2px solid ${confidenceColor(entry.confidence)}` }}>
                <div style={{ fontSize: 12, color: "#c9d1d9", lineHeight: 1.6 }}>{entry.text}</div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 10 }}>
                  <span style={{ color: "#333" }}>{new Date(entry.timestamp).toLocaleTimeString()}</span>
                  <span style={{ color: confidenceColor(entry.confidence) }}>{Math.round(entry.confidence * 100)}%</span>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* RIGHT PANEL */}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {/* Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid #1e2a3a", background: "#0d1117", alignItems: "center" }}>
            {(["entities", "soap", "risk"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ padding: "12px 24px", fontSize: 11, letterSpacing: 2, border: "none", background: "transparent", color: activeTab === tab ? "#4488ff" : "#aeafb3", borderBottom: activeTab === tab ? "2px solid #4488ff" : "2px solid transparent", cursor: "pointer", fontFamily: "inherit", transition: "color 0.2s" }}>
                {tab.toUpperCase()}
                {tab === "risk" && (analysis?.risk?.flags?.length ?? 0) > 0 && (
                  <span style={{ marginLeft: 6, background: severityColor(analysis?.risk?.highest_severity ?? "none"), color: "#000", borderRadius: 10, padding: "1px 6px", fontSize: 9, fontWeight: 700 }}>
                    {analysis?.risk?.flags?.length ?? 0}
                  </span>
                )}
              </button>
            ))}
            {/* SOAP copy button in tab bar */}
            {activeTab === "soap" && analysis?.soap && (
              <button onClick={copySOAP}
                style={{ marginLeft: "auto", marginRight: 16, background: "transparent", border: "1px solid #1e2a3a", color: "#555", padding: "5px 14px", borderRadius: 4, cursor: "pointer", fontSize: 10, fontFamily: "inherit", letterSpacing: 1 }}>
                ⎘ COPY NOTE
              </button>
            )}
          </div>

          {/* Tab Content */}
          <div style={{ flex: 1, overflow: "auto", padding: 24 }}>

            {/* Analyzing spinner */}
            {isAnalyzing && (
              <div style={{ textAlign: "center", marginTop: 80 }}>
                <div style={{ fontSize: 32, marginBottom: 16, animation: "spin 1s linear infinite", display: "inline-block" }}>⚡</div>
                <div style={{ fontSize: 12, color: "#4488ff", letterSpacing: 3 }}>RUNNING CLINICAL ANALYSIS</div>
                <div style={{ fontSize: 10, color: "#333", marginTop: 8, lineHeight: 2 }}>
                  Extracting entities<br />Generating SOAP note<br />Analyzing risk flags
                </div>
              </div>
            )}

            {/* No analysis yet */}
            {!isAnalyzing && !analysis && (
              <div style={{ textAlign: "center", marginTop: 80, color: "#5a74ac" }}>
                <div style={{ fontSize: 32, marginBottom: 16, opacity: 0.3 }}>⚕</div>
                <div style={{ fontSize: 12, letterSpacing: 1 }}>
                  Record a session then press ANALYZE<br />
                  <span style={{ fontSize: 10, color: "#206423", marginTop: 8, display: "block" }}>
                    Clinical entities · SOAP note · Risk flags
                  </span>
                </div>
              </div>
            )}

            {/* ── ENTITIES TAB ── */}
            {!isAnalyzing && analysis && activeTab === "entities" && (
              <div>
                <SectionHeader title="SYMPTOMS" count={analysis.entities.symptoms?.length} />
                {analysis.entities.symptoms?.length === 0 && <NoneFound />}
                {analysis.entities.symptoms?.map((s: any, i: number) => (
                  <EntityCard key={i} primary={s.term}
                    badges={[
                      { label: s.severity || "severity unknown", color: severityColor(s.severity) + "22" },
                      { label: s.duration || "duration unknown", color: "#1e2a3a" }
                    ]}
                    confidence={s.confidence} />
                ))}

                <SectionHeader title="MEDICATIONS" count={analysis.entities.medications?.length} />
                {analysis.entities.medications?.length === 0 && <NoneFound />}
                {analysis.entities.medications?.map((m: any, i: number) => (
                  <EntityCard key={i} primary={m.name}
                    badges={[
                      { label: m.dosage || "dosage unknown", color: "#0044ff22" },
                      { label: m.frequency || "freq unknown", color: "#0044ff22" }
                    ]}
                    confidence={m.confidence} />
                ))}

                <SectionHeader title="ALLERGIES" count={analysis.entities.allergies?.length} />
                {analysis.entities.allergies?.length === 0 && <NoneFound label="No allergies documented" />}
                {analysis.entities.allergies?.map((a: any, i: number) => (
                  <EntityCard key={i} primary={a.substance}
                    badges={[{ label: a.reaction || "reaction unknown", color: "#ff440022" }]}
                    confidence={a.confidence} />
                ))}

                <SectionHeader title="MEDICAL HISTORY" count={analysis.entities.history?.length} />
                {analysis.entities.history?.length === 0 && <NoneFound label="No history documented" />}
                {analysis.entities.history?.map((h: any, i: number) => (
                  <EntityCard key={i} primary={h.condition}
                    badges={[{ label: h.status, color: "#1e2a3a" }]}
                    confidence={h.confidence} />
                ))}

                <SectionHeader title="VITALS" count={analysis.entities.vitals?.length} />
                {analysis.entities.vitals?.length === 0 && <NoneFound label="No vitals recorded" />}
                {analysis.entities.vitals?.map((v: any, i: number) => (
                  <EntityCard key={i} primary={`${v.type}: ${v.value}`} badges={[]} confidence={v.confidence} />
                ))}
              </div>
            )}

            {/* ── SOAP TAB ── */}
            {!isAnalyzing && analysis && activeTab === "soap" && (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                  <span style={{ fontSize: 10, color: "#333", letterSpacing: 2 }}>AUTO-GENERATED SOAP NOTE</span>
                  <div style={{ display: "flex", gap: 16, fontSize: 11 }}>
                    <span style={{ color: completenessColor(analysis.soap.completeness) }}>
                      ● {analysis.soap.completeness?.toUpperCase()}
                    </span>
                    <span style={{ color: confidenceColor(analysis.soap.confidence) }}>
                      {Math.round(analysis.soap.confidence * 100)}% CONFIDENCE
                    </span>
                  </div>
                </div>
                {[
                  { key: "S", label: "SUBJECTIVE", field: "subjective", color: "#4488ff", desc: "Patient's own account" },
                  { key: "O", label: "OBJECTIVE", field: "objective", color: "#00ff88", desc: "Observable findings" },
                  { key: "A", label: "ASSESSMENT", field: "assessment", color: "#ff9900", desc: "Clinical interpretation" },
                  { key: "P", label: "PLAN", field: "plan", color: "#cc44ff", desc: "Next steps" },
                ].map(({ key, label, field, color, desc }) => (
                  <div key={key} style={{ marginBottom: 14, background: "#0d1117", borderRadius: 6, padding: 16, borderLeft: `3px solid ${color}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                      <div style={{ width: 26, height: 26, borderRadius: "50%", background: `${color}18`, border: `1px solid ${color}66`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, color, flexShrink: 0 }}>{key}</div>
                      <div>
                        <div style={{ fontSize: 11, color: "#666", letterSpacing: 2 }}>{label}</div>
                        <div style={{ fontSize: 9, color: "#333", letterSpacing: 1 }}>{desc}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: 13, color: "#c9d1d9", lineHeight: 1.8, paddingLeft: 36 }}>
                      {analysis.soap[field] || <span style={{ color: "#2a2a3e", fontStyle: "italic" }}>Not documented</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* ── RISK TAB ── */}
            {!isAnalyzing && analysis && activeTab === "risk" && (
              <div>
                {/* Summary */}
                <div style={{ background: "#0d1117", borderRadius: 6, padding: 16, marginBottom: 20, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, border: `1px solid ${severityColor(analysis.risk.highest_severity)}33` }}>
                  <div>
                    <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 6 }}>SEVERITY</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: severityColor(analysis.risk.highest_severity), letterSpacing: 2 }}>
                      {analysis.risk.highest_severity.toUpperCase()}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 6 }}>FLAGS</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: "#e6edf3" }}>
                      {analysis.risk.flags.length}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 6 }}>IMMEDIATE ACTION</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: analysis.risk.requires_immediate_action ? "#ff2244" : "#00ff88" }}>
                      {analysis.risk.requires_immediate_action ? "⚠ REQUIRED" : "✓ NOT REQUIRED"}
                    </div>
                  </div>
                </div>

                <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 12 }}>
                  RISK FLAGS — {analysis.risk.flags.length} DETECTED
                </div>

                {analysis.risk.flags.length === 0 && (
                  <div style={{ textAlign: "center", padding: "40px 0", color: "#1e2a3a" }}>
                    <div style={{ fontSize: 28, marginBottom: 12 }}>✓</div>
                    <div style={{ fontSize: 12 }}>No risk flags detected</div>
                  </div>
                )}

                {analysis.risk.flags.map((flag: any, i: number) => (
                  <div key={i} style={{ background: "#0d1117", borderRadius: 6, padding: 16, marginBottom: 12, borderLeft: `3px solid ${severityColor(flag.severity)}` }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                      <span style={{ fontSize: 13, color: "#e6edf3", fontWeight: 700, flex: 1, paddingRight: 12 }}>{flag.flag}</span>
                      <span style={{ fontSize: 9, padding: "3px 8px", borderRadius: 10, background: `${severityColor(flag.severity)}22`, color: severityColor(flag.severity), letterSpacing: 1, flexShrink: 0, fontWeight: 700 }}>
                        {flag.severity.toUpperCase()}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "#555", marginBottom: 8, lineHeight: 1.6 }}>{flag.reason}</div>
                    <div style={{ fontSize: 11, color: "#4488ff", marginBottom: 10, padding: "6px 10px", background: "#0044ff0a", borderRadius: 4 }}>
                      → {flag.action}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#2a2a3e", borderTop: "1px solid #1a1a2a", paddingTop: 8 }}>
                      <span>SOURCE: {flag.source?.replace("_", " ").toUpperCase()}</span>
                      <span>CONFIDENCE: {Math.round(flag.confidence * 100)}%</span>
                    </div>
                  </div>
                ))}

                {/* Analyzed at */}
                {analysis.risk.analyzed_at && (
                  <div style={{ fontSize: 10, color: "#1e2a3a", marginTop: 8, textAlign: "right" }}>
                    Analyzed: {new Date(analysis.risk.analyzed_at).toLocaleString()}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body, #root { background: #060910 !important; min-height: 100vh; }
  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }
  @keyframes wave { from { opacity: 0.3; transform: scaleY(0.6); } to { opacity: 1; transform: scaleY(1.2); } }
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  button:hover { opacity: 0.85; }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: #060910; }
  ::-webkit-scrollbar-thumb { background: #1e2a3a; border-radius: 2px; }
`}</style>
    </div>
  );
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div style={{ fontSize: 10, color: "#333", letterSpacing: 2, marginBottom: 8, marginTop: 20, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span>{title}</span>
      {count !== undefined && (
        <span style={{ color: count > 0 ? "#4488ff" : "#1e2a3a", background: count > 0 ? "#0044ff18" : "transparent", padding: "2px 8px", borderRadius: 10 }}>
          {count} FOUND
        </span>
      )}
    </div>
  );
}

function EntityCard({ primary, badges, confidence }: { primary: string; badges: { label: string; color: string }[]; confidence: number }) {
  const confidenceColor = (c: number) => c > 0.7 ? "#00ff88" : c > 0.4 ? "#ff9900" : "#ff4444";
  return (
    <div style={{ background: "#0d1117", borderRadius: 5, padding: "10px 12px", marginBottom: 7, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, color: "#e6edf3", marginBottom: 5 }}>{primary}</div>
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {badges.map((b, i) => (
            <span key={i} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 10, background: b.color || "#1e2a3a", color: "#888", letterSpacing: 1 }}>{b.label}</span>
          ))}
        </div>
      </div>
      <div style={{ textAlign: "right", marginLeft: 12 }}>
        <div style={{ fontSize: 12, color: confidenceColor(confidence), fontWeight: 700 }}>{Math.round(confidence * 100)}%</div>
        <div style={{ fontSize: 9, color: "#2a2a3e" }}>CONF</div>
      </div>
    </div>
  );
}

function NoneFound({ label = "None documented" }: { label?: string }) {
  return (
    <div style={{ fontSize: 11, color: "#2a2a3e", marginBottom: 8, padding: "8px 12px", background: "#0d1117", borderRadius: 4, fontStyle: "italic" }}>
      {label}
    </div>
  );
}