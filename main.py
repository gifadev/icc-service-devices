import logging
from fastapi import FastAPI, HTTPException, Form, WebSocket, WebSocketDisconnect
import threading
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from livecapture2 import start_live_capture
from livecapture2 import global_cap
from database_config import connect_to_database
import asyncio
from broadcaster import manager, set_loop
import os
import sqlite3
from pathlib import Path
import time

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
stop_event = threading.Event()
capture_thread = None
capture_thread_lock = threading.Lock()
sync_thread: threading.Thread = None
sync_stop_event = threading.Event()


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

def delete_sqlite_db(db_filename: str):
    script_dir = Path(__file__).parent
    db_path = script_dir / db_filename

    # Pastikan koneksi SQLite ditutup sebelum menghapus
    try:
        # Coba buka dan langsung tutup koneksi jika file ada
        if db_path.is_file():
            conn = sqlite3.connect(db_path)
            conn.close()
    except sqlite3.Error as e:
        print(f"Peringatan: gagal menutup koneksi SQLite: {e}")

    if db_path.is_file():
        try:
            os.remove(db_path)
            print(f"Berhasil menghapus database: {db_path}")
        except PermissionError:
            print(f"Gagal: tidak ada izin menghapus {db_path}")
        except OSError as e:
            print(f"Gagal menghapus {db_path}: {e}")
    else:
        print(f"Tidak menemukan file database di: {db_path}")

def sync_rssi_updates(
    id_campaign: int,
    stop_evt: threading.Event,
    log_db_filename: str = "logs.db",
    icc_db_filename: str = "icc.db",
    poll_interval: float = 1.0
):
    base = Path(__file__).parent
    log_db_path = base / log_db_filename
    icc_db_path = base / icc_db_filename

    # 1) Tunggu sampai file DB muncul
    while not (log_db_path.is_file() and icc_db_path.is_file()):
        if stop_evt.is_set():
            return
        time.sleep(poll_interval)

    # 2) Coba koneksi berulang kali sampai berhasil atau stop_evt diset
    while not stop_evt.is_set():
        try:
            log_conn = sqlite3.connect(str(log_db_path), timeout=5.0)
            log_conn.row_factory = sqlite3.Row
            icc_conn = sqlite3.connect(str(icc_db_path), timeout=5.0)
            break
        except sqlite3.Error:
            time.sleep(poll_interval)
    else:
        return

    last_rssi = {}
    try:
        logger.info(f"Sync RSSI untuk campaign={id_campaign} dimulai.")
        while not stop_evt.is_set():
            # 3) Baca tabel log_table, retry bila tabel belum ada
            try:
                rows = log_conn.execute(
                    "SELECT type, arfcn, rssi FROM log_table"
                ).fetchall()
            except sqlite3.OperationalError:
                time.sleep(poll_interval)
                continue

            # 4) Update hanya jika nilai rssi berubah
            for row in rows:
                device_ty = row["type"].strip().lower()
                key = (device_ty, row["arfcn"])
                current = row["rssi"]
                if last_rssi.get(key) != current:
                    sql = (
                        f"UPDATE {device_ty} "
                        "SET rssi = ? "
                        "WHERE arfcn = ? AND id_campaign = ?"
                    )
                    icc_conn.execute(sql, (current, row["arfcn"], id_campaign))
                    icc_conn.commit()
                    logger.info(
                        f"[{device_ty.upper()}] campaign={id_campaign} "
                        f"arfcn={row['arfcn']} rssi {last_rssi.get(key)}→{current}"
                    )
                    last_rssi[key] = current

            time.sleep(poll_interval)
    finally:
        log_conn.close()
        icc_conn.close()
        logger.info("Sync RSSI loop berhenti.")


def update_campaign_status(campaign_id, new_status):
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


@app.post("/start-capture")
async def start_capture(
    campaign_id: int = Form(...),
    campaign_name: str = Form(...)
):
    global capture_thread, sync_thread, sync_stop_event

    with capture_thread_lock:
        # 1) Cek dan hentikan thread live capture lama jika masih hidup
        if capture_thread and capture_thread.is_alive():
            raise HTTPException(400, "Live capture sudah berjalan")

        # 2) Reset stop_event dan mulai live capture thread baru
        stop_event.clear()
        create_campaign(campaign_id, campaign_name)
        capture_thread = threading.Thread(
            target=start_live_capture,
            args=(stop_event, campaign_id),
            daemon=True
        )
        capture_thread.start()

        # 3) Hapus logs.db agar dibuat ulang
        delete_sqlite_db("logs.db")

        # 4) Stop sync thread lama jika ada
        if sync_thread and sync_thread.is_alive():
            sync_stop_event.set()
            sync_thread.join(timeout=5)

        # 5) Reset event dan start sync_rssi_updates thread baru
        sync_stop_event = threading.Event()
        sync_thread = threading.Thread(
            target=sync_rssi_updates,
            args=(campaign_id, sync_stop_event),
            daemon=True
        )
        sync_thread.start()

        logger.info(f"Live capture dan RSSI sync dimulai: campaign={campaign_id}")

    return {
        "message": "Live capture started successfully",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name
    }



# @app.get("/stop-capture/{campaign_id}")
# async def stop_capture(campaign_id: int):
#     global capture_thread, stop_event, global_cap
#     update_campaign_status(campaign_id, 0)
    
#     if capture_thread is None or not capture_thread.is_alive():
#         logger.warning(f"Percobaan menghentikan capture yang tidak berjalan. Campaign ID: {campaign_id}")
#         raise HTTPException(status_code=400, detail="Live capture is not running")

#     try:
#         # Set stop_event untuk memberi sinyal ke thread
#         stop_event.set()
        
#         # Jika global_cap masih ada, panggil close() untuk memaksa keluar dari blocking read
#         if global_cap is not None:
#             global_cap.close()
        
#         capture_thread.join(timeout=2)
        
#         if capture_thread.is_alive():
#             logger.error(f"Capture thread tidak berhasil dihentikan dengan benar. Campaign ID: {campaign_id}")
#             raise HTTPException(status_code=500, detail="Live capture thread did not terminate properly.")
        
#         capture_thread = None
#         stop_event.clear()

#         logger.info(f"Live capture dihentikan dengan sukses. Campaign ID={campaign_id}")
#         return {"message": "Live capture stopped successfully", "campaign_id": campaign_id}
    
#     except Exception as e:
#         logger.exception(f"Error saat menghentikan capture untuk Campaign ID {campaign_id}: {e}")
#         raise HTTPException(status_code=500, detail=f"Error stopping capture: {str(e)}")

@app.get("/stop-capture/{campaign_id}")
async def stop_capture(campaign_id: int):
    global capture_thread, stop_event, global_cap, sync_thread, sync_stop_event

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
    
    if sync_thread and sync_thread.is_alive():
        sync_stop_event.set()
        sync_thread.join(timeout=5)
    
    capture_thread = None
    sync_thread = None

    update_campaign_status(campaign_id, 0)
    return {"status": "Capture dihentikan", "campaign_id": campaign_id}


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
