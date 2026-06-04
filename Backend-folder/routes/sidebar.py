from flask import Blueprint, jsonify, request

bp = Blueprint('sidebar', __name__)

@bp.route('/sidebar', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the sidebar endpoint"})
