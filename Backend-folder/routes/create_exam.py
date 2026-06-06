from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
import random
import string
import os
import json

bp = Blueprint('create_exam', __name__)


def generate_exam_code():
    chars = string.ascii_uppercase + string.digits
    return 'EXAM-' + ''.join(random.choices(chars, k=6))


@bp.route('/admin/exams/list', methods=['GET'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def get_exams():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                exam_id AS id,
                title,
                exam_code,
                duration_minutes AS duration,
                status,
                created_at,
                end_time AS deadline,
                (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.exam_id) AS total_questions
            FROM exams e
            ORDER BY created_at DESC
        """)
        exams = cursor.fetchall()
        return jsonify({"success": True, "exams": exams}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/admin/exams/create', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def create_exam():
    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    total_questions = data.get('total_questions')
    duration = data.get('duration')
    deadline = data.get('deadline')

    if not title or not total_questions or not duration:
        return jsonify({"success": False, "message": "Missing required fields"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        user_id = get_jwt_identity()
        exam_code = generate_exam_code()

        # FIX #4: Include total_questions + duration in INSERT
        query = """
            INSERT INTO exams (title, description, duration, duration_minutes, total_marks, passing_marks, is_published, start_time, end_time, status, created_by, exam_code, total_questions)
            VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), %s, 'published', %s, %s, %s)
        """
        cursor.execute(query, (title, description, duration, duration, total_questions, 0, deadline, user_id, exam_code, total_questions))
        conn.commit()

        return jsonify({"success": True, "message": "Exam created successfully", "exam_id": cursor.lastrowid, "exam_code": exam_code}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# POST /api/exams/create-with-pdf
@bp.route('/exams/create-with-pdf', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def create_exam_pdf():
    user_id = get_jwt_identity()

    title = request.form.get('title')
    duration = request.form.get('duration', 60)
    deadline = request.form.get('deadline')
    description = request.form.get('description', '')
    total_questions = int(request.form.get('total_questions', 0))

    if not title:
        return jsonify({"success": False, "message": "Title is required"}), 400

    # FIX A: Accept both 'pdf_file' (what frontend sends) and 'pdf' (fallback)
    pdf_file = request.files.get('pdf_file') or request.files.get('pdf')
    pdf_url = None

    # FIX B: Parse answer_key JSON sent by frontend
    answer_key_raw = request.form.get('answer_key')
    answer_key = {}
    if answer_key_raw:
        try:
            answer_key = json.loads(answer_key_raw)
        except (json.JSONDecodeError, TypeError):
            return jsonify({"success": False, "message": "Invalid answer_key format. Must be JSON like {\"1\":\"A\", \"2\":\"C\"}"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503

    try:
        cursor = conn.cursor()
        exam_code = generate_exam_code()

        # Insert exam record (include all NOT NULL columns)
        cursor.execute("""
            INSERT INTO exams (title, description, duration, duration_minutes, total_marks, passing_marks, is_published, start_time, end_time, status, created_by, exam_code, total_questions)
            VALUES (%s, %s, %s, %s, %s, %s, 1, NOW(), %s, 'published', %s, %s, %s)
        """, (title, description, duration, duration, total_questions or 0, 0, deadline or None, user_id, exam_code, total_questions or None))
        exam_id = cursor.lastrowid

        # FIX B: Store answer key as questions + options rows
        if answer_key:
            for q_num_str, correct_label in answer_key.items():
                q_num = int(q_num_str)
                # Insert question row (use question_order for ordering, same as exam_dashboard expects)
                cursor.execute("""
                    INSERT INTO questions (exam_id, question_text, question_order, marks)
                    VALUES (%s, %s, %s, %s)
                """, (exam_id, f"Question {q_num}", q_num, 1.00))
                question_id = cursor.lastrowid

                # Insert option rows (A, B, C, D) — set is_correct=1 on the right one
                for label in ['A', 'B', 'C', 'D']:
                    is_correct = 1 if label == correct_label.upper() else 0
                    cursor.execute("""
                        INSERT INTO options (question_id, option_label, option_text, is_correct)
                        VALUES (%s, %s, %s, %s)
                    """, (question_id, label, f"Option {label}", is_correct))

        # Save PDF after DB insert succeeds
        if pdf_file:
            upload_dir = os.path.join('uploads', 'exams')
            os.makedirs(upload_dir, exist_ok=True)

            filename = f"exam_{exam_code}_{pdf_file.filename}"
            filepath = os.path.join(upload_dir, filename)
            pdf_file.save(filepath)
            pdf_url = f"/uploads/exams/{filename}"

            # Update record with PDF URL
            cursor.execute("UPDATE exams SET pdf_url = %s WHERE exam_id = %s", (pdf_url, exam_id))

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Exam created successfully with PDF",
            "exam": {
                "exam_id": exam_id,
                "exam_code": exam_code,
                "title": title,
                "pdf_url": pdf_url
            }
        }), 201
    except Exception as e:
        conn.rollback()
        # Clean up orphaned file if it was saved but DB failed
        if pdf_url:
            try:
                os.remove(os.path.join('uploads', 'exams', filename))
            except:
                pass
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/admin/exams/<int:exam_id>', methods=['DELETE'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def delete_exam(exam_id):
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        # Delete related data first
        cursor.execute("DELETE FROM student_answers WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE exam_id = %s)", (exam_id,))
        cursor.execute("DELETE FROM proctoring_violations WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE exam_id = %s)", (exam_id,))
        cursor.execute("DELETE FROM results WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE exam_id = %s)", (exam_id,))
        cursor.execute("DELETE FROM student_attempts WHERE exam_id = %s", (exam_id,))
        cursor.execute("DELETE FROM questions WHERE exam_id = %s", (exam_id,))
        cursor.execute("DELETE FROM exam_assignments WHERE exam_id = %s", (exam_id,))
        cursor.execute("DELETE FROM exams WHERE exam_id = %s", (exam_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Exam deleted"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
