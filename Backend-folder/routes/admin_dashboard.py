from flask import Blueprint, jsonify, request

bp = Blueprint('admin_dashboard', __name__)

@bp.route('/admin_dashboard', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the admin_dashboard endpoint"})
