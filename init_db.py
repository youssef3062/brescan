import sqlite3

DB = "database.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # QR codes table
    c.execute('''
    CREATE TABLE IF NOT EXISTS qrcodes (
        qr_id TEXT PRIMARY KEY,
        assigned INTEGER DEFAULT 0,
        scans INTEGER DEFAULT 0
    );
    ''')

    # Lab reports for visits
    c.execute('''
    CREATE TABLE IF NOT EXISTS lab_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visit_id INTEGER,
        file_name TEXT,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (visit_id) REFERENCES visits(id) ON DELETE CASCADE
    );
    ''')

    # Patients table
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

    # Operators table
    c.execute('''
    CREATE TABLE IF NOT EXISTS operators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    );
    ''')

    # Scans table
    c.execute('''
    CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id TEXT,
        scanned_by TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    # Registration labs table (NEW)
    c.execute('''
    CREATE TABLE IF NOT EXISTS registration_labs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        uploaded_by TEXT DEFAULT 'patient',
        FOREIGN KEY (qr_id) REFERENCES patients(qr_id) ON DELETE CASCADE
    );
    ''')

    # Visits table
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

    # Doctors table
    c.execute('''
    CREATE TABLE IF NOT EXISTS doctors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        specialty TEXT NOT NULL,
        phone TEXT NOT NULL,
        email TEXT NOT NULL,
        hospital TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    ''')

    conn.commit()
    conn.close()
    print("✅ database.db initialized successfully with registration_labs table!")

if __name__ == "__main__":
    init_db()
