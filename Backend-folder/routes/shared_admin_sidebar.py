from flask import Blueprint, jsonify, request

bp = Blueprint('shared_admin_sidebar', __name__)

@bp.route('/shared_admin_sidebar', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the shared_admin_sidebar endpoint"})
