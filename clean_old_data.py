from database_config import connect_to_database

def clean_old_data():
    conn = connect_to_database()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM lte WHERE created_at <= date('now', '-1 month')")
    cursor.execute("DELETE FROM gsm WHERE created_at <= date('now', '-1 month')")

    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    clean_old_data()                                                                                                              