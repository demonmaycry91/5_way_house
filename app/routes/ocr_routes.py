from flask import Blueprint

bp = Blueprint('ocr', __name__, url_prefix='/ocr')


@bp.route('/')
def ocr_page():
    return "這是 OCR 頁面。"
