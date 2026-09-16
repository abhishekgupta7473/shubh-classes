from datetime import datetime
import re
import os
from werkzeug.utils import secure_filename
import razorpay
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from dotenv import load_dotenv
load_dotenv()
from twilio.rest import Client
from datetime import datetime
from zoneinfo import ZoneInfo

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

twilio_client = Client(
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN
)

app = Flask(__name__)
razorpay_client = razorpay.Client(
    auth=(
        os.getenv("RAZORPAY_KEY_ID"),
        os.getenv("RAZORPAY_KEY_SECRET")
    )
)
app.secret_key = "shubh_classes_secret_key"
db = mysql.connector.connect(
    host=os.getenv("MYSQLHOST"),
    user=os.getenv("MYSQLUSER"),
    password=os.getenv("MYSQLPASSWORD"),
    database=os.getenv("MYSQLDATABASE"),
    port=int(os.getenv("MYSQLPORT", 3306))
)
def ensure_db_connection():
    global db

    try:
        db.ping(reconnect=True, attempts=3, delay=2)
    except Exception:
        db = mysql.connector.connect(
            host=os.getenv("MYSQLHOST"),
            user=os.getenv("MYSQLUSER"),
            password=os.getenv("MYSQLPASSWORD"),
            database=os.getenv("MYSQLDATABASE"),
            port=int(os.getenv("MYSQLPORT", 3306)),
            connection_timeout=10
        )

    return db


@app.before_request
def check_database_connection():
    ensure_db_connection()

@app.route("/admin/dashboard")
def admin_dashboard():
    check = role_required("admin")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM teachers")
    total_teachers = cursor.fetchone()["total"]

    
    cursor.execute("""
    SELECT COUNT(DISTINCT class_name) AS total
    FROM students
    WHERE class_name IS NOT NULL AND class_name <> ''
""")
    total_classes = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM results")
    total_results = cursor.fetchone()["total"]

    cursor.close()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_teachers=total_teachers,
        total_classes=total_classes,
        total_results=total_results
    )
@app.route("/admin/reports")
def admin_reports():
    check = role_required("admin")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT COUNT(*) AS total FROM students")
    total_students = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM teachers")
    total_teachers = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM attendance")
    total_attendance = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM results")
    total_results = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM fees")
    total_fees = cursor.fetchone()["total"]

    cursor.execute("SELECT COALESCE(SUM(paid_amount), 0) AS total FROM fees")
    paid_fees = cursor.fetchone()["total"]

    cursor.close()

    pending_fees = total_fees - paid_fees

    return render_template(
        "admin_reports.html",
        total_students=total_students,
        total_teachers=total_teachers,
        total_attendance=total_attendance,
        total_results=total_results,
        total_fees=total_fees,
        paid_fees=paid_fees,
        pending_fees=pending_fees
    )

@app.route("/admin/students")
def students():

    class_filter = request.args.get("class", "all")

    cursor = db.cursor(dictionary=True)

    if class_filter == "all":
        cursor.execute("""
            SELECT *
            FROM students
            ORDER BY id DESC
        """)
    else:
        cursor.execute("""
            SELECT *
            FROM students
            WHERE class_name = %s
            ORDER BY id DESC
        """, (class_filter,))

    students = cursor.fetchall()

    cursor.close()

    return render_template(
        "students.html",
        students=students,
        class_filter=class_filter
    )
@app.route("/teacher/students")
def teacher_students():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """)

    students = cursor.fetchall()

    cursor.close()

    return render_template(
        "teacher_students.html",
        students=students
    )
@app.route("/admin/classes")
def admin_classes():
    check = role_required("admin")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT * FROM classes ORDER BY class_name
        """
    )

    classes = cursor.fetchall()
    cursor.close()

    return render_template("admin_classes.html", classes=classes)
@app.route("/admin/add-class", methods=["GET", "POST"])
def add_class():
    if request.method == "POST":
        class_name = request.form["class_name"]

        cursor = db.cursor()

        cursor.execute(
            "INSERT INTO classes (class_name) VALUES (%s)",
            (class_name,)
        )

        db.commit()
        cursor.close()

        return redirect(url_for("admin_classes"))

    return render_template("add_class.html")
@app.route("/admin/edit-class/<int:class_id>", methods=["GET", "POST"])
def edit_class(class_id):
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        class_name = request.form["class_name"]

        cursor.execute(
            "UPDATE classes SET class_name = %s WHERE id = %s",
            (class_name, class_id)
        )

        db.commit()
        cursor.close()

        return redirect(url_for("admin_classes"))

    cursor.execute(
        "SELECT * FROM classes WHERE id = %s",
        (class_id,)
    )

    class_data = cursor.fetchone()
    cursor.close()

    return render_template("edit_class.html", class_data=class_data)
@app.route("/admin/delete-class/<int:class_id>", methods=["POST"])
def delete_class(class_id):
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM classes WHERE id = %s",
        (class_id,)
    )

    db.commit()
    cursor.close()

    return redirect(url_for("admin_classes"))
@app.route("/admin/teachers")
def teachers():
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM teachers ORDER BY id DESC")
    teachers = cursor.fetchall()

    cursor.close()

    return render_template("teachers.html", teachers=teachers)
