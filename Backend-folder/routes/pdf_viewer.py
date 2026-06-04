from flask import Blueprint, jsonify, request

bp = Blueprint('pdf_viewer', __name__)

@bp.route('/pdf_viewer', methods=['GET'])
def index():
    return jsonify({"message": "Welcome to the pdf_viewer endpoint"})
