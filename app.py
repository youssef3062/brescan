
import os
from flask import (Flask, render_template, request, redirect, url_for, session,
                   flash, send_from_directory, abort, Response, jsonify)
import sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import io
import csv
import pandas as pd
import json

# ---------------- CONFIG ----------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(APP_ROOT, "database.db")
UPLOAD_FOLDER = os.path.join(APP_ROOT, "static", "labs")
PHOTO_FOLDER = os.path.join(APP_ROOT, "static", "photos")
QR_FOLDER = os.path.join(APP_ROOT, "static", "qrcodes")
ALLOWED_EXT = {"pdf"}
ALLOWED_PHOTO_EXT = {"jpg", "jpeg", "png", "gif"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PHOTO_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = "dev-super-secret-change-me"

MASTER_OPERATOR_KEY = "1234"   # per your request

# ---------------- DB helpers ----------------
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- Analytics helpers ----------------
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
    
    # Top operators
    c.execute("""
        SELECT created_by, COUNT(*) as visit_count 
        FROM visits 
        WHERE created_by IS NOT NULL 
        GROUP BY created_by 
        ORDER BY visit_count DESC 
        LIMIT 5
    """)
    top_operators = [{"operator": row["created_by"], "visits": row["visit_count"]} for row in c.fetchall()]
    
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
        "recent_visits": recent_visits,
        "monthly_trends": monthly_trends,
        "top_operators": top_operators,
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
    except:
        return None
    t = datetime.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))

# ---------------- Routes ----------------

@app.route("/")
def scanner_gate():
    return render_template("scanner_gate.html")

@app.route("/access/<qr_id>")
def access(qr_id):
    # increment scan counter
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT assigned FROM qrcodes WHERE qr_id = ?", (qr_id,))
    q = c.fetchone()
    if q:
        # increment scans
        c.execute("UPDATE qrcodes SET scans = scans + 1 WHERE qr_id = ?", (qr_id,))
        conn.commit()
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

