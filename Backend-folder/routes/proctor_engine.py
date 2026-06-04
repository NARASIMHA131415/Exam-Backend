from flask import Blueprint, jsonify, request

bp = Blueprint('proctor_engine', __name__)

@bp.route('/proctor_engine', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the proctor_engine endpoint"})
