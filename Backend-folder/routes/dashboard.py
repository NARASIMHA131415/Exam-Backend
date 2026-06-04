from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('dashboard', __name__)

@bp.route('/student/dashboard', methods=['GET'])
@jwt_required()
@role_required(['student'])
def get_student_dashboard():
    user_id = get_jwt_identity()
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM results WHERE user_id = %s", (user_id,))
        completed = cursor.fetchone()['count']
        cursor.execute("SELECT COUNT(*) as count FROM exam_assignments WHERE user_id = %s", (user_id,))
        assigned = cursor.fetchone()['count']
        return jsonify({"success": True, "data": {"completed_exams": completed, "assigned_exams": assigned}}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/profile', methods=['GET'])
@jwt_required()
@role_required(['student', 'admin', 'super_admin'])
def get_profile():
    user_id = get_jwt_identity()
    conn = db.get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, role FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        return jsonify({"success": True, "data": user}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
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
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user or not check_password_hash(user['password'], old_pw):
            return jsonify({"success": False, "message": "Current password is incorrect"}), 401
        
        hashed_new = generate_password_hash(new_pw)
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_new, user_id))
        conn.commit()
        return jsonify({"success": True, "message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
