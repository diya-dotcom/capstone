import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import boto3
import pymysql
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "capstone-student-app-secret-key-2026")

# Environment-based Configuration (Task F3: Externalized Secrets)
BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "student-photos-diya-2026")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
USE_PRESIGNED_URL = os.environ.get("USE_PRESIGNED_URL", "false").lower() in ("true", "1", "yes")

# Database Configuration (Task F3)
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_USER = os.environ.get("DB_USER", "admin")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "Admin123")
DB_NAME = os.environ.get("DB_NAME", "studentdb")
DB_PORT = int(os.environ.get("DB_PORT", 3306))


def get_db_connection():
    """
    Establishes connection to Amazon RDS MySQL database.
    Credentials are read securely from environment variables.
    """
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )


def get_s3_client():
    """
    Initializes Boto3 S3 client.
    Notice: No static AWS access keys are passed.
    Boto3 automatically discovers temporary credentials from the attached
    EC2 IAM Instance Role (ec2-s3-role).
    """
    return boto3.client("s3", region_name=AWS_REGION)


@app.route("/")
def home():
    """Renders the student registration form."""
    return render_template("index.html", bucket_name=BUCKET_NAME)


@app.route("/register", methods=["POST"])
def register():
    """
    Processes student registration:
    1. Uploads photo file to Amazon S3 using IAM role permissions.
    2. Determines S3 object URL (Public read or Pre-signed URL).
    3. Persists student metadata into Amazon RDS MySQL.
    """
    try:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()
        photo = request.files.get("photo")

        if not name or not email or not course or not photo or photo.filename == "":
            return render_template(
                "index.html",
                error="All fields (Name, Email, Course, and Photo) are required.",
                bucket_name=BUCKET_NAME
            ), 400

        # Generate unique filename to prevent S3 object collisions
        safe_filename = f"{uuid.uuid4().hex[:8]}_{photo.filename}"

        # Upload Photo to Amazon S3
        s3 = get_s3_client()
        content_type = photo.content_type or "image/jpeg"
        s3.upload_fileobj(
            photo,
            BUCKET_NAME,
            safe_filename,
            ExtraArgs={"ContentType": content_type}
        )

        # Generate Photo URL (Option 1: Standard URL / Option 2: Pre-signed URL)
        if USE_PRESIGNED_URL:
            # Task D2 (Option 2 Bonus): Generate 1-hour time-limited pre-signed URL
            photo_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": safe_filename},
                ExpiresIn=3600
            )
        else:
            # Task D2 (Option 1): Standard public object URL
            photo_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{safe_filename}"

        # Insert Record into Amazon RDS MySQL
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO students (name, email, course, photo_url)
                VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql, (name, email, course, photo_url))
        finally:
            conn.close()

        return render_template(
            "index.html",
            success=True,
            student_name=name,
            student_email=email,
            student_course=course,
            photo_url=photo_url,
            bucket_name=BUCKET_NAME
        )

    except Exception as e:
        app.logger.error(f"Registration Error: {e}")
        return render_template(
            "index.html",
            error=f"Error processing registration: {str(e)}",
            bucket_name=BUCKET_NAME
        ), 500


@app.route("/students")
def list_students():
    """
    Roster view displaying all registered students from RDS MySQL.
    Useful for Part G validation: 'confirm row was inserted in MySQL'.
    """
    try:
        conn = get_db_connection()
        students = []
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, name, email, course, photo_url FROM students ORDER BY id DESC")
                students = cursor.fetchall()
        finally:
            conn.close()
        return render_template("students.html", students=students)
    except Exception as e:
        return f"Database query error: {str(e)}", 500


@app.route("/health")
def health_check():
    """Health check endpoint for ALB or monitoring."""
    return jsonify({
        "status": "healthy",
        "database_host": DB_HOST,
        "s3_bucket": BUCKET_NAME
    }), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
