# cleanup_icc.py

import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from database_config import connect_to_database

# Interval pengecekan dalam detik (misal 24 jam)
CHECK_INTERVAL = 24 * 3600

def cleanup():
    # hitung cutoff time: sekarang - 1 bulan
    cutoff = datetime.now() - relativedelta(months=1)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    conn = connect_to_database()
    if conn is None:
        print(f"[{datetime.now()}] Gagal koneksi ke database, skip cleanup")
        return

    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM campaign WHERE timestamp < ?",
            (cutoff_str,)
        )

        cur.execute(
            "DELETE FROM lte WHERE created_at < ?",
            (cutoff_str,)
        )
        
        cur.execute(
            "DELETE FROM gsm WHERE created_at < ?",
            (cutoff_str,)
        )

        conn.commit()
        print(f"[{datetime.now()}] Cleanup selesai. Menghapus semua record sebelum {cutoff_str}")
    except Exception as e:
        print(f"[{datetime.now()}] Error saat cleanup: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    while True:
        cleanup()
        time.sleep(CHECK_INTERVAL)
