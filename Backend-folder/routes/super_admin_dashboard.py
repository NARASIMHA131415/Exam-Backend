from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from utils.auth import role_required
from database import db
from werkzeug.security import generate_password_hash

bp = Blueprint('super_admin', __name__)


@bp.route('/super_admin/admins/list', methods=['GET'])
@jwt_required()
@role_required(['super_admin'])
def get_admins():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                u.user_id AS id,
                u.email,
                u.role,
                u.created_at,
                CONCAT(up.first_name, ' ', up.last_name) AS name
            FROM users u
            LEFT JOIN user_profiles up ON u.user_id = up.user_id
            WHERE u.role IN ('admin', 'super_admin')
        """)
        admins = cursor.fetchall()
        return jsonify({"success": True, "admins": admins}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/super_admin/create-admin', methods=['POST'])
@jwt_required()
@role_required(['super_admin'])
def create_admin():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password')
    name = data.get('name', '').strip()

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        hashed_pw = generate_password_hash(password)

        cursor.execute("INSERT INTO users (email, password, role) VALUES (%s, %s, 'admin')", (email, hashed_pw))
        user_id = cursor.lastrowid

        first_name = name.split(' ')[0] if name else 'Admin'
        last_name = ' '.join(name.split(' ')[1:]) if name else ''
        cursor.execute("INSERT INTO user_profiles (user_id, first_name, last_name) VALUES (%s, %s, %s)", (user_id, first_name, last_name))

        conn.commit()
        return jsonify({"success": True, "message": "Admin created successfully"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/super_admin/admins/bulk-create', methods=['POST'])
@jwt_required()
@role_required(['super_admin'])
def bulk_create_admins():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file uploaded"}), 400

    file = request.files['file']
    content = file.read().decode('utf-8')
    lines = content.split('\n')

    created = []
    skipped = []
    errors = []

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(',')
            if len(parts) < 2:
                errors.append({"line": line, "error": "Invalid format"})
                continue

            email = parts[1].strip().lower()
            password = parts[2].strip() if len(parts) > 2 else "Admin@123"
            name = parts[0].strip()

            try:
                hashed_pw = generate_password_hash(password)
                cursor.execute("INSERT INTO users (email, password, role) VALUES (%s, %s, 'admin')", (email, hashed_pw))
                uid = cursor.lastrowid

                fname = name.split(' ')[0] if name else 'Admin'
                lname = ' '.join(name.split(' ')[1:]) if name else ''
                cursor.execute("INSERT INTO user_profiles (user_id, first_name, last_name) VALUES (%s, %s, %s)", (uid, fname, lname))
                created.append({"email": email, "password": password})
            except Exception as e:
                errors.append({"email": email, "error": str(e)})

        conn.commit()
        return jsonify({
            "success": True,
            "data": {"created": created, "skipped": skipped, "errors": errors, "summary": {"created": len(created)}}
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/super_admin/admins/<int:admin_id>', methods=['DELETE'])
@jwt_required()
@role_required(['super_admin'])
def delete_admin(admin_id):
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = %s", (admin_id,))
        conn.commit()
        return jsonify({"success": True, "message": "Admin deleted"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/super_admin/admins/<int:admin_id>', methods=['PUT'])
@jwt_required()
@role_required(['super_admin'])
def update_admin(admin_id):
    data = request.get_json()

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND role IN ('admin', 'super_admin')", (admin_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Admin not found"}), 404

        if data.get('password'):
            hashed_pw = generate_password_hash(data['password'])
            cursor.execute("UPDATE users SET password = %s WHERE user_id = %s", (hashed_pw, admin_id))

        if data.get('email'):
            cursor.execute("UPDATE users SET email = %s WHERE user_id = %s", (data['email'].strip().lower(), admin_id))

        if data.get('name'):
            name = data['name'].strip()
            first_name = name.split(' ')[0]
            last_name = ' '.join(name.split(' ')[1:])
            cursor.execute("UPDATE user_profiles SET first_name = %s, last_name = %s WHERE user_id = %s",
                           (first_name, last_name, admin_id))

        conn.commit()
        return jsonify({"success": True, "message": "Admin updated successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/superadmin/deletion-requests', methods=['GET'])
@jwt_required()
@role_required(['super_admin'])
def get_deletion_requests():
    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                dr.request_id AS id,
                dr.target_id,
                dr.type,
                dr.status,
                dr.reason,
                dr.created_at,
                u_target.email AS student_email,
                CONCAT(up_target.first_name, ' ', up_target.last_name) AS student_name,
                CONCAT(up_req.first_name, ' ', up_req.last_name) AS admin_name
            FROM deletion_requests dr
            JOIN users u_target ON dr.target_id = u_target.user_id
            JOIN user_profiles up_target ON u_target.user_id = up_target.user_id
            JOIN users u_req ON dr.requested_by = u_req.user_id
            JOIN user_profiles up_req ON u_req.user_id = up_req.user_id
        """)
        requests = cursor.fetchall()

        for req in requests:
            cursor.execute("""
                SELECT COUNT(*) AS count FROM proctoring_violations pv
                JOIN student_attempts sa ON pv.attempt_id = sa.attempt_id
                WHERE sa.user_id = %s
            """, (req['target_id'],))
            violation_count = cursor.fetchone()['count']
            req['has_violations'] = violation_count > 0

        for req in requests:
            req.pop('target_id', None)

        return jsonify({"success": True, "requests": requests}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()


@bp.route('/superadmin/deletion-requests/<int:request_id>/<action>', methods=['PUT'])
@jwt_required()
@role_required(['super_admin'])
def handle_deletion_request(request_id, action):
    if action not in ['approve', 'reject']:
        return jsonify({"success": False, "message": "Invalid action"}), 400

    conn = db.get_connection()
    if conn is None:
        return jsonify({"success": False, "message": "Database connection failed"}), 503
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT target_id, type FROM deletion_requests WHERE request_id = %s", (request_id,))
        req = cursor.fetchone()

        if not req:
            return jsonify({"success": False, "message": "Request not found"}), 404

        if action == 'approve':
            target_id = req['target_id']
            if req['type'] == 'student':
                # FIX #3: Delete ALL related data in correct order
                # 1. Delete student answers (references attempts)
                cursor.execute(
                    "DELETE FROM student_answers WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE user_id = %s)",
                    (target_id,)
                )
                # 2. Delete proctoring violations (references attempts)
                cursor.execute(
                    "DELETE FROM proctoring_violations WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE user_id = %s)",
                    (target_id,)
                )
                # 3. Delete question attempt logs (references attempts)
                cursor.execute(
                    "DELETE FROM question_attempt_logs WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE user_id = %s)",
                    (target_id,)
                )
                # 4. Delete results (references attempts)
                cursor.execute(
                    "DELETE FROM results WHERE attempt_id IN (SELECT attempt_id FROM student_attempts WHERE user_id = %s)",
                    (target_id,)
                )
                # 5. Delete attempts
                cursor.execute("DELETE FROM student_attempts WHERE user_id = %s", (target_id,))
                # 6. Delete exam assignments
                cursor.execute("DELETE FROM exam_assignments WHERE user_id = %s", (target_id,))
                # 7. Delete other deletion requests for this student
                cursor.execute("DELETE FROM deletion_requests WHERE target_id = %s AND type = 'student'", (target_id,))
                # 8. Delete profile
                cursor.execute("DELETE FROM user_profiles WHERE user_id = %s", (target_id,))
                # 9. Delete user (must be last)
                cursor.execute("DELETE FROM users WHERE user_id = %s", (target_id,))
            elif req['type'] == 'result':
                # Delete result and related data
                cursor.execute("DELETE FROM proctoring_violations WHERE attempt_id = %s", (target_id,))
                cursor.execute("DELETE FROM question_attempt_logs WHERE attempt_id = %s", (target_id,))
                cursor.execute("DELETE FROM student_answers WHERE attempt_id = %s", (target_id,))
                cursor.execute("DELETE FROM results WHERE attempt_id = %s", (target_id,))

            cursor.execute("UPDATE deletion_requests SET status = 'Approved' WHERE request_id = %s", (request_id,))
        else:
            cursor.execute("UPDATE deletion_requests SET status = 'Rejected' WHERE request_id = %s", (request_id,))

        conn.commit()
        return jsonify({"success": True, "message": f"Request {action}d successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if conn:
            conn.close()
