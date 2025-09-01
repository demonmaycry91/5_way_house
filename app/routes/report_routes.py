from flask import Blueprint, render_template, request
from flask_login import login_required
from ..models import BusinessDay, Transaction, TransactionItem, Location
from ..forms import ReportQueryForm
from .. import db
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from datetime import date, timedelta

bp = Blueprint('report', __name__, url_prefix='/report')

@bp.route('/query', methods=['GET', 'POST'])
@login_required
def query():
    form = ReportQueryForm()
    results = None
    report_type = None
    grand_total = None

    if form.validate_on_submit():
        report_type = form.report_type.data
        start_date = form.start_date.data
        end_date = form.end_date.data
        location_id = form.location_id.data

        if report_type == 'daily_summary':
            query = db.session.query(BusinessDay).options(
                db.joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date.between(start_date, end_date),
                BusinessDay.status == 'CLOSED'
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(BusinessDay.date.desc(), BusinessDay.location_id).all()

        elif report_type == 'transaction_log':
            query = db.session.query(Transaction).join(BusinessDay).options(
                selectinload(Transaction.items).selectinload(TransactionItem.category),
                db.joinedload(Transaction.business_day).joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date == start_date,
                BusinessDay.status == 'CLOSED'
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(Transaction.timestamp).all()

        elif report_type == 'combined_summary':
            results = db.session.query(
                BusinessDay.date,
                func.sum(BusinessDay.total_sales).label('total_sales'),
                func.sum(BusinessDay.cash_diff).label('cash_diff'),
                func.sum(BusinessDay.total_transactions).label('total_transactions'),
                func.sum(BusinessDay.total_items).label('total_items')
            ).filter(
                BusinessDay.date.between(start_date, end_date),
                BusinessDay.status == 'CLOSED'
            ).group_by(BusinessDay.date).order_by(BusinessDay.date.desc()).all()

        elif report_type == 'daily_cash_summary':
            query = db.session.query(BusinessDay).options(
                db.joinedload(BusinessDay.location)
            ).filter(
                BusinessDay.date == start_date,
                BusinessDay.status == 'CLOSED'
            )
            if location_id != 'all':
                query = query.filter(BusinessDay.location_id == location_id)
            results = query.order_by(BusinessDay.location_id).all()

            if results:
                grand_total_dict = {
                    'opening_cash': sum(r.opening_cash or 0 for r in results),
                    'total_sales': sum(r.total_sales or 0 for r in results),
                    'expected_cash': sum(r.expected_cash or 0 for r in results),
                    'closing_cash': sum(r.closing_cash or 0 for r in results),
                    'cash_diff': sum(r.cash_diff or 0 for r in results),
                    'donation_total': sum(r.donation_total or 0 for r in results),
                    'other_total': sum(r.other_total or 0 for r in results),
                }
                grand_total_dict['other_cash'] = grand_total_dict['donation_total'] + grand_total_dict['other_total']
                
                # Convert dictionary to an object-like structure for template compatibility
                class GrandTotal:
                    def __init__(self, **entries):
                        self.__dict__.update(entries)
                grand_total = GrandTotal(**grand_total_dict)


    return render_template('report/query.html', 
                           form=form, 
                           results=results, 
                           report_type=report_type,
                           grand_total=grand_total)

