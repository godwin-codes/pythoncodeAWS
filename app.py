from flask import Flask, render_template, request
import boto3
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

bucket_name = os.getenv("S3_BUCKET")

db = pymysql.connect(
    host=os.getenv("DB_HOST"),
    port=3306,
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():

    name = request.form['name']
    email = request.form['email']
    course = request.form['course']

    photo = request.files['photo']

    s3 = boto3.client('s3')

    s3.upload_fileobj(
        photo,
        bucket_name,
        photo.filename
    )

    photo_url = photo.filename

    cursor = db.cursor()

    sql = """
    INSERT INTO students
    (name, email, course, photo_url)
    VALUES(%s, %s, %s, %s)
    """

    cursor.execute(
        sql,
        (name, email, course, photo_url)
    )

    db.commit()

    return "Student Registered Successfully"

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )
