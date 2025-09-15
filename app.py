
import os
import io
import csv
import json
import sqlite3
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, send_from_directory, abort, Response, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------- CONFIG ----------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(APP_ROOT, "database.db")

STATIC_DIR = os.path.join(APP_ROOT, "static")
UPLOAD_FOLDER = os.path.join(STATIC_DIR, "labs")
PHOTO_FOLDER = os.path.join(STATIC_DIR, "photos")
QR_FOLDER = os.path.join(STATIC_DIR, "qrcodes")

ALLOWED_EXT = {"pdf"}
ALLOWED_PHOTO_EXT = {"jpg", "jpeg", "png", "gif"}

for p in (STATIC_DIR, UPLOAD_FOLDER, PHOTO_FOLDER, QR_FOLDER):
    os.makedirs(p, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = "BreScanStartupTeen20252ndI"

# Master key to create operators/doctors (used in Part 2/3)
MASTER_OPERATOR_KEY = "1234"

# ---------------- DB helpers ----------------
import sqlite3
from flask import g

DB_NAME = "database.db"

from flask import g

import sqlite3
from flask import g

DB = "database.db"

def get_db():
    conn = sqlite3.connect("database.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn



@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()



def ensure_schema():
    """
    Create/patch all tables safely (runs at startup).
    Uses a raw sqlite3 connection (no Flask g/context).
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # QR codes
    c.execute("""
        CREATE TABLE IF NOT EXISTS qrcodes (
            qr_id TEXT PRIMARY KEY,
            assigned INTEGER DEFAULT 0,
            scans INTEGER DEFAULT 0
        )
    """)

    # Patients
    c.execute("""
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
            other_info TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Operators
    c.execute("""
        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Doctors  ✅ مضاف فيها hospital + username UNIQUE
    c.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            specialty TEXT,
            phone TEXT,
            email TEXT,
            hospital TEXT,
            username TEXT UNIQUE,
            password TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Visits
    c.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_id TEXT,
            visit_date TEXT,
            diagnosis TEXT,
            treatment TEXT,
            medicines TEXT,
            lab_file TEXT,
            created_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe add of new columns if DB existed before
    def add_col(table, name, coldef):
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {coldef}")
        except sqlite3.OperationalError:
            pass

    add_col("qrcodes", "scans", "INTEGER DEFAULT 0")
    add_col("patients", "patient_photo", "TEXT")
    add_col("patients", "emergency_contact", "TEXT")
    add_col("patients", "other_info", "TEXT")
    add_col("visits", "created_by", "TEXT")
    add_col("doctors", "hospital", "TEXT")  # لو الجدول قديم

    conn.commit()
    conn.close()


ensure_schema() 



# ---------------- Analytics helpers (used in Part 2/3) ----------------
def get_analytics_data():
    conn = get_db()
    c = conn.cursor()

    # Basic counts
    c.execute("SELECT COUNT(*) as total FROM patients")
    total_patients = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) as total FROM visits")
    total_visits = c.fetchone()["total"]

    c.execute("SELECT SUM(scans) as total FROM qrcodes")
    total_scans = c.fetchone()["total"] or 0

    c.execute("SELECT COUNT(*) as total FROM operators")
    total_operators = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) as total FROM doctors")
    total_doctors = c.fetchone()["total"]

    # Recent activity (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) as recent FROM visits WHERE visit_date >= ?", (thirty_days_ago,))
    recent_visits = c.fetchone()["recent"]

    # Monthly trends
    c.execute("""
        SELECT strftime('%Y-%m', visit_date) as month, COUNT(*) as count
        FROM visits
        GROUP BY month
        ORDER BY month DESC
        LIMIT 6
    """)
    monthly_trends = [{"month": row["month"], "count": row["count"]} for row in c.fetchall()]

    # Top creators (operators + doctors)
    c.execute("""
        SELECT created_by, COUNT(*) as visit_count
        FROM visits
        WHERE created_by IS NOT NULL
        GROUP BY created_by
        ORDER BY visit_count DESC
        LIMIT 5
    """)
    top_creators = [{"creator": row["created_by"], "visits": row["visit_count"]} for row in c.fetchall()]

    # Patient demographics
    c.execute("SELECT gender, COUNT(*) as count FROM patients WHERE gender IS NOT NULL GROUP BY gender")
    gender_distribution = [{"gender": row["gender"], "count": row["count"]} for row in c.fetchall()]

    # Blood type distribution
    c.execute("SELECT blood_type, COUNT(*) as count FROM patients WHERE blood_type IS NOT NULL GROUP BY blood_type")
    blood_type_distribution = [{"type": row["blood_type"], "count": row["count"]} for row in c.fetchall()]

    # QR code usage
    c.execute("SELECT qr_id, scans FROM qrcodes WHERE scans > 0 ORDER BY scans DESC LIMIT 10")
    top_qr_codes = [{"qr_id": row["qr_id"], "scans": row["scans"]} for row in c.fetchall()]

    # Recent patients
    c.execute("""
        SELECT p.name, p.qr_id, p.phone, COUNT(v.id) as visit_count
        FROM patients p
        LEFT JOIN visits v ON p.qr_id = v.qr_id
        GROUP BY p.qr_id
        ORDER BY p.id DESC
        LIMIT 5
    """)
    recent_patients = [{"name": row["name"], "qr_id": row["qr_id"], "phone": row["phone"], "visits": row["visit_count"]} for row in c.fetchall()]

    conn.close()

    return {
        "total_patients": total_patients,
        "total_visits": total_visits,
        "total_scans": total_scans,
        "total_operators": total_operators,
        "total_doctors": total_doctors,
        "recent_visits": recent_visits,
        "monthly_trends": monthly_trends,
        "top_creators": top_creators,
        "gender_distribution": gender_distribution,
        "blood_type_distribution": blood_type_distribution,
        "top_qr_codes": top_qr_codes,
        "recent_patients": recent_patients
    }

# ---------------- utils ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def allowed_photo_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PHOTO_EXT

def calculate_age(birthdate_str):
    if not birthdate_str:
        return None
    try:
        b = datetime.strptime(birthdate_str, "%Y-%m-%d")
    except Exception:
        return None
    t = datetime.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))

def bump_scan(qr_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE qrcodes SET scans = COALESCE(scans,0) + 1 WHERE qr_id = ?", (qr_id,))
    conn.commit()
    conn.close()

# ---------------- Public & Patient Routes ----------------

@app.route("/")
def scanner_gate():
    # Landing page with camera/QR UI (template should show buttons: patient login, operator login, doctor login, manual)
    return render_template("scanner_gate.html")

@app.route("/access/<qr_id>")
def access(qr_id):
    """
    After scanning QR:
    - If QR not pre-seeded in qrcodes -> show 'not_registered' (404) with option to add by admin (form posts to /admin/add_qr in Part 3/3)
    - If QR exists:
        - increase scans
        - if patient exists -> guest view
        - else -> register
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT assigned FROM qrcodes WHERE qr_id = ?", (qr_id,))
    q = c.fetchone()
    if q:
        bump_scan(qr_id)
    conn.close()

    if not q:
        return render_template("not_registered.html", qr_id=qr_id), 404

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    conn.close()

    if patient:
        return redirect(url_for("guest_view", qr_id=qr_id))
    return redirect(url_for("register", qr_id=qr_id))

@app.route("/register/<qr_id>", methods=["GET", "POST"])
def register(qr_id):
    conn = get_db()
    c = conn.cursor()

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        name = request.form["name"]
        phone = request.form.get("phone")
        email = request.form.get("email")
        birthdate = request.form.get("birthdate")
        gender = request.form.get("gender")
        blood_type = request.form.get("blood_type")
        monthly_pills = request.form.get("monthly_pills")
        medications = request.form.get("medications")
        chronic_diseases = request.form.get("chronic_diseases")
        emergency_contact = request.form.get("emergency_contact")
        other_info = request.form.get("other_info")

        # Handle patient photo
        patient_photo = None
        if "patient_photo" in request.files:
            photo_file = request.files["patient_photo"]
            if photo_file and photo_file.filename:
                photo_filename = photo_file.filename
                photo_path = os.path.join("static/photos", photo_filename)
                photo_file.save(photo_path)
                patient_photo = photo_filename

        # Insert patient record
        c.execute("""
            INSERT INTO patients (
                qr_id, username, password, name, phone, email, birthdate, gender,
                blood_type, monthly_pills, medications, chronic_diseases,
                patient_photo, emergency_contact, other_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            qr_id, username, password, name, phone, email, birthdate, gender,
            blood_type, monthly_pills, medications, chronic_diseases,
            patient_photo, emergency_contact, other_info
        ))

        # Handle multiple lab uploads
        lab_files = request.files.getlist("registration_lab_files")
        for lab in lab_files:
            if lab and lab.filename:
                lab_filename = lab.filename
                lab_path = os.path.join("static/labs", lab_filename)
                lab.save(lab_path)

                c.execute("""
                    INSERT INTO registration_labs (qr_id, file_name, uploaded_by)
                    VALUES (?, ?, ?)
                """, (qr_id, lab_filename, "patient"))

        conn.commit()
        conn.close()
        flash("Patient registered successfully!", "success")
        return redirect(url_for("scanner_gate"))

    conn.close()
    return render_template("register.html", qr_id=qr_id)

@app.route("/guest/<qr_id>")
def guest_view(qr_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE qr_id=?", (qr_id,))
    patient = c.fetchone()
    conn.close()

    if not patient:
        return "Patient not found", 404

    # حساب العمر من تاريخ الميلاد لو موجود
    age = None
    if patient["birthdate"]:
        from datetime import datetime
        try:
            birth = datetime.strptime(patient["birthdate"], "%Y-%m-%d")
            today = datetime.today()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        except:
            age = None

    return render_template("guest_view.html", patient=patient, qr_id=qr_id, age=age)

@app.route('/login', methods=['GET', 'POST'])
@app.route('/login/<qr_id>', methods=['GET', 'POST'])
def login(qr_id=None):
    if request.method == 'POST':
        qr_id = qr_id or request.form.get('qr_id')
        username = request.form['username']
        password = request.form['password']

        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT * FROM patients 
                WHERE qr_id=? AND username=? AND password=?
            """, (qr_id, username, password))
            patient = c.fetchone()

        if patient:
            session['role'] = 'patient'
            session['patient_id'] = patient['id']
            session['patient_name'] = patient['name']
            session['qr_id'] = qr_id  # 👈 store qr_id in the session
            flash("Patient login successful!", "success")

            log_scan(qr_id, "patient")

            return redirect(url_for('dashboard', qr_id=qr_id))
        else:
            flash("Invalid credentials", "danger")

    return render_template('login.html', qr_id=qr_id)

def log_scan(qr_id, scanned_by):
    """Log when a QR is accessed by doctor or patient."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO scans (qr_id, scanned_by) VALUES (?, ?)", (qr_id, scanned_by))
        conn.commit()



@app.route("/dashboard/<qr_id>")
def dashboard(qr_id):
    """
    Patient full dashboard (restricted to same QR in session).
    """
    if session.get("role") != "patient" or session.get("qr_id") != qr_id:
        flash("Login as this patient to see full data.")
        return redirect(url_for("guest_view", qr_id=qr_id))

    conn = get_db()
    c = conn.cursor()

    # Patient record
    c.execute("SELECT * FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    if not patient:
        conn.close()
        flash("Patient not found.", "danger")
        return redirect(url_for("login"))

    # Visits
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()

    # Registration labs
    c.execute("SELECT * FROM registration_labs WHERE qr_id = ?", (qr_id,))
    registration_labs = c.fetchall()

    # Lab reports linked to visits
    visit_labs = {}
    for v in visits:
        c.execute("SELECT * FROM lab_reports WHERE visit_id = ?", (v["id"],))
        visit_labs[v["id"]] = c.fetchall()

    conn.close()

    # Age calculation
    age = calculate_age(patient["birthdate"])
    pills_total = patient["monthly_pills"] or 0
    pill_progress = min(100, pills_total * 3) if pills_total else 0

    return render_template(
        "dashboard.html",
        qr_id=qr_id,
        patient=patient,
        age=age,
        visits=visits,
        registration_labs=registration_labs,
        visit_labs=visit_labs,
        pill_progress=pill_progress
    )

@app.route("/timeline/<qr_id>")
def patient_timeline(qr_id):
    """
    Show a full visual timeline of a patient's visits and lab reports.
    """
    conn = get_db()
    c = conn.cursor()

    # Fetch patient info
    c.execute("SELECT * FROM patients WHERE qr_id=?", (qr_id,))
    patient = c.fetchone()
    if not patient:
        conn.close()
        return "Patient not found", 404

    # Fetch visits
    c.execute("SELECT * FROM visits WHERE qr_id=? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()

    # Fetch labs per visit
    visit_list = []
    for v in visits:
        c.execute("SELECT * FROM lab_reports WHERE visit_id=?", (v["id"],))
        labs = c.fetchall()
        visit_list.append({
            "id": v["id"],
            "date": v["visit_date"],
            "diagnosis": v["diagnosis"],
            "treatment": v["treatment"],
            "medicines": v["medicines"],
            "created_by": v["created_by"],
            "labs": labs
        })

    conn.close()
    return render_template("patient_timeline.html", patient=patient, visits=visit_list)

# Operator + Doctor flows


# ---------------- Operator flows ----------------

@app.route("/create_operator", methods=["GET", "POST"])
def create_operator():
    """
    Create operator using a master key (server-side protected form).
    """
    if request.method == "POST":
        key = request.form.get("master_key", "").strip()
        if key != MASTER_OPERATOR_KEY:
            flash("Invalid master key.")
            return render_template("create_operator.html")

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if not username or not password:
            flash("username and password are required.")
            return render_template("create_operator.html")

        hashed = generate_password_hash(password)
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO operators (username, password) VALUES (?, ?)", (username, hashed))
            conn.commit()
            flash("Operator created.")
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("username already exists.")
            conn.close()
            return render_template("create_operator.html")
        conn.close()
        return redirect(url_for("operator_login"))
    return render_template("create_operator.html")

@app.route("/operator_login", methods=["GET", "POST"])
def operator_login():
    """
    Operator login for full system access (all patients).
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM operators WHERE username = ?", (username,))
        op = c.fetchone()
        conn.close()

        if op and check_password_hash(op["password"], password):
            session.clear()
            session["role"] = "operator"
            session["username"] = username
            flash("Welcome operator.")
            return redirect(url_for("operator_dashboard"))

        flash("Invalid operator credentials.")
    return render_template("operator_login.html")

@app.route("/operator_dashboard")
def operator_dashboard():
    """
    Simple dashboard + search for operators.
    """
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))

    q = request.args.get("q", "").strip()
    conn = get_db()
    c = conn.cursor()
    if q:
        like = f"%{q}%"
        c.execute("""
            SELECT qr_id, name, phone, email, chronic_diseases
            FROM patients
            WHERE name LIKE ? OR qr_id LIKE ? OR phone LIKE ?
            ORDER BY name
        """, (like, like, like))
    else:
        c.execute("SELECT qr_id, name, phone, email, chronic_diseases FROM patients ORDER BY name")
    patients = c.fetchall()

    # quick analytics
    c.execute("SELECT COUNT(*) as total FROM patients")
    total_patients = c.fetchone()["total"]

    c.execute("SELECT SUM(scans) as total_scans FROM qrcodes")
    total_scans = c.fetchone()["total_scans"] or 0

    c.execute("SELECT COUNT(*) as visits_count FROM visits")
    total_visits = c.fetchone()["visits_count"]

    conn.close()
    return render_template(
        "operator_dashboard.html",
        patients=patients,
        q=q,
        total_patients=total_patients,
        total_scans=total_scans,
        total_visits=total_visits
    )

# ---------------- Analytics for operator ----------------

@app.route("/analytics")
def analytics_dashboard():
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))

    data = get_analytics_data()
    return render_template("analytics.html", data=data)

