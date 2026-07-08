import base64
import io
import cv2
import numpy as np
import qrcode
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
# Using OpenCV's built-in QR decoder (no system library needed)
import json
import uuid
import os

app = FastAPI()

# ---------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------
# Localhost and OnRender setup
# When deploying to OnRender, you might need to add your specific Render domain
# to the allow_origins list, or keep "*" for public access.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins for local testing. Update for production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# State Management
# ---------------------------------------------------------
# Slot states: "empty", "booked", "occupied"
slots = {
    1: {"status": "empty", "token": None},
    2: {"status": "empty", "token": None},
    3: {"status": "empty", "token": None},
}

# Active websocket connections for real-time frontend updates
active_connections: List[WebSocket] = []

async def broadcast_state():
    state_msg = json.dumps(slots)
    for connection in active_connections:
        try:
            await connection.send_text(state_msg)
        except Exception:
            pass

# ---------------------------------------------------------
# WebSockets
# ---------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    # Send initial state
    await websocket.send_text(json.dumps(slots))
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

# ---------------------------------------------------------
# Frontend Endpoints
# ---------------------------------------------------------
@app.get("/api/slots")
async def get_slots():
    return slots

class BookRequest(BaseModel):
    slot_id: int

@app.post("/api/book")
async def book_slot(req: BookRequest):
    slot_id = req.slot_id
    if slot_id not in slots:
        return {"error": "Invalid slot ID"}
    
    if slots[slot_id]["status"] != "empty":
        return {"error": "Slot is not empty"}
    
    # Generate unique token
    token = f"SLOT-{slot_id}-{uuid.uuid4().hex[:6]}"
    slots[slot_id]["status"] = "booked"
    slots[slot_id]["token"] = token
    
    # Generate QR Code image
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(token)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    
    # Notify all clients of state change
    await broadcast_state()
    
    return {"message": "Success", "qr_code": f"data:image/png;base64,{qr_base64}", "token": token}

# ---------------------------------------------------------
# ESP32-CAM Endpoints
# ---------------------------------------------------------
@app.post("/api/verify_qr")
async def verify_qr(image_file: UploadFile = File(...)):
    """
    ESP32 sends captured image here. We decode the QR code and
    tell the ESP32 which gate to open if valid.
    """
    try:
        # Read image
        contents = await image_file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return {"status": "error", "message": "Invalid image"}
        
        # Decode QR codes using OpenCV's built-in detector
        detector = cv2.QRCodeDetector()
        qr_data, _, _ = detector.detectAndDecode(img)
        
        if not qr_data:
            return {"status": "no_qr"}
        
        # Check if the scanned token matches any booked slot
        for slot_id, data in slots.items():
            if data["status"] == "booked" and data["token"] == qr_data:
                # Token matches! Set to occupied (car is entering)
                # The ESP32 will open the gate, and the IR sensor will monitor it.
                slots[slot_id]["status"] = "occupied"
                slots[slot_id]["token"] = None # Clear token so it can't be reused immediately
                
                await broadcast_state()
                return {"status": "success", "open_gate": slot_id}
                
        return {"status": "invalid_qr"}
    
    except Exception as e:
        return {"status": "error", "message": str(e)}

class IRUpdateRequest(BaseModel):
    slot_id: int
    is_empty: bool

@app.post("/api/update_ir")
async def update_ir(req: IRUpdateRequest):
    """
    ESP32 sends updates when IR sensor detects the car has left.
    """
    slot_id = req.slot_id
    if slot_id in slots:
        if req.is_empty:
            slots[slot_id]["status"] = "empty"
            slots[slot_id]["token"] = None
        else:
            slots[slot_id]["status"] = "occupied"
            
        await broadcast_state()
        return {"status": "success"}
    return {"status": "error"}

# ---------------------------------------------------------
# Serve Frontend Files
# ---------------------------------------------------------
# The frontend folder sits next to the backend folder in the repo
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# Serve CSS, JS, and other static assets from the frontend folder
app.mount("/", StaticFiles(directory=frontend_dir), name="frontend")

# ---------------------------------------------------------
# Run configuration
# ---------------------------------------------------------
# For local testing, you can run this script directly with `python main.py`
# For OnRender, Uvicorn is typically started via Render's start command:
# `uvicorn main:app --host 0.0.0.0 --port $PORT`
if __name__ == "__main__":
    import uvicorn
    # os.environ.get("PORT", 8000) handles Render's dynamic port assignment
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