@app.route("/admin/add-teacher", methods=["GET", "POST"])
def add_teacher():
    if request.method == "POST":
        user_id = request.form["user_id"]
        name = request.form["name"]
        password = request.form["password"]
        phone = request.form["phone"]
        if not phone.isdigit() or len(phone) != 10:
         return render_template(
        "add_teacher.html",
        error="Phone number must be exactly 10 digits."
    )
        email = request.form["email"]
        import re

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):

          return render_template(
        "add_teacher.html",
        error="Please enter a valid email address."
    )
        subject = request.form["subject"]
        qualification = request.form["qualification"]
        joining_date = request.form["joining_date"]

        cursor = db.cursor()

        cursor.execute(
          "SELECT user_id FROM teachers WHERE user_id = %s",
          (user_id,)
    )

        if cursor.fetchone():
           cursor.close()
           return render_template(
        "add_teacher.html",
        error="This User ID already exists. Please use a different User ID."
    )

        cursor.execute(
            """
            INSERT INTO teachers
            (user_id, name, phone, email, subject, qualification, joining_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                name,
                phone,
                email,
                subject,
                qualification,
                joining_date
            )
        )

        cursor.execute(
            """
            INSERT INTO users
            (user_id, password, role, name, email, phone)
            VALUES (%s, %s, 'teacher', %s, %s, %s)
            """,
            (
                user_id,
                password,
                name,
                email,
                phone
            )
        )

        db.commit()
        cursor.close()

        return "Teacher added successfully!"

    return render_template("add_teacher.html")

@app.route("/admin/teacher/edit/<user_id>", methods=["GET", "POST"])
def edit_teacher(user_id):

    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        if not phone.isdigit() or len(phone) != 10:
         return render_template(
        "edit_teacher.html",
        teacher={
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "email": email,
            "subject": subject,
            "qualification": qualification,
            "joining_date": joining_date
        },
        error="Phone number must be exactly 10 digits."
    )
        email = request.form["email"]
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
         return render_template(
        "edit_teacher.html",
        teacher={
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "email": email,
            "subject": subject,
            "qualification": qualification,
            "joining_date": joining_date
        },
        error="Please enter a valid email address."
    )
        subject = request.form["subject"]
        qualification = request.form["qualification"]
        joining_date = request.form["joining_date"]

        cursor.execute(
            """
            UPDATE teachers
            SET name=%s, phone=%s, email=%s, subject=%s,
                qualification=%s, joining_date=%s
            WHERE user_id=%s
            """,
            (
                name,
                phone,
                email,
                subject,
                qualification,
                joining_date,
                user_id
            )
        )

        cursor.execute(
            """
            UPDATE users
            SET name=%s, email=%s, phone=%s
            WHERE user_id=%s AND role='teacher'
            """,
            (name, email, phone, user_id)
        )

        db.commit()
        cursor.close()

        return redirect("/admin/teachers")

    cursor.execute(
        "SELECT * FROM teachers WHERE user_id=%s",
        (user_id,)
    )

    teacher = cursor.fetchone()
    cursor.close()

    return render_template("edit_teacher.html", teacher=teacher)

@app.route("/admin/teacher/delete/<user_id>", methods=["POST"])
def delete_teacher(user_id):

    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM teachers WHERE user_id=%s",
        (user_id,)
    )

    cursor.execute(
        "DELETE FROM users WHERE user_id=%s AND role='teacher'",
        (user_id,)
    )

    db.commit()
    cursor.close()

    return redirect("/admin/teachers")


@app.route("/admin/student/<user_id>")
def view_student(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") not in ["admin", "teacher"]:
        return "Access Denied", 403

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM students WHERE user_id = %s",
        (user_id,)
    )

    student = cursor.fetchone()
    cursor.close()

    if student:
        return render_template("view_student.html", student=student)

    return "Student not found"
@app.route("/admin/student/edit/<user_id>", methods=["GET", "POST"])
def edit_student(user_id):
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        if not phone.isdigit() or len(phone) != 10:
         return render_template(
        "edit_student.html",
        student={
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "email": email,
            "class_name": class_name,
            "course": course,
            "admission_date": admission_date
        },
        error="Phone number must be exactly 10 digits."
    )
        email = request.form["email"]
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
         return render_template(
        "edit_student.html",
        student={
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "email": email,
            "class_name": class_name,
            "course": course,
            "admission_date": admission_date
        },
        error="Please enter a valid email address."
    )
        class_name = request.form["class_name"]
        course = request.form["course"]
        admission_date = request.form["admission_date"]

        cursor.execute(
            """
            UPDATE students
            SET name=%s, phone=%s, email=%s,
                class_name=%s, course=%s, admission_date=%s
            WHERE user_id=%s
            """,
            (name, phone, email, class_name, course, admission_date, user_id)
        )

        db.commit()
        cursor.close()

        if session.get("role") == "teacher":
         return redirect(url_for("teacher_students"))

        if session.get("role") == "teacher":
          return redirect(url_for("teacher_students"))

        return redirect(url_for("students"))

    cursor.execute(
        "SELECT * FROM students WHERE user_id = %s",
        (user_id,)
    )

    student = cursor.fetchone()
    cursor.close()

    if student:
        return render_template("edit_student.html", student=student)

    return "Student not found"

@app.route("/admin/add-student", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        user_id = request.form["user_id"]
    
        name = request.form["name"]
        password = request.form["password"]
        phone = request.form["phone"]
        if not phone.isdigit() or len(phone) != 10:
         return render_template(
        "add_student.html",
        error="Phone number must be exactly 10 digits."
    )
        email = request.form["email"]
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
         return render_template(
        "add_student.html",
        error="Please enter a valid email address."
    )
        class_name = request.form["class_name"]
        course = request.form["course"]
        admission_date = request.form["admission_date"]

        cursor = db.cursor()

        cursor.execute(
           "SELECT user_id FROM students WHERE user_id = %s",
            (user_id,)
)

        if cursor.fetchone():
         cursor.close()
         return render_template(
        "add_student.html",
        error="This User ID already exists. Please use a different User ID."
    )

        cursor.execute(
            """
            INSERT INTO students
            (user_id, name, phone, email, class_name, course, admission_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                name,
                phone,
                email,
                class_name,
                course,
                admission_date
            )
        )

        cursor.execute(
            """
            INSERT INTO users
            (user_id, password, role, name, email, phone)
            VALUES (%s, %s, 'student', %s, %s, %s)
            """,
            (
                user_id,
                password,
                name,
                email,
                phone
            )
        )

        db.commit()
        try:
            twilio_client.messages.create(
                body=f"Dear {name}, your Shubh Classes account has been created. "
                f"Student ID: {user_id} | Password: {password}",
                from_=TWILIO_PHONE_NUMBER,
        to=f"+91{phone}"
    )
            print("SMS sent successfully!")
        except Exception as e:
         print("SMS failed:", e)
        cursor.close()

        return render_template(
    "add_student.html",
    success="Student added successfully!"
)

    return render_template("add_student.html")
