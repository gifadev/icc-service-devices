import sqlite3
from database_config import connect_to_database

def get_campaign_data_by_id(id_campaign):
    try:
        connection = connect_to_database()
        if connection is None:
            return None
        
        # Atur row factory untuk mengakses kolom dengan nama
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        
        # Ambil informasi campaign
        cursor.execute("SELECT id, timestamp FROM campaign WHERE id = ?", (id_campaign,))
        
        campaign = cursor.fetchone()
        
        if not campaign:
            return None
        
        # Ambil informasi device
        cursor.execute("SELECT * FROM device")
        device = cursor.fetchone()
        
        # Ambil data GSM
        cursor.execute("SELECT * FROM gsm WHERE id_campaign = ?", (id_campaign,))
        gsm_data = cursor.fetchall()
        
        # Ambil data LTE
        cursor.execute("SELECT * FROM lte WHERE id_campaign = ?", (id_campaign,))
        lte_data = cursor.fetchall()
        
        # Jika diperlukan, konversi data menjadi dict
        return{
            "status": "success",
            "campaign": dict(campaign),
            "gsm_data": [dict(row) for row in gsm_data],
            "lte_data": [dict(row) for row in lte_data],
            "device": dict()
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        if connection:
            cursor.close()
            connection.close()
