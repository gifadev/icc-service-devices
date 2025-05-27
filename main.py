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

    if not capture_thread or not capture_thread.is_alive():
        return {"status": "Tidak ada capture yang berjalan"}

    stop_event.set()  # Kirim sinyal untuk menghentikan loop capture
    
    # Jika ada global_cap, tutup capture untuk memaksa keluar dari loop
    if global_cap:
        try:
            global_cap.close()
            logger.info("Pyshark capture berhasil ditutup.")
        except Exception as e:
            logger.error(f"Error saat menutup global_cap: {e}")

    # Tunggu thread berhenti dengan timeout agar API tetap responsif
    capture_thread.join(timeout=5)

    if capture_thread.is_alive():
        logger.warning("Thread masih berjalan! Memaksa penghentian...")
        capture_thread = None  # Hapus referensi ke thread agar bisa dibuat ulang
        return {
           "status": "Capture dihentikan", "campaign_id": campaign_id,
        }

    update_campaign_status(campaign_id, 0)
    return {"status": "Capture dihentikan", "campaign_id": campaign_id}

@app.post("/add-device/")
async def add_device(
    serial_number: str = Form(...),
    ip: str = Form(...),
    is_connected: int = Form(0)
):
    """Menambahkan satu device via form data"""
    connection = None
    cursor = None
    try:
        connection = connect_to_database()
        cursor = connection.cursor()
        
        cursor.execute(
            "INSERT INTO device (serial_number, ip, is_connected) VALUES (?, ?, ?)",
            (serial_number, ip, is_connected)
        )
        
        connection.commit()
        device_id = cursor.lastrowid
        
        logger.info(f"Device ditambahkan - ID: {device_id}, SN: {serial_number}")
        
        return {
            "message": "Device added successfully",
            "device_id": device_id,
            "serial_number": serial_number
        }
        
    except Exception as e:
        logger.error(f"Error saat menambahkan device: {e}")
        raise HTTPException(
            status_code=500,
            detail="Gagal menambahkan device"
        )
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.get("/get-device}")
async def get_device():
    """Ambil satu device via ID"""
    connection = None
    cursor = None
    try:
        connection = connect_to_database()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT id, serial_number, ip, is_connected FROM device"
        )
        row = cursor.fetchone()

        if not row:
            # ID tidak ditemukan
            raise HTTPException(
                status_code=404,
                detail=f"Device dengan  tidak ada"
            )

        # mapping hasil query ke dict
        device = {
            "id": row[0],
            "serial_number": row[1],
            "ip": row[2],
            "is_connected": row[3],
        }

        return {"device": device}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat mengambil device: {e}")
        raise HTTPException(
            status_code=500,
            detail="Gagal mengambil data device"
        )
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


@app.put("/update-device/{device_id}")
async def update_device(
    device_id: int,
    ip:str = Form(None),
    is_connected: int = Form(None),
):

    connection = None
    cursor = None
    try:
        connection = connect_to_database()
        cursor = connection.cursor()

        updates = []
        params = []
        if ip is not None:
            updates.append("ip = ?")
            params.append(ip)
        if is_connected is not None:
            updates.append("is_connected = ?")
            params.append(is_connected)

        if not updates:
            raise HTTPException(
                status_code=400,
                detail="Tidak ada field yang di-update"
            )

        # tambahkan serial_number ke params untuk WHERE
        params.append(device_id)
        sql = f"""
            UPDATE device
            SET {', '.join(updates)}
            WHERE id = ?
        """
        cursor.execute(sql, params)
        connection.commit()

        if cursor.rowcount == 0:
            # kalau tidak ada baris yang berubah, serial_number tidak ditemukan
            raise HTTPException(
                status_code=404,
                detail="Device dengan serial_number tersebut tidak ada"
            )

        logger.info(f"Device di-update - ID: {device_id}, fields: {updates}")
        return {"message": "Device updated successfully"}

    except HTTPException:
        # lempar ulang HTTPException yang sudah kita bangun
        raise
    except Exception as e:
        logger.error(f"Error saat update device: {e}")
        raise HTTPException(
            status_code=500,
            detail="Gagal meng-update device"
        )
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

@app.delete("/delete-device/{device_id}")
async def delete_device(
    device_id: int
):
    """Hapus satu device via ID"""
    connection = None
    cursor = None
    try:
        connection = connect_to_database()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM device WHERE id = ?",
            (device_id,)
        )
        connection.commit()

        if cursor.rowcount == 0:
            # tidak ada baris yang terhapus → ID tidak ditemukan
            raise HTTPException(
                status_code=404,
                detail=f"Device dengan ID {device_id} tidak ada"
            )

        logger.info(f"Device dihapus - ID: {device_id}")
        return {"message": f"Device ID {device_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saat menghapus device: {e}")
        raise HTTPException(
            status_code=500,
            detail="Gagal menghapus device"
        )
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()

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