@app.route("/teacher/add-student", methods=["GET", "POST"])
def teacher_add_student():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        user_id = request.form["user_id"]
        name = request.form["name"]
        password = request.form["password"]
        phone = request.form["phone"]
        email = request.form["email"]
        class_name = request.form["class_name"]
        course = request.form["course"]
        admission_date = request.form["admission_date"]

        # Phone validation
        if not phone.isdigit() or len(phone) != 10:
            return render_template(
                "teacher_add_student.html",
                error="Phone number must be exactly 10 digits."
            )

        # Email validation
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template(
                "teacher_add_student.html",
                error="Please enter a valid email address."
            )

        cursor = db.cursor()

        # Check duplicate student ID
        cursor.execute(
            "SELECT user_id FROM students WHERE user_id = %s",
            (user_id,)
        )

        if cursor.fetchone():
            cursor.close()

            return render_template(
                "teacher_add_student.html",
                error="This User ID already exists. Please use a different User ID."
            )

        # Add student
        cursor.execute(
            """
            INSERT INTO students
            (user_id, name, phone, email, class_name, course, admission_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                name,
                phone,
                email,
                class_name,
                course,
                admission_date
            )
        )

        # Add login account
        cursor.execute(
            """
            INSERT INTO users
            (user_id, password, role, name, email, phone)
            VALUES (%s, %s, 'student', %s, %s, %s)
            """,
            (
                user_id,
                password,
                name,
                email,
                phone
            )
        )

        db.commit()
        try:
            twilio_client.messages.create(
                body="sms_appointment_reminders",
                from_=TWILIO_PHONE_NUMBER,
                to=f"+91{phone}"
    )
            print("SMS sent successfully!")
        except Exception as e:
         print("SMS failed:", e)

        cursor.close()
        return render_template(
    "teacher_add_student.html",
    success="Student added successfully!"
)


    return render_template("teacher_add_student.html")
@app.route("/student/dashboard/<user_id>")
def student_dashboard(user_id):
    check = role_required("student")
    if check:
      return check
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        "SELECT * FROM students WHERE user_id = %s",
        (user_id,)
    )

    student = cursor.fetchone()
    cursor.execute(
        """
        SELECT day_name, start_time, end_time,
               class_name, subject, room
        FROM timetable
        WHERE class_name = %s
        ORDER BY start_time
        """,
        (student["class_name"],)
    )


    cursor.execute(
    """
    SELECT day_name, start_time, end_time,
           class_name, subject, room
    FROM timetable
    WHERE class_name = %s
    ORDER BY start_time
    """,
    (student["class_name"],)
)
    schedule = cursor.fetchall()

    return render_template(
    "student_dashboard.html",
    student=student,
    schedule=schedule,
)
@app.route("/student/attendance/<user_id>")


def student_attendance(user_id):
    cursor = db.cursor(dictionary=True, buffered=True)

    cursor.execute(
        "SELECT * FROM attendance WHERE student_user_id = %s ORDER BY attendance_date DESC",
        (user_id,)
    )

    attendance = cursor.fetchall()

    total = len(attendance)
    present = sum(1 for record in attendance if record["status"] == "Present")

    if total > 0:
        percentage = round((present / total) * 100, 2)
    else:
        percentage = 0

    cursor.close()

    return render_template(
        "student_attendance.html",
        attendance=attendance,
        total=total,
        present=present,
        percentage=percentage
    )
@app.route("/student/profile")
def student_profile():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT user_id, name, email, phone, class_name, course, profile_pic
        FROM students
        WHERE user_id = %s
    """, (user_id,))

    student = cursor.fetchone()

    cursor.close()

    if not student:
        return "Student not found."

    return render_template(
        "student_profile.html",
        student=student
    )



