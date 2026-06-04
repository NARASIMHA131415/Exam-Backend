from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('dashboard', __name__)


# FIX #7: GET /api/admin/dashboard
@bp.route('/admin/dashboard', methods=['GET'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def get_admin_dashboard():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS count FROM exams")
        total_exams = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM student_attempts")
        total_submissions = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'student'")
        total_students = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin'")
        total_admins = cursor.fetchone()['count']

        return jsonify({
            "success": True,
            "data": {
                "total_exams": total_exams,
                "total_submissions": total_submissions,
                "total_students": total_students,
                "total_admins": total_admins
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/student/dashboard', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_student_dashboard():
    user_id = get_jwt_identity()
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS count FROM results r JOIN student_attempts sa ON r.attempt_id = sa.attempt_id WHERE sa.user_id = %s", (user_id,))
        completed = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) AS count FROM exam_assignments WHERE user_id = %s", (user_id,))
        assigned = cursor.fetchone()['count']
        return jsonify({"success": True, "data": {"completed_exams": completed, "assigned_exams": assigned}}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/profile', methods=['GET'])
@jwt_required()
@role_required(['student', 'admin', 'super_admin'])
def get_profile():
    user_id = get_jwt_identity()
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.email, u.role, u.created_at,
                   CONCAT(up.first_name, ' ', up.last_name) AS name
            FROM users u
            LEFT JOIN user_profiles up ON u.user_id = up.user_id
            WHERE u.user_id = %s
        """, (user_id,))
        user = cursor.fetchone()
        return jsonify({"success": True, "data": user}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/admin/change-password', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def change_password():
    user_id = get_jwt_identity()
    data = request.get_json()
    old_pw = data.get('old_password')
    new_pw = data.get('new_password')

    if not old_pw or not new_pw:
        return jsonify({"success": False, "message": "Both passwords are required"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password'], old_pw):
            if not user or user['password'] != old_pw:
                return jsonify({"success": False, "message": "Current password is incorrect"}), 401

        hashed_new = generate_password_hash(new_pw)
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_new, user_id))
        conn.commit()
        return jsonify({"success": True, "message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# FIX #5: POST /api/student/change-password
@bp.route('/student/change-password', methods=['POST'])
@jwt_required()
@role_required(['student'])
def student_change_password():
    user_id = get_jwt_identity()
    data = request.get_json()
    old_pw = data.get('old_password')
    new_pw = data.get('new_password')

    if not old_pw or not new_pw:
        return jsonify({"success": False, "message": "Both passwords are required"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user or not check_password_hash(user['password'], old_pw):
            if not user or user['password'] != old_pw:
                return jsonify({"success": False, "message": "Current password is incorrect"}), 401

        hashed_new = generate_password_hash(new_pw)
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_new, user_id))
        conn.commit()
        return jsonify({"success": True, "message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


# FIX #8: GET /api/student/statistics
@bp.route('/student/statistics', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_student_statistics():
    user_id = get_jwt_identity()
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS count FROM student_attempts WHERE user_id = %s", (user_id,))
        total_taken = cursor.fetchone()['count']

        cursor.execute("""
            SELECT COALESCE(AVG(r.percentage), 0) AS avg_score
            FROM results r
            JOIN student_attempts sa ON r.attempt_id = sa.attempt_id
            WHERE sa.user_id = %s
        """, (user_id,))
        avg_score = round(cursor.fetchone()['avg_score'], 1)

        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM results r
            JOIN student_attempts sa ON r.attempt_id = sa.attempt_id
            WHERE sa.user_id = %s AND r.percentage >= 50
        """, (user_id,))
        passed = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) AS count FROM exam_assignments WHERE user_id = %s", (user_id,))
        assigned = cursor.fetchone()['count']

        return jsonify({
            "success": True,
            "data": {
                "total_taken": total_taken,
                "average_score": avg_score,
                "passed": passed,
                "failed": total_taken - passed,
                "assigned_exams": assigned
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