@app.route("/api/analytics")
def api_analytics():
    if session.get("role") != "operator":
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_analytics_data())

@app.route('/doctor/login/', methods=['GET', 'POST'])
@app.route('/doctor/login/<qr_id>', methods=['GET', 'POST'])
def doctor_login(qr_id):
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        doctor = conn.execute(
            "SELECT * FROM doctors WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if doctor:
            session['username'] = doctor['username']
            session['role'] = 'doctor'
            flash("Login successful!", "success")
            return redirect(url_for('doctor_dashboard', qr_id=qr_id))
        else:
            flash("Invalid username or password", "danger")

    return render_template('doctor_login.html', qr_id=qr_id)



# ---------------- Doctor flows ----------------

@app.route('/register_doctor', methods=['GET', 'POST'])
def register_doctor():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        full_name = request.form['full_name']
        specialty = request.form['specialty']
        phone = request.form['phone']
        email = request.form['email']
        hospital = request.form['hospital']

        c.execute('INSERT INTO doctors (full_name, specialty, phone, email, hospital) VALUES (?, ?, ?, ?, ?)',
                  (full_name, specialty, phone, email, hospital))
        conn.commit()
        flash("Doctor registered successfully!", "success")
        return redirect(url_for('scanner_gate'))

    return render_template("register_doctor.html")


@app.route("/doctor/dashboard/<qr_id>", methods=["GET", "POST"])
def doctor_dashboard(qr_id):
    if "username" not in session or session.get("role") != "doctor":
        flash("Please log in as a doctor.", "warning")
        return redirect(url_for("doctor_login", qr_id=qr_id))

    conn = get_db()
    c = conn.cursor()

    # Add Visit
    if request.method == "POST":
        visit_date = request.form.get("visit_date")
        diagnosis = request.form.get("diagnosis")
        treatment = request.form.get("treatment")

        c.execute("""
            INSERT INTO visits (qr_id, visit_date, diagnosis, treatment, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (qr_id, visit_date, diagnosis, treatment, session["username"]))
        visit_id = c.lastrowid

        files = request.files.getlist("lab_files")
        for file in files:
            if file and file.filename:
                filename = file.filename
                save_path = os.path.join("static/labs", filename)
                file.save(save_path)

                c.execute(
                    "INSERT INTO lab_reports (visit_id, file_name) VALUES (?, ?)",
                    (visit_id, filename)
                )

        conn.commit()
        flash("Visit and lab reports added successfully!", "success")
        return redirect(url_for("doctor_dashboard", qr_id=qr_id))

    # Doctor info
    doctor = c.execute(
        "SELECT * FROM doctors WHERE username=?", (session["username"],)
    ).fetchone()

    # Patient info
    patient = c.execute(
        "SELECT * FROM patients WHERE qr_id=?", (qr_id,)
    ).fetchone()

    if not patient:
        flash("Patient not found.", "danger")
        conn.close()
        return redirect(url_for("scanner_gate"))

    # Registration labs
    registration_labs = c.execute(
        "SELECT * FROM registration_labs WHERE qr_id=?", (qr_id,)
    ).fetchall()

    # Visits + attached lab reports
    visits = c.execute(
        "SELECT * FROM visits WHERE qr_id=? ORDER BY visit_date DESC", (qr_id,)
    ).fetchall()

    visit_list = []
    for visit in visits:
        visit = dict(visit)
        labs = c.execute(
            "SELECT * FROM lab_reports WHERE visit_id=?", (visit["id"],)
        ).fetchall()
        visit["lab_reports"] = [dict(l) for l in labs]
        visit_list.append(visit)

    conn.close()

    return render_template(
        "doctor_dashboard.html",
        doctor=doctor,
        patient=patient,
        registration_labs=[dict(l) for l in registration_labs],
        visits=visit_list,
        qr_id=qr_id
    )


@app.route("/patient_visits/<qr_id>")
def patient_visits(qr_id):
    """
    Operator: can view any patient's visits.
    Doctor: only the allowed QR.
    """
    role = session.get("role")
    if role == "operator":
        pass
    elif role == "doctor":
        if session.get("allowed_qr") != qr_id:
            flash("Not authorized for this QR.")
            return redirect(url_for("doctor_login", qr_id=qr_id))
    else:
        flash("Login required.")
        return redirect(url_for("scanner_gate"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()
    c.execute("SELECT name FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    conn.close()

    if not patient:
        flash("Patient not found.")
        if role == "operator":
            return redirect(url_for("operator_dashboard"))
        else:
            return redirect(url_for("doctor_dashboard", qr_id=session.get("allowed_qr", "")))

    # render a generic view; template can show creator and files
    return render_template("patient_visits.html", qr_id=qr_id, patient=patient, visits=visits)

# ---------------- Shared: add visit (operator/doctor) ----------------


@app.route("/add_visit/<qr_id>", methods=["GET", "POST"])
def add_visit(qr_id):
    """
    Operator: can add visits to any QR.
    Doctor: can add visits only to the allowed QR.
    """
    role = session.get("role")
    if role == "operator":
        pass
    elif role == "doctor":
        if session.get("allowed_qr") != qr_id:
            flash("Doctor can only add visit for the scanned QR.")
            return redirect(url_for("doctor_login", qr_id=qr_id))
    else:
        flash("Operator or Doctor login required.")
        return redirect(url_for("scanner_gate"))

    # ensure patient exists
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    if not patient:
        conn.close()
        flash("Patient not found.")
        if role == "operator":
            return redirect(url_for("operator_dashboard"))
        return redirect(url_for("doctor_dashboard", qr_id=session.get("allowed_qr", "")))

    if request.method == "POST":
        visit_date = request.form.get("visit_date") or datetime.now().strftime("%Y-%m-%d")
        diagnosis = request.form.get("diagnosis", "").strip()
        treatment = request.form.get("treatment", "").strip()
        medicines = request.form.get("medicines", "").strip()

        # optional lab attachment
        lab = request.files.get("lab_file")
        lab_filename = None
        if lab and lab.filename:
            safe = secure_filename(lab.filename)
            if allowed_file(safe):
                lab_filename = f"{qr_id}__{safe}"
                lab.save(os.path.join(app.config["UPLOAD_FOLDER"], lab_filename))
            else:
                flash("Only PDF allowed for labs.")
                conn.close()
                return redirect(url_for("add_visit", qr_id=qr_id))

        creator = session.get("username", "")
        if role == "doctor":
            created_by = f"dr:{creator}"
        else:
            created_by = f"op:{creator}"

        c.execute("""
            INSERT INTO visits (qr_id, visit_date, diagnosis, treatment, medicines, lab_file, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (qr_id, visit_date, diagnosis, treatment, medicines, lab_filename, created_by))
        conn.commit()
        conn.close()

        flash("Visit added.")
        # redirect according to role
        if role == "operator":
            return redirect(url_for("patient_visits", qr_id=qr_id))
        return redirect(url_for("doctor_dashboard", qr_id=qr_id))

    conn.close()
    # Render shared form
    return render_template("add_visit.html", qr_id=qr_id, patient=patient)
# ---------------- Operator-only: edit patient core fields ----------------
@app.route("/doctor/patient/<qr_id>")
def doctor_patient_view(qr_id):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM patients WHERE qr_id=?", (qr_id,))
    patient = c.fetchone()

    c.execute("SELECT * FROM visits WHERE qr_id=? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()

    # هات كل التحاليل
    visit_ids = [v["id"] for v in visits]
    labs = {}
    if visit_ids:
        q_marks = ",".join("?" * len(visit_ids))
        c.execute(f"SELECT * FROM lab_reports WHERE visit_id IN ({q_marks})", visit_ids)
        for lab in c.fetchall():
            labs.setdefault(lab["visit_id"], []).append(lab)

    conn.close()

    return render_template("doctor_patient_view.html", patient=patient, visits=visits, labs=labs, qr_id=qr_id)



@app.route('/doctor_register', methods=['GET', 'POST'])
def doctor_register():
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        specialty = request.form['specialty'].strip()
        phone = request.form['phone'].strip()
        email = request.form['email'].strip()
        hospital = request.form['hospital'].strip()
        username = request.form['username'].strip()
        password = request.form['password'].strip()  # لاحقًا نعمل hashing

        if not all([full_name, specialty, phone, email, hospital, username, password]):
            flash("All fields are required.", "warning")
            return redirect(url_for('doctor_register'))

        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO doctors (full_name, specialty, phone, email, hospital, username, password)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (full_name, specialty, phone, email, hospital, username, password))
                conn.commit()
            flash("Doctor registered successfully!", "success")
            return redirect(url_for('doctor_login'))

        except sqlite3.IntegrityError:
            flash("⚠️ Username already exists. Please choose another.", "danger")
            return redirect(url_for('doctor_register'))
        except sqlite3.OperationalError:
            flash("⚠️ Database is busy. Please try again.", "danger")
            return redirect(url_for('doctor_register'))

    return render_template('doctor_register.html')



    return render_template('doctor_login.html')
@app.route("/operator_edit/<qr_id>", methods=["GET", "POST"])
def operator_edit(qr_id):
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    if not patient:
        conn.close()
        flash("Patient not found.")
        return redirect(url_for("operator_dashboard"))

    if request.method == "POST":
        chronic = request.form.get("chronic_diseases", "").strip()
        meds = request.form.get("medications", "").strip()
        emergency = request.form.get("emergency_contact", "").strip()
        other = request.form.get("other_info", "").strip()

        # optional lab update
        lab = request.files.get("lab_file")
        if lab and lab.filename:
            safe = secure_filename(lab.filename)
            if allowed_file(safe):
                lab_filename = f"{qr_id}__{safe}"
                lab.save(os.path.join(app.config["UPLOAD_FOLDER"], lab_filename))
                c.execute("UPDATE patients SET lab_file = ? WHERE qr_id = ?", (lab_filename, qr_id))
            else:
                flash("Only PDF labs allowed.")
                conn.close()
                return redirect(url_for("operator_edit", qr_id=qr_id))

        # optional photo update
        photo = request.files.get("patient_photo")
        if photo and photo.filename:
            safe = secure_filename(photo.filename)
            if allowed_photo_file(safe):
                photo_filename = f"{qr_id}__{safe}"
                photo.save(os.path.join(PHOTO_FOLDER, photo_filename))
                c.execute("UPDATE patients SET patient_photo = ? WHERE qr_id = ?", (photo_filename, qr_id))
            else:
                flash("Only JPG, PNG, GIF allowed for photo uploads.")
                conn.close()
                return redirect(url_for("operator_edit", qr_id=qr_id))

        c.execute("""
            UPDATE patients
            SET chronic_diseases = ?, medications = ?, emergency_contact = ?, other_info = ?
            WHERE qr_id = ?
        """, (chronic, meds, emergency, other, qr_id))
        conn.commit()
        conn.close()

        flash("Patient updated.")
        return redirect(url_for("operator_dashboard"))

    conn.close()
    return render_template("operator_edit.html", patient=patient)
@app.route("/export_visits/<qr_id>")
def export_visits(qr_id):
    role = session.get("role")
    if role not in ("operator", "doctor"):
        flash("Operator or Doctor required.")
        return redirect(url_for("scanner_gate"))

    # doctor limited to allowed qr
    if role == "doctor" and session.get("allowed_qr") != qr_id:
        flash("Doctor not authorized for this QR.")
        return redirect(url_for("doctor_login", qr_id=qr_id))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    rows = c.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["visit_date", "diagnosis", "treatment", "medicines", "lab_file", "created_by"])
    for r in rows:
        cw.writerow([r["visit_date"], r["diagnosis"], r["treatment"], r["medicines"], r["lab_file"], r["created_by"]])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={qr_id}_visits.csv"}
    )

# ---------------- Serve labs ----------------
@app.route("/labs/<filename>")
def labs(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------------- Serve patient photos ----------------
@app.route("/photos/<filename>")
def photos(filename):
    return send_from_directory(PHOTO_FOLDER, filename)

# ---------------- Admin add QR ----------------
@app.route("/admin/add_qr", methods=["POST"])
def admin_add_qr():
    qr_id = request.form.get("qr_id", "").strip()
    if not qr_id:
        flash("No QR specified.")
        return redirect(url_for("scanner_gate"))

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO qrcodes (qr_id, assigned, scans) VALUES (?, 0, 0)", (qr_id,))
    conn.commit()
    conn.close()
    flash("QR added.")
    return redirect(url_for("scanner_gate"))

# ---------------- Logout ----------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("scanner_gate"))
    

# ---------------- Run ----------------
iimport os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # default to 8080
    app.run(host="0.0.0.0", port=port)

