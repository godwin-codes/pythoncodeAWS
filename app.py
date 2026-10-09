
import os
import uuid
from pathlib import Path

import boto3
import pymysql
from botocore.exceptions import ClientError
from flask import Flask, request, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

BUCKET = os.environ["S3_BUCKET"]
REGION = os.environ.get("AWS_REGION", "ap-south-1")

s3 = boto3.client("s3", region_name=REGION)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

def get_db_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        port=3306,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor
    )

PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>Student Registration</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family:Arial; background:#f2f5f9; padding:25px; }
.container { max-width:520px; margin:auto; background:white;
padding:25px; border-radius:12px; }
label { display:block; margin-top:15px; font-weight:bold; }
input { box-sizing:border-box; width:100%; padding:10px;
margin-top:6px; }
button { margin-top:20px; padding:12px; width:100%;
background:#1769aa; color:white; border:0; cursor:pointer; }
</style>
</head>
<body>
<div class="container">
<h1>Student Registration System</h1>
{% if message %}<p>{{ message }}</p>{% endif %}
<form method="POST" action="/register"
enctype="multipart/form-data">
<label>Full name</label>
<input name="name" maxlength="100" required>
<label>Email address</label>
<input name="email" type="email" maxlength="150" required>
<label>Course</label>
<input name="course" maxlength="100" required>
<label>Student photo (optional, JPG/PNG/WEBP, max 5 MB)</label>
<input name="photo" type="file"
accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp">
<button type="submit">Register Student</button>
</form>
<p><a href="/students">View registered students</a></p>
</div>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE, message=None)

@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    course = request.form.get("course", "").strip()

    if not name or not email or not course:
        return "All fields are required.", 400

    photo_key = None
    photo = request.files.get("photo")

    if photo and photo.filename:
        extension = Path(photo.filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            return "Use a JPG, JPEG, PNG, or WEBP image.", 400

        photo_key = f"student-photos/{uuid.uuid4().hex}{extension}"

        try:
            s3.upload_fileobj(
                photo,
                BUCKET,
                photo_key,
                ExtraArgs={"ContentType": photo.mimetype}
            )
        except ClientError:
            app.logger.exception("S3 photo upload failed")
            return "Photo upload failed. Please try again.", 500

    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO students
                   (name, email, course, photo_url)
                   VALUES (%s, %s, %s, %s)""",
                (name, email, course, photo_key)
            )
        connection.commit()
    except Exception:
        connection.rollback()
        # Avoid leaving an uploaded photo if the database insert fails.
        if photo_key:
            try:
                s3.delete_object(Bucket=BUCKET, Key=photo_key)
            except ClientError:
                app.logger.exception("S3 cleanup failed")
        app.logger.exception("Student registration failed")
        return "Registration failed. Please try again.", 500
    finally:
        connection.close()

    return render_template_string(
        PAGE, message="Registration successful!"
    )

@app.route("/students")
def students():
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT id, name, email, course, photo_url, created_at
                   FROM students ORDER BY id DESC"""
            )
            records = cursor.fetchall()
    finally:
        connection.close()

    return render_template_string("""
    <html><head><title>Registered Students</title></head>
    <body style="font-family:Arial;margin:25px">
    <h1>Registered Students</h1>
    <p><a href="/">Back to registration</a></p>
    {% if records %}
    <table border="1" cellpadding="8" cellspacing="0">
    <tr><th>ID</th><th>Name</th><th>Email</th><th>Course</th>
    <th>S3 photo object key</th><th>Registered</th></tr>
    {% for s in records %}
    <tr><td>{{ s.id }}</td><td>{{ s.name }}</td>
    <td>{{ s.email }}</td><td>{{ s.course }}</td>
    <td>{{ s.photo_url or 'No photo' }}</td>
    <td>{{ s.created_at }}</td></tr>
    {% endfor %}
    </table>
    {% else %}<p>No students registered yet.</p>{% endif %}
    </body></html>
    """, records=records)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