# 👇 YAHAN SE NAYA ROUTE START HOGA

@app.route("/student/update-profile-pic", methods=["POST"])
def update_profile_pic():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "student":
        return "Access Denied", 403

    file = request.files.get("profile_pic")

    if not file or file.filename == "":
        return redirect(url_for("student_profile"))

    allowed_extensions = {"png", "jpg", "jpeg", "webp"}

    filename = file.filename
    extension = filename.rsplit(".", 1)[-1].lower()

    if extension not in allowed_extensions:
        return "Invalid image format.", 400

    upload_folder = os.path.join(
        app.static_folder,
        "uploads",
        "profile_pics"
    )

    os.makedirs(upload_folder, exist_ok=True)

    user_id = session["user_id"]
    new_filename = f"{user_id}.{extension}"

    file.save(
        os.path.join(upload_folder, new_filename)
    )

    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE students
        SET profile_pic = %s
        WHERE user_id = %s
        """,
        (new_filename, user_id)
    )

    db.commit()
    cursor.close()

    return redirect(url_for("student_profile"))
@app.route("/student/remove-profile-pic", methods=["POST"])
def remove_profile_pic():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("role") != "student":
        return "Access Denied", 403

    user_id = session["user_id"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT profile_pic
        FROM students
        WHERE user_id = %s
        """,
        (user_id,)
    )

    student = cursor.fetchone()

    if student and student["profile_pic"]:

        filename = os.path.basename(student["profile_pic"])

        upload_folder = os.path.join(
            app.static_folder,
            "uploads",
            "profile_pics"
        )

        file_path = os.path.join(
            upload_folder,
            filename
        )

        if os.path.exists(file_path):
            os.remove(file_path)

        cursor.execute(
            """
            UPDATE students
            SET profile_pic = NULL
            WHERE user_id = %s
            """,
            (user_id,)
        )

        db.commit()

    cursor.close()

    return redirect(url_for("student_profile"))
@app.route("/student/results/<user_id>")
def student_results(user_id):
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM results WHERE student_user_id = %s ORDER BY id DESC",
        (user_id,)
    )

    results = cursor.fetchall()
    cursor.close()

    return render_template("student_results.html", results=results)
@app.route("/teacher/dashboard")
def teacher_dashboard():
    check = role_required("teacher")
    if check:
        return check
    return render_template("teacher_dashboard.html")
@app.route("/teacher/profile")
def teacher_profile():
    check = role_required("teacher")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT user_id, name, email, phone, role FROM users WHERE user_id = %s",
        (session["user_id"],)
    )

    teacher = cursor.fetchone()
    cursor.close()

    return render_template("teacher_profile.html", teacher=teacher)
