import sqlite3

def connect_to_database():
    try:
        connection = sqlite3.connect("icc.db")
        return connection
    except sqlite3.Error as e:
        print(f"Error connecting to SQLite Database: {e}")
        return None