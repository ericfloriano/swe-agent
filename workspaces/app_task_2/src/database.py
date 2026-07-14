import sqlite3

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('activities.db')
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT
            )
        ''')
        self.conn.commit()

    def add_activity(self, activity):
        cursor = self.conn.cursor()
        cursor.execute('INSERT INTO activities (name, description) VALUES (?, ?)', (activity.name, activity.description))
        self.conn.commit()
        activity.id = cursor.lastrowid

    def get_all_activities(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM activities')
        return [Activity(row[1], row[2]) for row in cursor.fetchall()]