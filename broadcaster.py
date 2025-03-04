import asyncio
from fastapi import WebSocket
from typing import List
import json
from data_queries import get_campaign_data_by_id

# Manager untuk koneksi WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# Variabel global untuk debounce broadcast
fastapi_loop = None  # Akan di-set pada event startup
pending_update_count = 0
broadcast_delay = 1.0  # delay dalam detik
broadcast_scheduled = False
pending_campaign_id = None  # Untuk menyimpan campaign_id dari event yang terjadi

def set_loop(loop):
    global fastapi_loop
    fastapi_loop = loop

def schedule_update_broadcast(campaign_id):
    global pending_update_count, broadcast_scheduled, pending_campaign_id
    pending_update_count += 1
    # Simpan campaign_id yang diterima (asumsi satu campaign aktif)
    pending_campaign_id = campaign_id  
    # Jika belum ada broadcast terjadwal, jadwalkan satu broadcast setelah delay
    if not broadcast_scheduled and fastapi_loop is not None:
        broadcast_scheduled = True
        fastapi_loop.call_later(broadcast_delay, _perform_aggregated_broadcast)

def _perform_aggregated_broadcast():
    global pending_update_count, broadcast_scheduled, pending_campaign_id
    count = pending_update_count  
    pending_update_count = 0
    broadcast_scheduled = False

    # Memanggil function dari data_queries.py untuk mendapatkan data terbaru
    try:
        data = get_campaign_data_by_id(pending_campaign_id)
        print("ini data", data)
        if data is None:
            raise Exception("Campaign tidak ditemukan atau data kosong.")
        # Jika perlu, tambahkan jumlah perubahan pada data atau buat ringkasan tambahan
        data["update_count"] = count
        # Serialize data ke JSON
        message = json.dumps(data)
    except Exception as e:
        message = json.dumps({"error": f"Gagal mengambil data dari campaign_id {pending_campaign_id}  : {str(e)}"})
    
    # Kirim broadcast secara thread-safe ke event loop FastAPI
    if fastapi_loop is not None:
        asyncio.run_coroutine_threadsafe(manager.broadcast(message), fastapi_loop)
    else:
        print("FastAPI loop belum tersedia!")
