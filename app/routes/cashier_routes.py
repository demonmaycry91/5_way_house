from flask import Blueprint

bp = Blueprint('cashier', __name__, url_prefix='/cashier')


@bp.route('/')
def cashier_page():
    return "這是收銀機頁面。"
