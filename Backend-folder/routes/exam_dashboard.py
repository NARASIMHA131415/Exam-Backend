from flask import Blueprint, jsonify, request, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from datetime import datetime
import os
import base64
import uuid

bp = Blueprint('exam_dashboard', __name__)

# Helper to save base64 image to disk
def save_violation_image(base64_str):
    if not base64_str or not base64_str.startswith('data:image'):
        return None
    try:
        # Remove header (e.g., "data:image/jpeg;base64,")
        header, encoded = base64_str.split(',', 1)
        data = base64.b64decode(encoded)
        
        filename = f"violation_{uuid.uuid4().hex}.jpg"
        filepath = os.path.join('uploads', 'violations', filename)
        
        with open(filepath, 'wb') as f:
            f.write(data)
        
        return f"/uploads/violations/{filename}"
    except Exception as e:
        print(f"Image save error: {e}")
        return None

@bp.route('/exam/<int:exam_id>/questions', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_exam_questions(exam_id):
    user_id = get_jwt_identity()
    conn = db.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT exam_id as id, title, exam_code, duration_minutes as duration, pdf_url, total_questions FROM exams WHERE exam_id = %s", (exam_id,))
        exam = cursor.fetchone()
        if not exam:
            return jsonify({"success": False, "message": "Exam not found"}), 404
        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s", (exam_id, user_id))
        attempt = cursor.fetchone()
        questions = []
        if not exam['pdf_url']:
            cursor.execute("SELECT question_id as id, question_text, marks FROM questions WHERE exam_id = %s ORDER BY question_order", (exam_id,))
            questions = cursor.fetchall()
            for q in questions:
                cursor.execute("SELECT option_text, is_correct FROM options WHERE question_id = %s", (q['id'],))
                opts = cursor.fetchall()
                q['options'] = {chr(65+i): opt['option_text'] for i, opt in enumerate(opts)}
        return jsonify({"success": True, "exam": exam, "questions": questions, "submission": attempt}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/exam/<int:exam_id>/save-answer', methods=['POST'])
@jwt_required()
@role_required(['student'])
def save_answer(exam_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    answer = data.get('answer')
    q_id = data.get('question_id') or data.get('question_number')
    if not q_id or not answer:
        return jsonify({"success": False, "message": "Missing question ID or answer"}), 400
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s AND attempt_status = 'in_progress'", (exam_id, user_id))
        attempt = cursor.fetchone()
        if not attempt: return jsonify({"success": False, "message": "No active attempt"}), 403
        cursor.execute("INSERT INTO student_answers (attempt_id, question_id, selected_option_id) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE selected_option_id = VALUES(selected_option_id)", (attempt[0], q_id, answer))
        conn.commit()
        return jsonify({"success": True, "message": "Answer saved"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/exam/<int:exam_id>/submit', methods=['POST'])
@jwt_required()
@role_required(['student'])
def submit_exam(exam_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    answers = data.get('answers', [])
    time_taken = data.get('time_taken', 0)
    violations = data.get('violations', [])

    conn = db.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s AND attempt_status = 'in_progress'", (exam_id, user_id))
        attempt = cursor.fetchone()
        if not attempt: return jsonify({"success": False, "message": "No active attempt"}), 403
        attempt_id = attempt['attempt_id']
        cursor.execute("UPDATE student_attempts SET attempt_status = 'submitted', end_time = %s WHERE attempt_id = %s", (datetime.now(), attempt_id))
        
        # Store violations and save images
        for v in violations:
            image_path = save_violation_image(v.get('image'))
            # Using a dedicated proctoring_violations table for better structure
            cursor.execute("""
                INSERT INTO proctoring_violations (attempt_id, type, message, severity, image_path, timestamp) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (attempt_id, v.get('type'), v.get('message'), v.get('severity'), image_path, datetime.now()))

        # Grading logic (simplified)
        cursor.execute("SELECT q.question_id, o.option_id FROM questions q JOIN options o ON q.question_id = o.question_id WHERE q.exam_id = %s AND o.is_correct = TRUE", (exam_id,))
        correct_map = {row['question_id']: row['option_id'] for row in cursor.fetchall()}
        correct_count = sum(1 for a in answers if (a.get('question_id') or a.get('question_number')) in correct_map and str(a.get('answer')) == str(correct_map.get(a.get('question_id') or a.get('question_number'))))
        
        score = correct_count
        percentage = (correct_count / len(correct_map) * 100) if correct_map else 0
        cursor.execute("INSERT INTO results (attempt_id, score, correct_answers, percentage, evaluated_at) VALUES (%s, %s, %s, %s, %s)", (attempt_id, score, correct_count, percentage, datetime.now()))
        
        conn.commit()
        return jsonify({"success": True, "attempt_id": attempt_id, "score": score}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

# Route to serve the violation images to the Admin
@bp.route('/uploads/violations/<filename>')
def serve_violation_image(filename):
    return send_from_directory('uploads/violations', filename)