@app.route("/teacher/classes")
def teacher_classes():
    check = role_required("teacher")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT DISTINCT class_name
        FROM timetable
        WHERE teacher_user_id = %s
        ORDER BY class_name
        """,
        (session["user_id"],)
    )

    classes = cursor.fetchall()
    cursor.close()

    return render_template("teacher_classes.html", classes=classes)


@app.route("/teacher/attendance", methods=["GET", "POST"])
def teacher_attendance():

    cursor = db.cursor(dictionary=True)

    # Get all classes
    cursor.execute("""
        SELECT DISTINCT class_name
        FROM students
        WHERE class_name IS NOT NULL
        AND class_name != ''
        ORDER BY class_name
    """)
    classes = cursor.fetchall()

    students = []
    selected_class = request.args.get("class_name") or request.form.get("class_name")
    attendance_date = (
    request.form.get("attendance_date")
    or request.form.get("selected_date")
    or request.args.get("attendance_date")
    or ""
)

    # When class is selected, get students of that class
    if selected_class:
        cursor.execute("""
            SELECT user_id, name, class_name
            FROM students
            WHERE class_name = %s
            ORDER BY name
        """, (selected_class,))

        students = cursor.fetchall()

    # Save attendance
    if request.method == "POST":

        if not selected_class:
            cursor.close()
            return "Please select a class."

        if not attendance_date:
            cursor.close()
            return "Please select attendance date."

        marked_by = session.get("user_id")

        for student in students:
            status = request.form.get(
                f"status_{student['user_id']}"
            )

            if status:
                cursor.execute("""
                    INSERT INTO attendance
                    (student_user_id, attendance_date, status, marked_by)
                    VALUES (%s, %s, %s, %s)
                """, (
                    student["user_id"],
                    attendance_date,
                    status,
                    marked_by
                ))

        db.commit()

        # Count attendance
        present_count = 0
        absent_count = 0

        for student in students:
            status = request.form.get(
                f"status_{student['user_id']}"
            )

            if status == "Present":
                present_count += 1
            elif status == "Absent":
                absent_count += 1

        cursor.close()

        return render_template(
            "attendance.html",
            classes=classes,
            students=students,
            selected_class=selected_class,
            attendance_date=attendance_date,
            present_count=present_count,
            absent_count=absent_count,
            success=True
        )

    cursor.close()

    return render_template(
        "attendance.html",
        classes=classes,
        students=students,
        selected_class=selected_class,
        attendance_date=attendance_date,
        present_count=0,
        absent_count=0
    )

@app.route("/teacher/add-result", methods=["GET", "POST"])
def add_result():
    if request.method == "POST":
        student_user_id = request.form["student_user_id"]
        subject = request.form["subject"]
        exam_name = request.form["exam_name"]
        marks = request.form["marks"]
        max_marks = request.form["max_marks"]
        teacher_user_id = request.form["teacher_user_id"]

        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO results
            (student_user_id, subject, exam_name, marks, max_marks, teacher_user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                student_user_id,
                subject,
                exam_name,
                marks,
                max_marks,
                teacher_user_id
            )
        )

        db.commit()
        cursor.close()

        return render_template(
    "add_result.html",
    success="Result saved successfully!"
)

    return render_template("add_result.html")
@app.route("/teacher/add-note", methods=["GET", "POST"])
def add_note():

    if request.method == "POST":

        title = request.form["title"]
        subject = request.form["subject"]
        description = request.form["description"]
        content = request.form["content"]
        teacher_user_id = request.form["teacher_user_id"]

        # PDF file
        pdf_file = request.files.get("pdf_file")

        pdf_filename = None

        # Agar PDF upload ki gayi hai
        if pdf_file and pdf_file.filename:

            # Sirf PDF allow
            if not pdf_file.filename.lower().endswith(".pdf"):
                return render_template(
                    "add_note.html",
                    error="Only PDF files are allowed."
                )

            # Upload folder
            upload_folder = os.path.join(
                "static",
                "uploads",
                "notes"
            )

            # Folder automatically create hoga
            os.makedirs(upload_folder, exist_ok=True)

            # Unique safe filename
        original_filename = secure_filename(pdf_file.filename)

        name, extension = os.path.splitext(original_filename)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        pdf_filename = f"{name}_{timestamp}{extension}"

            # PDF save
        pdf_file.save(
                os.path.join(
                    upload_folder,
                    pdf_filename
                )
            )

        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO notes
            (title, subject, description, content,
             teacher_user_id, pdf_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                title,
                subject,
                description,
                content,
                teacher_user_id,
                pdf_filename
            )
        )

        db.commit()
        cursor.close()

        return "Note saved successfully!"

    return render_template("add_note.html")
@app.route("/student/download-note/<filename>")
def download_note(filename):

    if "user_id" not in session:
        return redirect(url_for("login"))

    notes_folder = os.path.join(
        "static",
        "uploads",
        "notes"
    )

    safe_filename = secure_filename(filename)
    if not safe_filename.lower().endswith(".pdf"):
     return "Invalid file type.", 400

    file_path = os.path.join(
        notes_folder,
        safe_filename
    )

    if not os.path.isfile(file_path):
        return "PDF not found.", 404

    return send_from_directory(
        notes_folder,
        safe_filename,
        as_attachment=True
    )
@app.route("/student/notes")
def student_notes():
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM notes ORDER BY id DESC"
    )

    notes = cursor.fetchall()
    cursor.close()

    return render_template(
    "student_notes.html",
    notes=notes,
    user_id=session.get("user_id")
)
@app.route("/student/timetable/<class_name>")
def student_timetable(class_name):
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT * FROM timetable
        WHERE class_name = %s
        ORDER BY FIELD(day_name,
        'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'),
        start_time
        """,
        (class_name,)
    )

    timetable = cursor.fetchall()
    cursor.close()

    return render_template("student_timetable.html", timetable=timetable)
@app.route("/student/classes")
def student_classes():

    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT *
        FROM timetable
        WHERE class_name = (
            SELECT class_name
            FROM students
            WHERE user_id = %s
        )
        ORDER BY day_name, start_time
    """, (user_id,))

    classes = cursor.fetchall()

    cursor.close()

    return render_template(
        "student_classes.html",
        classes=classes
    )
@app.route("/teacher/schedule/<teacher_user_id>")
def teacher_schedule(teacher_user_id):
    check = role_required("teacher")
    if check:
        return check

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT * FROM timetable
        WHERE teacher_user_id = %s
        ORDER BY FIELD(day_name,
        'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'),
        start_time
        """,
        (teacher_user_id,)
    )

    schedule = cursor.fetchall()
    cursor.close()

    return render_template("teacher_schedule.html", schedule=schedule)
@app.route("/admin/add-timetable", methods=["GET", "POST"])
def add_timetable():
    if request.method == "POST":
        class_name = request.form["class_name"]
        day_name = request.form["day_name"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]
        subject = request.form["subject"]
        teacher_user_id = request.form["teacher_user_id"]
        room = request.form["room"]

        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO timetable
            (class_name, day_name, start_time, end_time,
             subject, teacher_user_id, room)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                class_name,
                day_name,
                start_time,
                end_time,
                subject,
                teacher_user_id,
                room
            )
        )

        db.commit()
        cursor.close()
        return render_template(
    "add_timetable.html",
    success="Timetable saved successfully!"
)
    return render_template("add_timetable.html")
