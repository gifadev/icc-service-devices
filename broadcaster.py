import asyncio
import logging
from fastapi import WebSocket
from typing import List
import json
from data_queries import get_campaign_data_by_id

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

# 🔹 Manager untuk koneksi WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket baru terhubung: {websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket terputus: {websocket.client}")

    async def broadcast(self, message: str):
        if not self.active_connections:
            logger.warning("Tidak ada koneksi WebSocket aktif untuk broadcast.")
            return
        
        logger.info(f"Broadcast pesan ke {len(self.active_connections)} koneksi WebSocket.")
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
                logger.debug(f"Pesan dikirim ke {connection.client}")
            except Exception as e:
                logger.error(f"Error saat mengirim pesan ke {connection.client}: {e}")

manager = ConnectionManager()

# 🔹 Variabel global untuk debounce broadcast
fastapi_loop = None  # Akan di-set pada event startup
pending_update_count = 0
broadcast_delay = 5.0  # delay dalam detik
broadcast_scheduled = False
pending_campaign_id = None  # Untuk menyimpan campaign_id dari event yang terjadi

def set_loop(loop):
    global fastapi_loop
    fastapi_loop = loop
    logger.info("Event loop FastAPI telah disimpan untuk broadcasting.")

def schedule_update_broadcast(campaign_id):
    global pending_update_count, broadcast_scheduled, pending_campaign_id
    pending_update_count += 1
    pending_campaign_id = campaign_id  # Simpan campaign_id yang diterima
    # logger.info(f"Broadcast dijadwalkan untuk Campaign ID={campaign_id} dengan delay {broadcast_delay}s.")

    if not broadcast_scheduled and fastapi_loop is not None:
        broadcast_scheduled = True
        fastapi_loop.call_later(broadcast_delay, _perform_aggregated_broadcast)

def _perform_aggregated_broadcast():
    global pending_update_count, broadcast_scheduled, pending_campaign_id
    count = pending_update_count  
    pending_update_count = 0
    broadcast_scheduled = False

    try:
        # 🔹 Ambil data campaign terbaru
        data = get_campaign_data_by_id(pending_campaign_id)
        logger.info(f"Mengambil data untuk Campaign ID={pending_campaign_id}")

        if data is None:
            raise Exception("Campaign tidak ditemukan atau data kosong.")

        # Tambahkan informasi jumlah update
        data["update_count"] = count
        message = json.dumps(data)
        logger.info(f"Broadcast data campaign ID={pending_campaign_id} dengan update_count={count}")

    except Exception as e:
        message = json.dumps({"error": f"Gagal mengambil data campaign_id {pending_campaign_id}: {str(e)}"})
        logger.error(f"Gagal mengambil data untuk Campaign ID={pending_campaign_id}: {e}")

    # 🔹 Kirim broadcast ke WebSocket
    if fastapi_loop is not None:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), fastapi_loop)
    else:
        logger.error("FastAPI loop belum tersedia! Broadcast gagal.")
