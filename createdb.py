import sqlite3

def create_tables():
    # Membuat (atau membuka) database icc.db
    connection = sqlite3.connect("icc.db")
    cursor = connection.cursor()

    # Membuat tabel campaign 
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT ,
            status INTEGER ,
            timestamp DATETIME 
        );
    """)

    # Membuat tabel device 
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS device (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serial_number TEXT,
            ip TEXT,
            is_connected INTEGER
        );
    """)

    # Membuat tabel lte 
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lte (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            id_campaign                 INTEGER NOT NULL,
            mcc                         TEXT,
            mnc                         TEXT,
            operator                    TEXT,
            arfcn                       TEXT,
            cell_identity               TEXT,
            tracking_area_code          TEXT,
            frequency_band_indicator    TEXT,
            signal_level                TEXT,
            snr                         TEXT,
            rx_lev_min                  TEXT, 
            status                      INTEGER DEFAULT 1
        );
    """)

    # Membuat tabel gsm
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gsm (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            id_campaign       INTEGER,
            mcc               TEXT,
            mnc               TEXT,
            operator          TEXT,
            local_area_code   TEXT,
            arfcn             TEXT,
            cell_identity     TEXT,
            rxlev             TEXT,
            rxlev_access_min  TEXT,
            status            INTEGER DEFAULT 1
        );
    """)

    # Menyimpan perubahan
    connection.commit()

    # Menutup koneksi
    connection.close()

if __name__ == "__main__":
    create_tables()
    print("Tabel berhasil dibuat.")
