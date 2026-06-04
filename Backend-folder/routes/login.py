from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import check_password_hash, generate_password_hash
from database import db
import os

bp = Blueprint('login', __name__)


@bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required"}), 400

    # --- SUPER ADMIN ENV OVERRIDE ---
    env_super_email = os.getenv('SUPER_ADMIN_EMAIL', '').lower()
    env_super_pw = os.getenv('SUPER_ADMIN_PASSWORD', '')

    if env_super_email and email == env_super_email and password == env_super_pw:
        access_token = create_access_token(
            identity="1",
            additional_claims={"role": "super_admin"}
        )
        return jsonify({
            "success": True,
            "message": "Login successful (Super Admin)",
            "data": {
                "token": access_token,
                "user": {
                    "id": 1,
                    "email": email,
                    "role": "super_admin",
                    "name": "Super Admin"
                }
            }
        }), 200
    # -------------------------------

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503

    try:
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT u.user_id, u.email, u.password, u.role,
                   CONCAT(up.first_name, ' ', up.last_name) AS name
            FROM users u
            LEFT JOIN user_profiles up ON u.user_id = up.user_id
            WHERE u.email = %s
        """
        cursor.execute(query, (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401

        # FIX #3: Removed plain text password fallback — only hashed passwords allowed
        if not check_password_hash(user['password'], password):
            return jsonify({"success": False, "message": "Invalid email or password"}), 401

        # Create JWT Token
        access_token = create_access_token(
            identity=str(user['user_id']),
            additional_claims={"role": user['role']}
        )

        return jsonify({
            "success": True,
            "message": "Login successful",
            "data": {
                "token": access_token,
                "user": {
                    "id": user['user_id'],
                    "email": user['email'],
                    "role": user['role'],
                    "name": user['name'] or user['email'].split('@')[0]
                }
            }
        }), 200

    except Exception as e:
        print(f"Login Error: {e}")
        return jsonify({"success": False, "message": "An internal server error occurred"}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    data = request.get_json()
    old_password = data.get('oldPassword')
    new_password = data.get('newPassword')

    if not old_password or not new_password:
        return jsonify({"success": False, "message": "Old and new passwords are required"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "message": "User not found"}), 404

        # FIX #3: Only hashed password verification
        if not check_password_hash(user['password'], old_password):
            return jsonify({"success": False, "message": "Current password is incorrect"}), 401

        hashed_new_pw = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_new_pw, user_id))
        conn.commit()

        return jsonify({"success": True, "message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
