import sqlite3
import logging
from database_config import connect_to_database

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

def get_campaign_data_by_id(id_campaign):
    try:
        connection = connect_to_database()
        if connection is None:
            logger.error(f"Gagal menghubungkan ke database. Connection=None")
            return None

        # Atur row factory untuk mengakses kolom dengan nama
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        logger.info(f"Mengambil data untuk Campaign ID={id_campaign}")

        # 🔹 Ambil informasi campaign
        cursor.execute("SELECT id, name, status, timestamp FROM campaign WHERE id = ?", (id_campaign,))
        campaign = cursor.fetchone()

        if not campaign:
            logger.warning(f"Campaign ID={id_campaign} tidak ditemukan dalam database.")
            return None

        # 🔹 Ambil informasi device
        cursor.execute("SELECT * FROM device")
        device = cursor.fetchone()

        # 🔹 Ambil data GSM
        cursor.execute("SELECT * FROM gsm WHERE id_campaign = ?", (id_campaign,))
        gsm_data = cursor.fetchall()

        # 🔹 Ambil data LTE
        cursor.execute("SELECT * FROM lte WHERE id_campaign = ?", (id_campaign,))
        lte_data = cursor.fetchall()

        result = {
            "status": "success",
            "campaign": dict(campaign),
            "device": dict(device) if device else None,
            "gsm_data": [dict(row) for row in gsm_data],
            "lte_data": [dict(row) for row in lte_data]
        }

        logger.info(f"Data berhasil diambil untuk Campaign ID={id_campaign}")

        return result

    except Exception as e:
        logger.exception(f"Error saat mengambil data campaign ID={id_campaign}: {e}")
        return None
    finally:
        if connection:
            cursor.close()
            connection.close()
            logger.debug("Koneksi database ditutup.")
