import logging
from fastapi import FastAPI, HTTPException, Form, WebSocket, WebSocketDisconnect
import threading
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from livecapture import start_live_capture
from livecapture import global_cap
from database_config import connect_to_database
import asyncio
from broadcaster import manager, set_loop

# 🔹 Konfigurasi Logging
logging.basicConfig(
    level=logging.INFO,  
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("icc.log"),  
        logging.StreamHandler()  
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def create_campaign(id_campaign, name):
    """Membuat campaign baru di database."""
    try:
        connection = connect_to_database()
        cursor = connection.cursor()
        
        sql = "INSERT INTO campaign (id, timestamp, name, status) VALUES (?, DATETIME('now'), ?, 1)"
        cursor.execute(sql, (id_campaign, name))
        connection.commit()

        logger.info(f"Campaign berhasil dibuat: ID={id_campaign}, Name={name}")

    except Exception as e:
        logger.error(f"Error saat membuat campaign: {e}")
        raise HTTPException(status_code=500, detail="Gagal membuat campaign.")
    finally:
        cursor.close()
        connection.close()

def update_campaign_status(campaign_id, new_status):
    """Memperbarui status campaign di database."""
    try:
        connection = connect_to_database()
        cursor = connection.cursor()
        
        sql = "UPDATE campaign SET status = ? WHERE id = ?"
        cursor.execute(sql, (new_status, campaign_id))
        connection.commit()

        logger.info(f"Campaign ID={campaign_id} status diperbarui menjadi {new_status}")

    except Exception as e:
        logger.error(f"Error saat memperbarui status campaign: {e}")
        raise HTTPException(status_code=500, detail="Gagal memperbarui status campaign.")
    finally:
        cursor.close()
        connection.close()

stop_event = threading.Event()
capture_thread = None
capture_thread_lock = threading.Lock()

@app.post("/start-capture")
async def start_capture(
    campaign_id: int = Form(),
    campaign_name: str = Form()
):
    """Memulai live capture dengan campaign tertentu."""
    global capture_thread
    with capture_thread_lock: 
        if capture_thread and capture_thread.is_alive():
            logger.warning(f"Percobaan memulai capture saat sudah berjalan. Campaign ID: {campaign_id}")
            raise HTTPException(status_code=400, detail="Live capture is already running")

        stop_event.clear()
        create_campaign(campaign_id, campaign_name)

        capture_thread = threading.Thread(
            target=start_live_capture,
            args=(stop_event, campaign_id)
        )
        capture_thread.daemon = True
        capture_thread.start()

        logger.info(f"Live capture dimulai: Campaign ID={campaign_id}, Name={campaign_name}")

    return {
        "message": "Live capture started successfully",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name
    }

@app.get("/stop-capture/{campaign_id}")
async def stop_capture(campaign_id: int):
    global capture_thread, stop_event, global_cap
    update_campaign_status(campaign_id, 0)
    
    if capture_thread is None or not capture_thread.is_alive():
        logger.warning(f"Percobaan menghentikan capture yang tidak berjalan. Campaign ID: {campaign_id}")
        raise HTTPException(status_code=400, detail="Live capture is not running")

    try:
        # Set stop_event untuk memberi sinyal ke thread
        stop_event.set()
        
        # Jika global_cap masih ada, panggil close() untuk memaksa keluar dari blocking read
        if global_cap is not None:
            global_cap.close()
        
        capture_thread.join(timeout=2)
        
        if capture_thread.is_alive():
            logger.error(f"Capture thread tidak berhasil dihentikan dengan benar. Campaign ID: {campaign_id}")
            raise HTTPException(status_code=500, detail="Live capture thread did not terminate properly.")
        
        capture_thread = None
        stop_event.clear()

        logger.info(f"Live capture dihentikan dengan sukses. Campaign ID={campaign_id}")
        return {"message": "Live capture stopped successfully", "campaign_id": campaign_id}
    
    except Exception as e:
        logger.exception(f"Error saat menghentikan capture untuk Campaign ID {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping capture: {str(e)}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Menangani koneksi WebSocket."""
    await manager.connect(websocket)
    logger.info(f"WebSocket baru terhubung: {websocket.client}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Pesan WebSocket diterima: {data}")
            await websocket.send_text(f"Anda mengirim: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket terputus: {websocket.client}")
    except Exception as e:
        logger.exception(f"Error WebSocket: {e}")

@app.on_event("startup")
async def startup_event():
    """Event yang dijalankan saat aplikasi FastAPI mulai."""
    try:
        set_loop(asyncio.get_running_loop())
        logger.info("Aplikasi FastAPI berhasil dimulai.")
    except RuntimeError:
        logger.error("Gagal mendapatkan event loop yang sedang berjalan.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
