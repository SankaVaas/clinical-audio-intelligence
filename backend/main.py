import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from audio.session import AudioSession
from nlp.extractor import extract_clinical_entities
from soap.generator import generate_soap_note
from risk.engine import RiskEngine

app = FastAPI(title="Clinical Audio Intelligence")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

session = AudioSession()
risk_engine = RiskEngine()
connected_clients: list[WebSocket] = []
last_analysis = {}

async def broadcast(message: dict):
    for ws in connected_clients:
        try:
            await ws.send_json(message)
        except:
            pass

@app.get("/health")
async def health():
    return {"status": "online", "service": "clinical-audio-intelligence"}

@app.post("/session/start")
async def start_session():
    if session.is_active:
        return {"status": "already_running"}
    asyncio.create_task(session.start(broadcast=broadcast))
    return {"status": "started"}

@app.post("/session/stop")
async def stop_session():
    session.stop()
    return {"status": "stopped", "segments": len(session.transcript)}

@app.get("/transcript")
async def get_transcript():
    return {
        "entries": session.get_transcript(),
        "full_text": session.get_full_text(),
        "is_active": session.is_active
    }

@app.post("/analyze")
async def analyze():
    """Run full clinical analysis on current transcript"""
    full_text = session.get_full_text()
    if not full_text.strip():
        return {"error": "No transcript available"}

    await broadcast({"type": "analysis_started"})

    # Run extraction + SOAP in parallel
    entities, soap = await asyncio.gather(
        extract_clinical_entities(full_text),
        generate_soap_note(full_text, {})
    )

    # Run risk analysis (sync, fast)
    risk = risk_engine.analyze(entities, full_text)

    # Re-generate SOAP with entities for better quality
    soap = await generate_soap_note(full_text, entities)

    global last_analysis
    last_analysis = {
        "entities": entities,
        "soap": soap,
        "risk": risk,
        "transcript_length": len(full_text.split()),
        "segments": len(session.transcript)
    }

    await broadcast({"type": "analysis_complete", **last_analysis})
    return last_analysis

@app.get("/analysis")
async def get_analysis():
    return last_analysis or {"error": "No analysis run yet. Call POST /analyze first."}

@app.get("/audit")
async def get_audit():
    return risk_engine.get_audit_log()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    for entry in session.transcript:
        await websocket.send_json({"type": "transcript_chunk", **entry})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)