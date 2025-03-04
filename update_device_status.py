import json
import time
from database_config import connect_to_database

def update_device_status():
    try:
        with open("pancashiki.json", "r") as file:
            data = json.load(file)
        status_value = 1 if data.get("is_samsung_connected", False) else 0

        connection = connect_to_database()
        if connection is None:
            print("Error connecting to the database")
            return

        cursor = connection.cursor()
        update_query = "UPDATE device SET is_connected = ?"
        cursor.execute(update_query, (status_value,))
        connection.commit()

        print(f"Device status updated to: {status_value}")
    except Exception as e:
        print("Error:", e)
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            connection.close()
        except Exception:
            pass

if __name__ == "__main__":
    while True:
        update_device_status()
        time.sleep(3)  
