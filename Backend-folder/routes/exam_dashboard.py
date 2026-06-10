from flask import Blueprint, jsonify, request, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from datetime import datetime
import os
import base64
import uuid

bp = Blueprint('exam_dashboard', __name__)


def save_violation_image(base64_str):
    # Now returns the Base64 string directly for Database LONGTEXT storage
    if not base64_str or not base64_str.startswith('data:image'):
        return None
    return base64_str


@bp.route('/exam/<int:exam_id>/questions', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_exam_questions(exam_id):
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT exam_id as id, title, exam_code, COALESCE(duration_minutes, duration) as duration, pdf_url, total_questions FROM exams WHERE exam_id = %s", (exam_id,))
        exam = cursor.fetchone()

        if not exam:
            return jsonify({"success": False, "message": "Exam not found"}), 404

        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s", (exam_id, user_id))
        attempt = cursor.fetchone()

        questions = []
        if not exam['pdf_url']:
            cursor.execute("""
                SELECT q.question_id AS id, q.question_text, q.marks, q.question_order,
                       o.option_id, o.option_text, o.option_label, o.is_correct
                FROM questions q
                JOIN options o ON q.question_id = o.question_id
                WHERE q.exam_id = %s
                ORDER BY q.question_order, o.option_id
            """, (exam_id,))
            rows = cursor.fetchall()

            # Group options by question
            question_map = {}
            for row in rows:
                qid = row['id']
                if qid not in question_map:
                    question_map[qid] = {
                        "id": qid,
                        "question_text": row['question_text'],
                        "marks": row['marks'],
                        "options": {}
                    }
                # Use option_label (A, B, C, D) as key, store option_id for reference
                label = row.get('option_label') or chr(65 + len(question_map[qid]['options']))
                question_map[qid]['options'][label] = row['option_text']
                # Store correct option_id internally for grading
                if row['is_correct']:
                    question_map[qid]['_correct_label'] = label

            questions = list(question_map.values())
            # Remove internal grading info before sending to student
            for q in questions:
                q.pop('_correct_label', None)

        return jsonify({"success": True, "exam": exam, "questions": questions, "submission": attempt}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/exam/<int:exam_id>/save-answer', methods=['POST'])
@jwt_required()
@role_required(['student'])
def save_answer(exam_id):
    user_id = get_jwt_identity()
    data = request.get_json()
    answer = data.get('answer')  # This is the option label: "A", "B", "C", "D"
    q_id = data.get('question_id')
    q_number = data.get('question_number')

    if not answer:
        return jsonify({"success": False, "message": "Missing answer"}), 400
    if not q_id and not q_number:
        return jsonify({"success": False, "message": "Missing question ID or question number"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s AND attempt_status = 'in_progress'", (exam_id, user_id))
        attempt = cursor.fetchone()

        if not attempt:
            return jsonify({"success": False, "message": "No active attempt"}), 403

        attempt_id = attempt['attempt_id']

        # FIX: If only question_number was sent (PDF mode), look up the real question_id
        real_q_id = q_id
        real_q_number = q_number
        if q_number and not q_id:
            # PDF mode: frontend sends question_number (1, 2, 3...), need to find actual question_id
            cursor.execute(
                "SELECT question_id, question_order FROM questions WHERE exam_id = %s AND question_order = %s",
                (exam_id, int(q_number))
            )
            q_row = cursor.fetchone()
            if q_row:
                real_q_id = q_row['question_id']
                real_q_number = q_row['question_order']
            else:
                # Fallback: use q_number as q_id (for non-PDF mode or old data)
                real_q_id = int(q_number)
                real_q_number = int(q_number)
        elif q_id and not q_number:
            real_q_number = int(q_id)

        # Store with both the real question_id AND question_number
        # Use INSERT ... ON DUPLICATE KEY UPDATE to handle re-saves
        cursor.execute(
            """INSERT INTO student_answers (attempt_id, question_id, question_number, selected_option_id, selected_option)
               VALUES (%s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE selected_option_id = VALUES(selected_option_id), selected_option = VALUES(selected_option)""",
            (attempt_id, real_q_id, real_q_number, answer, answer)
        )
        conn.commit()

        return jsonify({"success": True, "message": "Answer saved"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
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
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT attempt_id FROM student_attempts WHERE exam_id = %s AND user_id = %s AND attempt_status = 'in_progress'", (exam_id, user_id))
        attempt = cursor.fetchone()

        if not attempt:
            return jsonify({"success": False, "message": "No active attempt"}), 403

        attempt_id = attempt['attempt_id']

        # 1. Mark attempt as submitted
        cursor.execute("UPDATE student_attempts SET attempt_status = 'submitted', end_time = %s WHERE attempt_id = %s", (datetime.now(), attempt_id))

        # 2. Save violation images and records
        for v in violations:
            image_path = save_violation_image(v.get('image'))
            cursor.execute("""
                INSERT INTO proctoring_violations (attempt_id, type, message, severity, image_path, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (attempt_id, v.get('type'), v.get('message'), v.get('severity'), image_path, datetime.now()))

        # 3. Grading logic
        # Get correct answers: keyed by BOTH question_id AND question_order
        # This handles both PDF mode (uses question_order) and non-PDF mode (uses question_id)
        cursor.execute("""
            SELECT q.question_id, q.question_order, o.option_label
            FROM questions q
            JOIN options o ON q.question_id = o.question_id
            WHERE q.exam_id = %s AND o.is_correct = TRUE
        """, (exam_id,))
        correct_rows = cursor.fetchall()

        # Build correct_map: question_id -> correct_label
        # Also build order_to_id: question_order -> question_id (for resolving PDF mode answers)
        correct_map = {}
        order_to_id = {}
        id_to_order = {}
        for row in correct_rows:
            correct_map[row['question_id']] = row['option_label'].strip().upper()
            if row['question_order'] is not None:
                order_to_id[row['question_order']] = row['question_id']
                id_to_order[row['question_id']] = row['question_order']

        # Get student answers from DB (already saved via save-answer)
        cursor.execute("SELECT question_id, question_number, selected_option_id FROM student_answers WHERE attempt_id = %s", (attempt_id,))
        db_answer_rows = cursor.fetchall()

        # Build db_answers keyed by question_id (resolving question_number -> question_id if needed)
        db_answers = {}
        for row in db_answer_rows:
            qid = row['question_id']
            ans = row['selected_option_id']
            # If question_id doesn't exist in correct_map but question_number does, resolve it
            if qid not in correct_map and row['question_number'] in order_to_id:
                qid = order_to_id[row['question_number']]
            if ans:
                db_answers[qid] = ans

        # Process frontend-submitted answers: resolve question_number -> question_id
        submitted_answers = {}
        for a in answers:
            raw_q_id = a.get('question_id')
            raw_q_num = a.get('question_number')
            ans_val = a.get('answer')

            if not ans_val:
                continue

            # Resolve to real question_id
            if raw_q_id:
                resolved_id = raw_q_id
                # Check if this is actually a question_number (PDF mode sends number as question_id)
                if resolved_id not in correct_map and raw_q_num and raw_q_num in order_to_id:
                    resolved_id = order_to_id[raw_q_num]
                elif resolved_id not in correct_map and resolved_id in order_to_id:
                    resolved_id = order_to_id[resolved_id]
            elif raw_q_num:
                resolved_id = order_to_id.get(int(raw_q_num), int(raw_q_num))
            else:
                continue

            submitted_answers[resolved_id] = ans_val

        # Merge: submitted answers override DB answers
        final_answers = {**db_answers, **submitted_answers}

        # Grade: compare student answer label with correct answer label
        correct_count = 0
        total_questions = len(correct_map)
        for q_id, correct_label in correct_map.items():
            student_answer = str(final_answers.get(q_id, '')).strip().upper()
            if student_answer and student_answer == correct_label:
                correct_count += 1

        score = correct_count
        percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0

        # Fix wrong_count/skipped calculation
        answered_count = len([v for v in final_answers.values() if v])
        skipped = total_questions - answered_count
        wrong_count = answered_count - correct_count

        # 4. Save results
        cursor.execute(
            "INSERT INTO results (attempt_id, score, max_score, total_questions, correct_answers, wrong_answers, skipped_questions, percentage, evaluated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (attempt_id, score, total_questions, total_questions, correct_count, wrong_count, skipped, percentage, datetime.now())
        )

        conn.commit()

        return jsonify({
            "success": True,
            "attempt_id": attempt_id,
            "score": score,
            "total_questions": total_questions,
            "percentage": round(percentage, 1)
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# GET /api/exam/<id>/timer
@bp.route('/exam/<int:exam_id>/timer', methods=['GET'])
@jwt_required()
@role_required(['student'])
def check_timer(exam_id):
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COALESCE(duration_minutes, duration) as duration_minutes FROM exams WHERE exam_id = %s", (exam_id,))
        exam = cursor.fetchone()

        if not exam:
            return jsonify({"success": False, "message": "Exam not found"}), 404

        cursor.execute(
            "SELECT attempt_id, start_time FROM student_attempts WHERE exam_id = %s AND user_id = %s AND attempt_status = 'in_progress'",
            (exam_id, user_id)
        )
        attempt = cursor.fetchone()

        if not attempt:
            return jsonify({"success": False, "message": "No active attempt"}), 403

        start_time = attempt['start_time']
        duration_seconds = exam['duration_minutes'] * 60
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = max(0, int(duration_seconds - elapsed))

        return jsonify({
            "success": True,
            "data": {
                "attempt_id": attempt['attempt_id'],
                "start_time": start_time.isoformat(),
                "duration_seconds": duration_seconds,
                "elapsed_seconds": int(elapsed),
                "remaining_seconds": remaining,
                "is_expired": remaining <= 0
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/uploads/violations/<filename>')
def serve_violation_image(filename):
    return send_from_directory('uploads/violations', filename)
