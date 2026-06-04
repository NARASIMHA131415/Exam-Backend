from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
import random
import string

bp = Blueprint('create_exam', __name__)

def generate_exam_code():
    chars = string.ascii_uppercase + string.digits
    return 'EXAM-' + ''.join(random.choices(chars, k=6))

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
    try:
        cursor = conn.cursor()
        user_id = get_jwt_identity()
        exam_code = generate_exam_code()
        
        query = """
            INSERT INTO exams (title, description, duration_minutes, end_time, status, created_by, exam_code) 
            VALUES (%s, %s, %s, %s, 'published', %s, %s)
        """
        # Note: I'm adding exam_code to the INSERT. You should add this column to your DB.
        cursor.execute(query, (title, description, duration, deadline, user_id, exam_code))
        conn.commit()
        
        return jsonify({"success": True, "message": "Exam created successfully", "exam_id": cursor.lastrowid}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/admin/exams/<int:exam_id>', methods=['DELETE'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def delete_exam(exam_id):
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM exams WHERE exam_id = %s", (exam_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Exam deleted"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
