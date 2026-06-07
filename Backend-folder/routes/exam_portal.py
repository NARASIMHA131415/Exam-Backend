from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from datetime import datetime

bp = Blueprint('exam_portal', __name__)


@bp.route('/exam/available', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_available_exams():
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        # Show all published exams — students join by code, no assignment required
        query = """
            SELECT
                e.exam_id as id, e.title, e.exam_code, e.description,
                e.duration_minutes as duration, e.end_time as deadline, e.created_at,
                (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.exam_id) as total_questions
            FROM exams e
            WHERE e.status = 'published'
            ORDER BY e.created_at DESC
        """
        cursor.execute(query)
        exams = cursor.fetchall()

        return jsonify({"success": True, "exams": exams}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/exam/by-code/<string:code>', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_exam_by_code(code):
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        # Look up exam by code only — no assignment required (students join by code)
        query = """
            SELECT e.exam_id as id, e.title, e.exam_code, e.description,
                   e.duration_minutes as duration, e.end_time as deadline,
                   (SELECT COUNT(*) FROM questions q WHERE q.exam_id = e.exam_id) as total_questions
            FROM exams e
            WHERE e.exam_code = %s AND e.status = 'published'
        """
        cursor.execute(query, (code.strip().upper(),))
        exam = cursor.fetchone()

        if not exam:
            return jsonify({"success": False, "message": "Invalid or expired exam code"}), 404

        return jsonify({"success": True, "exam": exam}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/exam/join', methods=['POST'])
@jwt_required()
@role_required(['student'])
def join_exam():
    user_id = get_jwt_identity()
    data = request.get_json()
    exam_code = (data.get('exam_code') or '').strip().upper()

    if not exam_code:
        return jsonify({"success": False, "message": "Exam code is required"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Find exam by code
        cursor.execute("SELECT exam_id FROM exams WHERE exam_code = %s AND status = 'published'", (exam_code,))
        exam = cursor.fetchone()

        if not exam:
            return jsonify({"success": False, "message": "Invalid exam code"}), 404

        exam_id = exam['exam_id']

        # 2. Check if already joined
        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s", (exam_id, user_id))
        attempt = cursor.fetchone()

        if attempt:
            return jsonify({"success": True, "message": "Already joined this exam", "attempt_id": attempt['attempt_id']}), 200

        # 3. Create new attempt
        cursor.execute(
            "INSERT INTO student_attempts (exam_id, user_id, student_id, start_time, end_time, attempt_status) VALUES (%s, %s, %s, %s, %s, 'in_progress')",
            (exam_id, user_id, user_id, datetime.now(), datetime.now())
        )
        conn.commit()

        return jsonify({"success": True, "message": "Joined successfully", "attempt_id": cursor.lastrowid}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