# Registration
@app.route("/register/<qr_id>", methods=["GET","POST"])
def register(qr_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT assigned FROM qrcodes WHERE qr_id = ?", (qr_id,))
    q = c.fetchone()
    if not q:
        conn.close()
        return "QR not in system. Admin add first.", 404
    if q["assigned"] == 1:
        conn.close()
        return redirect(url_for("guest_view", qr_id=qr_id))

    if request.method == "POST":
        f = request.form
        username = f.get("username","").strip()
        password = f.get("password","").strip()
        name = f.get("name","").strip()
        phone = f.get("phone","").strip()
        email = f.get("email","").strip()
        birthdate = f.get("birthdate","").strip()
        gender = f.get("gender","").strip()
        blood_type = f.get("blood_type","").strip()
        monthly_pills = int(f.get("monthly_pills") or 0)
        medications = f.get("medications","").strip()
        chronic = f.get("chronic_diseases","").strip()
        emergency = f.get("emergency_contact","").strip()
        other = f.get("other_info","").strip()

        if not username or not password or not name:
            flash("username, password and full name required")
            return render_template("register.html", qr_id=qr_id)

        lab_file = request.files.get("lab_file")
        lab_filename = None
        if lab_file and lab_file.filename:
            safe = secure_filename(lab_file.filename)
            if allowed_file(safe):
                lab_filename = f"{qr_id}__{safe}"
                lab_file.save(os.path.join(app.config["UPLOAD_FOLDER"], lab_filename))
            else:
                flash("Only PDF allowed for lab uploads.")
                return render_template("register.html", qr_id=qr_id)

        patient_photo = request.files.get("patient_photo")
        photo_filename = None
        if patient_photo and patient_photo.filename:
            safe = secure_filename(patient_photo.filename)
            if allowed_photo_file(safe):
                photo_filename = f"{qr_id}__{safe}"
                patient_photo.save(os.path.join(PHOTO_FOLDER, photo_filename))
            else:
                flash("Only JPG, PNG, GIF allowed for photo uploads.")
                return render_template("register.html", qr_id=qr_id)

        hashed = generate_password_hash(password)
        try:
            c.execute("""
                INSERT INTO patients (qr_id, username, password, name, phone, email, birthdate, gender,
                blood_type, monthly_pills, medications, chronic_diseases, lab_file, patient_photo, emergency_contact, other_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (qr_id, username, hashed, name, phone, email, birthdate, gender,
                 blood_type, monthly_pills, medications, chronic, lab_filename, photo_filename, emergency, other))
            c.execute("UPDATE qrcodes SET assigned = 1 WHERE qr_id = ?", (qr_id,))
            conn.commit()
            flash("Patient registered.")
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("username or QR already used.")
            conn.close()
            return render_template("register.html", qr_id=qr_id)
        conn.close()
        return redirect(url_for("guest_view", qr_id=qr_id))
    conn.close()
    return render_template("register.html", qr_id=qr_id)

# Guest view minimal
@app.route("/guest/<qr_id>")
def guest_view(qr_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, birthdate, chronic_diseases, emergency_contact, blood_type, patient_photo FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    conn.close()
    if not patient:
        flash("Patient not found.")
        return redirect(url_for("scanner_gate"))
    age = calculate_age(patient["birthdate"])
    return render_template("guest_view.html", patient=patient, age=age, qr_id=qr_id)

# Patient login
@app.route("/login/<qr_id>", methods=["GET","POST"])
def login_patient(qr_id):
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM patients WHERE qr_id = ? AND username = ?", (qr_id, username))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["role"] = "patient"
            session["qr_id"] = qr_id
            session["username"] = username
            flash("Logged in.")
            return redirect(url_for("dashboard", qr_id=qr_id))
        flash("Invalid credentials.")
    return render_template("login.html", qr_id=qr_id, role="patient")

# Patient dashboard (full)
@app.route("/dashboard/<qr_id>")
def dashboard(qr_id):
    if session.get("role") != "patient" or session.get("qr_id") != qr_id:
        flash("Login as patient to see full data.")
        return redirect(url_for("guest_view", qr_id=qr_id))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()
    conn.close()
    age = calculate_age(patient["birthdate"])
    # compute pill progress (simple placeholder)
    pills_total = patient["monthly_pills"] or 0
    # For demo, compute random progress value or 0
    progress = min(100, pills_total * 3) if pills_total else 0
    return render_template("dashboard.html", patient=patient, age=age, visits=visits, pill_progress=progress)

# ---------------- Operator flows ----------------

# Create operator (protected by master key)
@app.route("/create_operator", methods=["GET","POST"])
def create_operator():
    if request.method == "POST":
        key = request.form.get("master_key","").strip()
        if key != MASTER_OPERATOR_KEY:
            flash("Invalid master key.")
            return render_template("create_operator.html")
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        if not username or not password:
            flash("username and password required")
            return render_template("create_operator.html")
        hashed = generate_password_hash(password)
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO operators (username, password) VALUES (?, ?)", (username, hashed))
            conn.commit()
            flash("Operator created.")
            conn.close()
            return redirect(url_for("operator_login"))
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            flash("username already exists.")
            return render_template("create_operator.html")
    return render_template("create_operator.html")

# Operator login
@app.route("/operator_login", methods=["GET","POST"])
def operator_login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
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

# Operator dashboard with search + analytics quick stats
@app.route("/operator_dashboard")
def operator_dashboard():
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))
    q = request.args.get("q","").strip()
    conn = get_db()
    c = conn.cursor()
    if q:
        like = f"%{q}%"
        c.execute("SELECT qr_id, name, phone, email, chronic_diseases FROM patients WHERE name LIKE ? OR qr_id LIKE ? OR phone LIKE ? ORDER BY name", (like, like, like))
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
    return render_template("operator_dashboard.html", patients=patients, q=q, total_patients=total_patients, total_scans=total_scans, total_visits=total_visits)

# Analytics Dashboard
@app.route("/analytics")
def analytics_dashboard():
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))
    
    analytics_data = get_analytics_data()
    return render_template("analytics.html", data=analytics_data)

# Analytics API endpoint
@app.route("/api/analytics")
def api_analytics():
    if session.get("role") != "operator":
        return jsonify({"error": "Unauthorized"}), 401
    
    analytics_data = get_analytics_data()
    return jsonify(analytics_data)

# Add visit (operator)
@app.route("/add_visit/<qr_id>", methods=["GET","POST"])
def add_visit(qr_id):
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
        visit_date = request.form.get("visit_date") or datetime.now().strftime("%Y-%m-%d")
        diagnosis = request.form.get("diagnosis","").strip()
        treatment = request.form.get("treatment","").strip()
        medicines = request.form.get("medicines","").strip()
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
        created_by = session.get("username")
        c.execute("""INSERT INTO visits (qr_id, visit_date, diagnosis, treatment, medicines, lab_file, created_by)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""", (qr_id, visit_date, diagnosis, treatment, medicines, lab_filename, created_by))
        conn.commit()
        conn.close()
        flash("Visit added.")
        return redirect(url_for("patient_visits", qr_id=qr_id))
    conn.close()
    return render_template("add_visit.html", qr_id=qr_id, patient=patient)

# View patient visits (operator)
@app.route("/patient_visits/<qr_id>")
def patient_visits(qr_id):
    if session.get("role") != "operator":
        flash("Operator login required.")
        return redirect(url_for("operator_login"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    visits = c.fetchall()
    c.execute("SELECT name FROM patients WHERE qr_id = ?", (qr_id,))
    patient = c.fetchone()
    conn.close()
    if not patient:
        flash("Patient not found.")
        return redirect(url_for("operator_dashboard"))
    return render_template("patient_visits.html", qr_id=qr_id, patient=patient, visits=visits)

# Edit patient (operator)
@app.route("/operator_edit/<qr_id>", methods=["GET","POST"])
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
        chronic = request.form.get("chronic_diseases","").strip()
        meds = request.form.get("medications","").strip()
        emergency = request.form.get("emergency_contact","").strip()
        other = request.form.get("other_info","").strip()
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
        c.execute("""UPDATE patients SET chronic_diseases = ?, medications = ?, emergency_contact = ?, other_info = ? WHERE qr_id = ?""",
                  (chronic, meds, emergency, other, qr_id))
        conn.commit()
        conn.close()
        flash("Patient updated.")
        return redirect(url_for("operator_dashboard"))
    conn.close()
    return render_template("operator_edit.html", patient=patient)

# Quick CSV export of visits for a QR
@app.route("/export_visits/<qr_id>")
def export_visits(qr_id):
    if session.get("role") != "operator":
        flash("Operator required.")
        return redirect(url_for("operator_login"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM visits WHERE qr_id = ? ORDER BY visit_date DESC", (qr_id,))
    rows = c.fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["visit_date","diagnosis","treatment","medicines","lab_file","created_by"])
    for r in rows:
        cw.writerow([r["visit_date"], r["diagnosis"], r["treatment"], r["medicines"], r["lab_file"], r["created_by"]])
    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-Disposition":f"attachment;filename={qr_id}_visits.csv"})

# Serve labs
@app.route("/labs/<filename>")
def labs(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# Serve patient photos
@app.route("/photos/<filename>")
def photos(filename):
    return send_from_directory(PHOTO_FOLDER, filename)

# Admin add QR
@app.route("/admin/add_qr", methods=["POST"])
def admin_add_qr():
    qr_id = request.form.get("qr_id","").strip()
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

# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("scanner_gate"))

# Run
if __name__ == "__main__":
    app.run(debug=True)
