from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv
import os

# Import blueprints
from routes.login import bp as login_bp
from routes.dashboard import bp as student_dash_bp
from routes.admin_dashboard import bp as admin_dash_bp
from routes.super_admin_dashboard import bp as super_admin_bp
from routes.exam_portal import bp as exam_portal_bp
from routes.exam_dashboard import bp as exam_dash_bp
from routes.result_page import bp as result_bp
from routes.create_exam import bp as create_exam_bp
from routes.student_management import bp as student_mgmt_bp
from routes.detected_students import bp as detected_students_bp

load_dotenv()

app = Flask(__name__)

# CORS Configuration using FRONTEND_URL from .env
frontend_url = os.getenv('FRONTEND_URL', '*')
CORS(app, resources={r"/api/*": {"origins": frontend_url}})

# JWT Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'super-secret-key-change-this-in-production')
jwt = JWTManager(app)

# Register blueprints with prefixes to match api.js
app.register_blueprint(login_bp, url_prefix='/api')
app.register_blueprint(student_dash_bp, url_prefix='/api')
app.register_blueprint(admin_dash_bp, url_prefix='/api')
app.register_blueprint(super_admin_bp, url_prefix='/api')
app.register_blueprint(exam_portal_bp, url_prefix='/api')
app.register_blueprint(exam_dash_bp, url_prefix='/api')
app.register_blueprint(result_bp, url_prefix='/api')
app.register_blueprint(create_exam_bp, url_prefix='/api')
app.register_blueprint(student_mgmt_bp, url_prefix='/api')
app.register_blueprint(detected_students_bp, url_prefix='/api')

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is running"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