@app.route("/student/fees/<user_id>")
def student_fees(user_id):
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM fees WHERE student_user_id = %s ORDER BY id DESC",
        (user_id,)
    )

    fees = cursor.fetchall()
    cursor.close()

    return render_template(
    "student_fees.html",
    fees=fees,
    user_id=user_id
)
@app.route("/student/payment-history/<user_id>")
def payment_history(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    # Student sirf apni payment history dekh sakta hai
    if session["user_id"] != user_id:
        return "Access Denied", 403

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT
            id,
            razorpay_payment_id,
            razorpay_order_id,
            amount,
            status,
            payment_date
        FROM payment_transactions
        WHERE student_user_id = %s
        ORDER BY payment_date DESC
        """,
        (user_id,)
    )

    transactions = cursor.fetchall()
    cursor.close()

    return render_template(
        "payment_history.html",
        transactions=transactions,
        user_id=user_id
    )
@app.route("/student/create-payment", methods=["POST"])
def create_payment():

    if "user_id" not in session:
        return redirect(url_for("login"))

    student_user_id = session["user_id"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT amount, paid_amount
        FROM fees
        WHERE student_user_id = %s
        """,
        (student_user_id,)
    )

    fees = cursor.fetchall()
    cursor.close()

    total_remaining = sum(
        (fee["amount"] or 0) - (fee["paid_amount"] or 0)
        for fee in fees
    )

    if total_remaining <= 0:
        return "No outstanding fee.", 400

    amount_paise = int(round(float(total_remaining) * 100))

    order = razorpay_client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "receipt": f"fee_{student_user_id}",
        "notes": {
            "student_user_id": student_user_id
        }
    })

    return {
        "order_id": order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "key_id": os.getenv("RAZORPAY_KEY_ID")
    }
