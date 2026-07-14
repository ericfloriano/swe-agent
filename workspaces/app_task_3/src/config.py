import sqlite3

def create_table():
    conn = sqlite3.connect('activities.db')
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT, date TEXT)")
    conn.commit()
    conn.close()