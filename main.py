from fastapi import FastAPI, HTTPException, Form, WebSocket, WebSocketDisconnect
import threading
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from livecapture import start_live_capture
from database_config import connect_to_database
import asyncio

from broadcaster import manager, set_loop

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def create_campaign(name):
    connection = connect_to_database()
    cursor = connection.cursor()
    
    sql = "INSERT INTO campaign (timestamp, name, status) VALUES (DATETIME('now'), ?, 1)"
    cursor.execute(sql, (name,))
    
    campaign_id = cursor.lastrowid  # Mendapatkan ID campaign yang baru dibuat
    connection.commit()
    
    cursor.close()
    connection.close()
    
    return campaign_id

def update_campaign_status(campaign_id, new_status):
    connection = connect_to_database()
    cursor = connection.cursor()
    
    sql = "UPDATE campaign SET status = ? WHERE id = ?"
    cursor.execute(sql, (new_status, campaign_id))
    
    connection.commit()
    
    cursor.close()
    connection.close()

stop_event = threading.Event()
capture_thread = None

@app.post("/start-capture")
async def start_capture(
    campaign_name: str = Form(...)
):
    global capture_thread
    if capture_thread and capture_thread.is_alive():
        raise HTTPException(status_code=400, detail="Live capture is already running")
    
    stop_event.clear()
    campaign_id = create_campaign(campaign_name)
    
    capture_thread = threading.Thread(
        target=start_live_capture,
        args=(stop_event, campaign_id)
    )
    capture_thread.daemon = True
    capture_thread.start()
    
    return {
        "message": "Live capture started successfully",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name
    }

@app.get("/stop-capture/{campaign_id}")
async def stop_capture(campaign_id: int):
    global capture_thread
    update_campaign_status(campaign_id, 0)
    
    if not capture_thread or not capture_thread.is_alive():
        raise HTTPException(status_code=400, detail="Live capture is not running")
    
    try:
        stop_event.set()
        capture_thread.join(timeout=2) 
        capture_thread = None
        return {"message": "Live capture stopped successfully", "campaign_id": campaign_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping capture: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Anda mengirim: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    set_loop(asyncio.get_running_loop())


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
