from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from datetime import datetime

bp = Blueprint('detected_students', __name__)


@bp.route('/admin/clear-violations', methods=['DELETE'])
@jwt_required()
@role_required(['super_admin'])
def clear_all_violations():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM question_attempt_logs WHERE action LIKE 'VIOLATION%'")
        conn.commit()
        return jsonify({"success": True, "message": "All violation records cleared successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# FIX #2: POST /api/admin/deletion-requests
@bp.route('/admin/deletion-requests', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def create_deletion_request():
    user_id = get_jwt_identity()
    data = request.get_json()

    target_id = data.get('target_id')
    req_type = data.get('type')
    reason = data.get('reason', '')

    if not target_id or not req_type:
        return jsonify({"success": False, "message": "target_id and type are required"}), 400

    if req_type not in ['student', 'result']:
        return jsonify({"success": False, "message": "Type must be 'student' or 'result'"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT request_id FROM deletion_requests WHERE target_id = %s AND type = %s AND status = 'Pending Approval'",
            (target_id, req_type)
        )
        if cursor.fetchone():
            return jsonify({"success": False, "message": "A pending deletion request already exists for this item"}), 409

        cursor.execute(
            "INSERT INTO deletion_requests (target_id, type, reason, requested_by, status, created_at) VALUES (%s, %s, %s, %s, 'Pending Approval', %s)",
            (target_id, req_type, reason, user_id, datetime.now())
        )
        conn.commit()

        return jsonify({"success": True, "message": "Deletion request submitted successfully"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# FIX #3: DELETE /api/admin/results/<id>
@bp.route('/admin/results/<int:result_id>', methods=['DELETE'])
@jwt_required()
@role_required(['super_admin'])
def delete_result(result_id):
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT attempt_id FROM results WHERE result_id = %s OR attempt_id = %s", (result_id, result_id))
        result = cursor.fetchone()

        if not result:
            return jsonify({"success": False, "message": "Result not found"}), 404

        attempt_id = result['attempt_id']

        cursor.execute("DELETE FROM proctoring_violations WHERE attempt_id = %s", (attempt_id,))
        cursor.execute("DELETE FROM question_attempt_logs WHERE attempt_id = %s", (attempt_id,))
        cursor.execute("DELETE FROM student_answers WHERE attempt_id = %s", (attempt_id,))
        cursor.execute("DELETE FROM results WHERE attempt_id = %s", (attempt_id,))

        conn.commit()
        return jsonify({"success": True, "message": "Result and associated data deleted successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
