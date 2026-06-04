from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from werkzeug.security import generate_password_hash

bp = Blueprint('student_management', __name__)

@bp.route('/admin/students/list', methods=['GET'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def get_students():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 500
    try:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT u.user_id as id, u.email, u.created_at, 
                   CONCAT(up.first_name, ' ', up.last_name) as name 
            FROM users u 
            JOIN user_profiles up ON u.user_id = up.user_id 
            WHERE u.role = 'student'
            ORDER BY u.created_at DESC
        """
        cursor.execute(query)
        return jsonify({"success": True, "students": cursor.fetchall()}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/admin/students/create', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def create_student():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password')
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    
    if not email or not password or not first_name:
        return jsonify({"success": False, "message": "Name, email and password are required"}), 400

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        # 1. Create User
        hashed_pw = generate_password_hash(password)
        cursor.execute("INSERT INTO users (email, password, role) VALUES (%s, %s, 'student')", (email, hashed_pw))
        user_id = cursor.lastrowid
        
        # 2. Create Profile
        cursor.execute("INSERT INTO user_profiles (user_id, first_name, last_name) VALUES (%s, %s, %s)", (user_id, first_name, last_name))
        
        conn.commit()
        return jsonify({"success": True, "data": {"id": user_id}, "message": "Student created successfully"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/admin/students/<int:student_id>', methods=['PUT'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def update_student(student_id):
    data = request.get_json()
    password = data.get('password')
    
    if not password:
        return jsonify({"success": False, "message": "New password is required"}), 400

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        hashed_pw = generate_password_hash(password)
        cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_pw, student_id))
        conn.commit()
        return jsonify({"success": True, "message": "Password updated successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/admin/students/<int:student_id>', methods=['DELETE'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def delete_student(student_id):
    user_id = get_jwt_identity()
    # We can check the role here if we want different behavior, 
    # but the frontend already handles the 'request vs delete' logic.
    # If the frontend calls this, we assume it's a direct delete (super_admin).
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = %s", (student_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Student deleted successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()

@bp.route('/admin/students/bulk-create', methods=['POST'])
@jwt_required()
@role_required(['admin', 'super_admin'])
def bulk_create_students():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file uploaded"}), 400
    
    file = request.files['file']
    content = file.read().decode('utf-8')
    lines = content.split('\n')
    
    created = []
    skipped = []
    errors = []
    
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        for line in lines:
            if not line.strip(): continue
            parts = line.split(',')
            if len(parts) < 2:
                errors.append({"line": line, "error": "Invalid format"})
                continue
            
            email = parts[1].strip().lower()
            password = parts[2].strip() if len(parts) > 2 else "Student@123"
            name = parts[0].strip()
            
            try:
                # Check if exists
                cursor.execute("SELECT user_id FROM users WHERE email = %s", (email,))
                if cursor.fetchone():
                    skipped.append(email)
                    continue
                
                hashed_pw = generate_password_hash(password)
                cursor.execute("INSERT INTO users (email, password, role) VALUES (%s, %s, 'student')", (email, hashed_pw))
                uid = cursor.lastrowid
                
                fname = name.split(' ')[0] if name else 'Student'
                lname = ' '.join(name.split(' ')[1:]) if name else ''
                cursor.execute("INSERT INTO user_profiles (user_id, first_name, last_name) VALUES (%s, %s, %s)", (uid, fname, lname))
                created.append({"email": email, "password": password})
            except Exception as e:
                errors.append({"email": email, "error": str(e)})
        
        conn.commit()
        return jsonify({"success": True, "data": {"created": created, "skipped": skipped, "errors": errors, "summary": {"created": len(created)}}}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        conn.close()