@app.route("/student/verify-payment", methods=["POST"])
def verify_payment():

    if "user_id" not in session:
        return {"error": "Please login first."}, 401

    data = request.get_json()

    try:
        # Razorpay signature verification
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": data["razorpay_order_id"],
            "razorpay_payment_id": data["razorpay_payment_id"],
            "razorpay_signature": data["razorpay_signature"]
        })

    except Exception:
        return {"error": "Payment verification failed."}, 400

    student_user_id = session["user_id"]

    cursor = db.cursor(dictionary=True)

    # Get the actual outstanding fee from database
    cursor.execute(
        """
        SELECT id, amount, paid_amount
        FROM fees
        WHERE student_user_id = %s
        ORDER BY due_date ASC, id ASC
        """,
        (student_user_id,)
    )

    fees = cursor.fetchall()

    # Calculate actual outstanding amount
    total_remaining = sum(
        float(fee["amount"] or 0)
        - float(fee["paid_amount"] or 0)
        for fee in fees
    )

    if total_remaining <= 0:
        cursor.close()
        return {"error": "No outstanding fee."}, 400

    # Get the Razorpay payment details
    try:
        payment = razorpay_client.payment.fetch(
            data["razorpay_payment_id"]
        )

    except Exception:
        cursor.close()
        return {"error": "Unable to verify payment details."}, 400

    # Make sure payment belongs to the order created by our server
    if payment["order_id"] != data["razorpay_order_id"]:
        cursor.close()
        return {"error": "Invalid payment order."}, 400

    # Get amount actually paid according to Razorpay
    payment_amount = float(payment["amount"]) / 100

    # Payment should not exceed outstanding fee
    if payment_amount > total_remaining:
        cursor.close()
        return {"error": "Payment amount is invalid."}, 400

    remaining_payment = payment_amount

    for fee in fees:

        fee_remaining = (
            float(fee["amount"])
            - float(fee["paid_amount"] or 0)
        )

        if fee_remaining <= 0:
            continue

        if remaining_payment <= 0:
            break

        payment_for_fee = min(
            remaining_payment,
            fee_remaining
        )

        new_paid_amount = (
            float(fee["paid_amount"] or 0)
            + payment_for_fee
        )

        if new_paid_amount >= float(fee["amount"]):
            status = "Paid"
        elif new_paid_amount > 0:
            status = "Partial"
        else:
            status = "Pending"

        cursor.execute(
            """
            UPDATE fees
            SET paid_amount = %s,
                status = %s,
                payment_date = CURDATE()
            WHERE id = %s
            """,
            (
                new_paid_amount,
                status,
                fee["id"]
            )
        )

        remaining_payment -= payment_for_fee

    cursor.execute(
           """
        INSERT INTO payment_transactions
        (
            student_user_id,
            razorpay_payment_id,
            razorpay_order_id,
            amount,
            status
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            student_user_id,
            data["razorpay_payment_id"],
            data["razorpay_order_id"],
            payment_amount,
            "Paid"
        )
    )

    db.commit()
    cursor.close()

    return {
        "success": True,
        "message": "Payment verified successfully."
    }
@app.route("/student/payment-receipt/<payment_id>")
def payment_receipt(payment_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    student_user_id = session["user_id"]

    try:
        payment = razorpay_client.payment.fetch(payment_id)
    except Exception:
        return "Payment not found.", 404

    if payment.get("status") != "captured":
        return "Payment is not completed.", 400

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT name, user_id, class_name, course
        FROM students
        WHERE user_id = %s
        """,
        (student_user_id,)
    )

    student = cursor.fetchone()
    cursor.close()

    if not student:
        return "Student not found.", 404

    amount = float(payment["amount"]) / 100

    payment_date = datetime.fromtimestamp(
    payment["created_at"],
    tz=ZoneInfo("Asia/Kolkata")
).strftime("%d %B %Y, %I:%M %p")

    return render_template(
    "payment_receipt.html",
    student=student,
    payment=payment,
    amount=amount,
    payment_date=payment_date
)
@app.route("/admin/add-fee", methods=["GET", "POST"])
def add_fee():
    if request.method == "POST":
        student_user_id = request.form["student_user_id"]
        fee_type = request.form["fee_type"]
        amount = request.form["amount"]
        paid_amount = request.form["paid_amount"]
        due_date = request.form["due_date"]
        status = request.form["status"]
        payment_date = request.form["payment_date"]

        cursor = db.cursor()

        cursor.execute(
            """
            INSERT INTO fees
            (student_user_id, fee_type, amount, paid_amount,
             due_date, status, payment_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_user_id,
                fee_type,
                amount,
                paid_amount,
                due_date,
                status,
                payment_date
            )
        )

        db.commit()
        cursor.close()

        return "Fee saved successfully!"

    return render_template("add_fee.html")

@app.route("/admin/fees")
def admin_fees():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            s.user_id,
            s.name,
            s.class_name,
            COALESCE(SUM(f.amount), 0) AS total_fee,
            COALESCE(SUM(f.paid_amount), 0) AS total_paid,
            COALESCE(
                SUM(f.amount) - SUM(f.paid_amount),
                0
            ) AS total_pending,
            MAX(f.due_date) AS due_date
        FROM students s
        LEFT JOIN fees f
            ON s.user_id = f.student_user_id
        GROUP BY
            s.user_id,
            s.name,
            s.class_name
        ORDER BY s.name ASC
    """)

    students = cursor.fetchall()
    cursor.close()

    return render_template(
    "admin_fees.html",
    students=students,
    generated=request.args.get("generated"),
    skipped=request.args.get("skipped")
)
@app.route("/admin/fees/generate-monthly", methods=["POST"])
def generate_monthly_fee():

    check = role_required("admin")
    if check:
        return check

    class_name = request.form.get("class_name", "").strip()
    fee_type = request.form.get("fee_type", "").strip()
    amount = float(request.form.get("amount") or 0)
    due_date = request.form.get("due_date")

    if not class_name:
        return "Please select a class.", 400

    if not fee_type:
        return "Fee type is required.", 400

    if amount <= 0:
        return "Fee amount must be greater than 0.", 400

    if not due_date:
        return "Due date is required.", 400

    cursor = db.cursor(dictionary=True)

    # ONLY students from selected class
    cursor.execute(
        """
        SELECT user_id
        FROM students
        WHERE class_name = %s
        ORDER BY user_id ASC
        """,
        (class_name,)
    )

    students = cursor.fetchall()

    created_count = 0
    skipped_count = 0

    for student in students:

        student_user_id = student["user_id"]

        # Check if this fee already exists for this student
        cursor.execute(
            """
            SELECT id
            FROM fees
            WHERE student_user_id = %s
              AND fee_type = %s
              AND due_date = %s
            LIMIT 1
            """,
            (
                student_user_id,
                fee_type,
                due_date
            )
        )

        existing_fee = cursor.fetchone()

        if existing_fee:
            skipped_count += 1
            continue

        # Create fee only for selected class students
        cursor.execute(
            """
            INSERT INTO fees
            (
                student_user_id,
                fee_type,
                amount,
                paid_amount,
                due_date,
                status,
                payment_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                student_user_id,
                fee_type,
                amount,
                0,
                due_date,
                "Pending",
                None
            )
        )

        created_count += 1

    db.commit()
    cursor.close()

    return redirect(
        url_for(
            "admin_fees",
            generated=created_count,
            skipped=skipped_count
        )
    )
@app.route("/admin/fees/manage/<user_id>", methods=["GET", "POST"])
def manage_student_fee(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    # Student details
    cursor.execute(
        """
        SELECT user_id, name, class_name, course, profile_pic
        FROM students
        WHERE user_id = %s
        """,
        (user_id,)
    )

    student = cursor.fetchone()

    if not student:
        cursor.close()
        return "Student not found.", 404

    # Update fee
    if request.method == "POST":

        fee_id = request.form["fee_id"]
        paid_amount = float(request.form["paid_amount"] or 0)
        payment_date = request.form.get("payment_date") or None

        # Get original fee
        cursor.execute(
            """
            SELECT amount
            FROM fees
            WHERE id = %s
              AND student_user_id = %s
            """,
            (fee_id, user_id)
        )

        fee = cursor.fetchone()

        if not fee:
            cursor.close()
            return "Fee record not found.", 404

        total_amount = float(fee["amount"])

        # Paid amount cannot exceed total fee
        if paid_amount > total_amount:
            cursor.close()
            return "Paid amount cannot be greater than total fee.", 400

        if paid_amount <= 0:
            status = "Pending"
        elif paid_amount < total_amount:
            status = "Partial"
        else:
            status = "Paid"

        cursor.execute(
            """
            UPDATE fees
            SET paid_amount = %s,
                status = %s,
                payment_date = %s
            WHERE id = %s
              AND student_user_id = %s
            """,
            (
                paid_amount,
                status,
                payment_date,
                fee_id,
                user_id
            )
        )

        db.commit()

    # Get all fee records
    cursor.execute(
        """
        SELECT
            id,
            fee_type,
            amount,
            paid_amount,
            due_date,
            status,
            payment_date
        FROM fees
        WHERE student_user_id = %s
        ORDER BY due_date DESC, id DESC
        """,
        (user_id,)
    )

    fees = cursor.fetchall()
    cursor.close()

    return render_template(
        "manage_student_fee.html",
        student=student,
        fees=fees
    )
@app.route("/admin/fees/manage/<user_id>/add", methods=["POST"])
def add_student_fee_from_manage(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    fee_type = request.form.get("fee_type")
    amount = float(request.form.get("amount") or 0)
    due_date = request.form.get("due_date") or None

    if not fee_type or amount <= 0:
        return "Invalid fee details.", 400

    cursor = db.cursor()

    cursor.execute(
        """
        INSERT INTO fees
        (
            student_user_id,
            fee_type,
            amount,
            paid_amount,
            due_date,
            status,
            payment_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            user_id,
            fee_type,
            amount,
            0,
            due_date,
            "Pending",
            None
        )
    )

    db.commit()
    cursor.close()

    return redirect(
        url_for("manage_student_fee", user_id=user_id)
    )

