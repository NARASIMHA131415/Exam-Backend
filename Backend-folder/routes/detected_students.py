from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from utils.auth import role_required
from database import db

bp = Blueprint('detected_students', __name__)

@bp.route('/admin/clear-violations', methods=['DELETE'])
@jwt_required()
@role_required(['super_admin'])
def clear_all_violations():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor()
        # Clear the attempt logs where violations are stored
        cursor.execute("DELETE FROM question_attempt_logs WHERE action LIKE 'VIOLATION%'")
        conn.commit()
        return jsonify({"success": True, "message": "All violation records cleared successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
