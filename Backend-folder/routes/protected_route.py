from flask import Blueprint, jsonify, request

bp = Blueprint('protected_route', __name__)

@bp.route('/protected_route', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the protected_route endpoint"})