@app.route("/admin/fees/manage/<user_id>/cash-payment", methods=["POST"])
def record_cash_payment(user_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    fee_id = request.form.get("fee_id")
    cash_amount = float(request.form.get("cash_amount") or 0)
    payment_date = request.form.get("payment_date")

    if not fee_id or cash_amount <= 0 or not payment_date:
        return "Invalid cash payment details.", 400

    cursor = db.cursor(dictionary=True)

    # Get fee record
    cursor.execute(
        """
        SELECT id, amount, paid_amount
        FROM fees
        WHERE id = %s
          AND student_user_id = %s
        """,
        (fee_id, user_id)
    )

    fee = cursor.fetchone()

    if not fee:
        cursor.close()
        return "Fee record not found.", 404

    total_fee = float(fee["amount"])
    current_paid = float(fee["paid_amount"] or 0)

    # Remaining amount
    remaining_amount = total_fee - current_paid

    # Cash payment cannot exceed remaining fee
    if cash_amount > remaining_amount:
        cursor.close()
        return (
            f"Cash amount cannot be greater than "
            f"remaining fee ₹{remaining_amount:.2f}."
        ), 400

    # New paid amount
    new_paid_amount = current_paid + cash_amount

    # Determine status
    if new_paid_amount >= total_fee:
        status = "Paid"
    elif new_paid_amount > 0:
        status = "Partial"
    else:
        status = "Pending"

    # Update fee
    cursor.execute(
        """
        UPDATE fees
        SET paid_amount = %s,
            status = %s,
            payment_date = %s
        WHERE id = %s
          AND student_user_id = %s
        """,
        (
            new_paid_amount,
            status,
            payment_date,
            fee_id,
            user_id
        )
    )

    # Save cash transaction
    cursor.execute(
        """
        INSERT INTO cash_transactions
        (
            student_user_id,
            fee_id,
            amount,
            payment_date
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            user_id,
            fee_id,
            cash_amount,
            payment_date
        )
    )

    db.commit()
    cursor.close()

    return redirect(
        url_for(
            "manage_student_fee",
            user_id=user_id
        )
    )
@app.route("/")
@app.route("/")
def home():
    return render_template("login.html")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    user_id = request.form["user_id"]
    password = request.form["password"]
    role = request.form["role"]

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s AND password = %s AND role = %s",
        (user_id, password, role)
    )

    user = cursor.fetchone()
    cursor.close()

    if user:
        session["user_id"] = user["user_id"]
        session["role"] = str(user["role"]).strip().lower()

        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))

        if user["role"] == "student":
            return redirect(url_for("student_dashboard", user_id=user_id))

        if user["role"] == "teacher":
            return redirect(url_for("teacher_dashboard"))

    return render_template(
        "login.html",
        error="Wrong User ID, Password, or Login Type."
)


def login_required():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return None
def role_required(required_role):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_role = str(session.get("role", "")).strip().lower()
    required_role = str(required_role).strip().lower()

    print("DEBUG ROLE:", repr(user_role), "REQUIRED:", repr(required_role))

    if user_role != required_role:
        return "Access Denied", 403

    return None
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/admin/student/delete/<user_id>", methods=["POST"])
def delete_student(user_id):
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM students WHERE user_id = %s",
        (user_id,)
    )

    cursor.execute(
        "DELETE FROM users WHERE user_id = %s AND role = 'student'",
        (user_id,)
    )

    db.commit()
    cursor.close()

    if session.get("role") == "teacher":
      return redirect(url_for("teacher_students"))

    return redirect(url_for("students"))
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    user_id = request.form["user_id"]
    role = request.form["role"]
    new_password = request.form["new_password"]

    cursor = db.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s AND role = %s",
        (user_id, role)
    )

    user = cursor.fetchone()

    if not user:
        cursor.close()
        return render_template(
            "forgot_password.html",
            error="User ID ya Login Type galat hai."
        )

    cursor.execute(
        "UPDATE users SET password = %s WHERE user_id = %s AND role = %s",
        (new_password, user_id, role)
    )

    db.commit()
    cursor.close()

    return render_template(
        "forgot_password.html",
        success="Password successfully change ho gaya."
    )
if __name__ == "__main__":
   app.run(host="0.0.0.0", port=5001, debug=True)
