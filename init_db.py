# init_db.py
import sqlite3

DB = "database.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS qrcodes (
        qr_id TEXT PRIMARY KEY,
        assigned INTEGER DEFAULT 0,
        scans INTEGER DEFAULT 0
    );
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id TEXT UNIQUE,
        username TEXT UNIQUE,
        password TEXT,
        name TEXT,
        phone TEXT,
        email TEXT,
        birthdate TEXT,
        gender TEXT,
        blood_type TEXT,
        monthly_pills INTEGER DEFAULT 0,
        medications TEXT,
        chronic_diseases TEXT,
        lab_file TEXT,
        patient_photo TEXT,
        emergency_contact TEXT,
        other_info TEXT
    );
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS operators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    );
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id TEXT,
        visit_date TEXT,
        diagnosis TEXT,
        treatment TEXT,
        medicines TEXT,
        lab_file TEXT,
        created_by TEXT
    );
    ''')

    conn.commit()
    conn.close()
    print("✅ database.db initialized")

if __name__ == "__main__":
    init_db()
