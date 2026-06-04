from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from datetime import datetime

bp = Blueprint('result_page', __name__)


@bp.route('/result/<int:attempt_id>', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_result(attempt_id):
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT r.*, e.title as exam_title, e.exam_code, sa.start_time, sa.end_time, sa.user_id
            FROM results r
            JOIN student_attempts sa ON r.attempt_id = sa.attempt_id
            JOIN exams e ON sa.exam_id = e.exam_id
            WHERE r.attempt_id = %s AND sa.user_id = %s
        """
        cursor.execute(query, (attempt_id, user_id))
        result = cursor.fetchone()

        if not result:
            return jsonify({"success": False, "message": "Result not found"}), 404

        start, end = result['start_time'], result['end_time']
        time_taken = int((end - start).total_seconds()) if start and end else 0

        cursor.execute("SELECT exam_id FROM student_attempts WHERE attempt_id = %s", (attempt_id,))
        exam_id = cursor.fetchone()['exam_id']

        # BUG FIX: Use option_label instead of option_text for comparison
        # selected_option_id stores the label (A, B, C, D), so we compare with option_label
        # Also fetch option_text for display purposes
        cursor.execute(
            "SELECT q.question_id, o.option_label as correct_val, o.option_text as correct_text "
            "FROM questions q JOIN options o ON q.question_id = o.question_id "
            "WHERE q.exam_id = %s AND o.is_correct = TRUE",
            (exam_id,)
        )
        correct_ans = cursor.fetchall()

        cursor.execute("SELECT question_id, selected_option_id FROM student_answers WHERE attempt_id = %s", (attempt_id,))
        student_ans = {row['question_id']: row['selected_option_id'] for row in cursor.fetchall()}

        detailed = []
        for i, row in enumerate(correct_ans, 1):
            q_id = row['question_id']
            s_val = student_ans.get(q_id)
            # Compare labels (A==A), not text vs label
            is_correct = (str(s_val).strip().upper() == str(row['correct_val']).strip().upper()) if s_val and row['correct_val'] else False
            detailed.append({
                "question_number": i,
                "correct_answer": row['correct_val'],      # Label: "A"
                "correct_text": row.get('correct_text'),    # Text: "Paris" (for display)
                "student_answer": s_val,                     # Label: "A" or "B" etc
                "is_correct": is_correct
            })

        return jsonify({
            "success": True,
            "data": {**result, "time_taken": time_taken, "answers": detailed, "total_questions": len(correct_ans)}
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/student/results', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_student_results():
    user_id = get_jwt_identity()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT r.attempt_id, r.score, r.percentage, r.evaluated_at as submitted_at,
                   e.title as exam_title, e.exam_id,
                   (SELECT COUNT(*) FROM questions WHERE exam_id = e.exam_id) as total_questions,
                   TIMESTAMPDIFF(SECOND, sa.start_time, sa.end_time) as time_taken
            FROM results r
            JOIN student_attempts sa ON r.attempt_id = sa.attempt_id
            JOIN exams e ON sa.exam_id = e.exam_id
            WHERE sa.user_id = %s
            ORDER BY r.evaluated_at DESC
        """
        cursor.execute(query, (user_id,))
        return jsonify({"success": True, "results": cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/admin/results/list', methods=['GET'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def get_admin_results():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT r.*, e.title as exam_title, e.exam_code,
                   up.first_name, up.last_name, u.email as student_email,
                   (SELECT COUNT(*) FROM questions WHERE exam_id = e.exam_id) as total_questions,
                   TIMESTAMPDIFF(SECOND, sa.start_time, sa.end_time) as time_taken
            FROM results r
            JOIN student_attempts sa ON r.attempt_id = sa.attempt_id
            JOIN exams e ON sa.exam_id = e.exam_id
            JOIN users u ON sa.user_id = u.user_id
            LEFT JOIN user_profiles up ON u.user_id = up.user_id
            ORDER BY r.evaluated_at DESC
        """
        cursor.execute(query)
        results = cursor.fetchall()

        final_results = []
        for r in results:
            cursor.execute(
                "SELECT action, timestamp FROM question_attempt_logs WHERE attempt_id = %s AND action LIKE 'VIOLATION%%'",
                (r['attempt_id'],)
            )
            v_logs = cursor.fetchall()

            violations = []
            for log in v_logs:
                parts = log['action'].replace('VIOLATION: ', '').split(' - ')
                v_type = parts[0] if len(parts) > 0 else 'Unknown'
                v_msg = parts[1] if len(parts) > 1 else ''
                violations.append({
                    "type": v_type,
                    "message": v_msg,
                    "timestamp": log['timestamp'].isoformat() if log['timestamp'] else None,
                    "image": None
                })

            r['student_name'] = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or r['student_email']
            r['violations'] = violations
            final_results.append(r)

        return jsonify({"success": True, "results": final_results}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/admin/deletion-requests', methods=['GET'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def get_admin_deletion_requests():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM deletion_requests")
        return jsonify({"success": True, "requests": cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
