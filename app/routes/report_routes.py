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
    location_details = None

    if form.validate_on_submit():
        report_type = form.report_type.data
        start_date = form.start_date.data
        end_date = form.end_date.data if form.end_date.data else start_date
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
                
                class GrandTotal:
                    def __init__(self, **entries):
                        self.__dict__.update(entries)
                grand_total = GrandTotal(**grand_total_dict)
        
        # --- ↓↓↓ 在這裡新增合併報表總結的邏輯 ↓↓↓ ---
        elif report_type == 'combined_summary_final':
            previous_date = start_date - timedelta(days=1)
            
            today_reports = db.session.query(BusinessDay).options(db.joinedload(BusinessDay.location)).filter(BusinessDay.date == start_date, BusinessDay.status == 'CLOSED').all()
            yesterday_reports = db.session.query(BusinessDay).filter(BusinessDay.date == previous_date, BusinessDay.status == 'CLOSED').all()
            yesterday_data = {report.location_id: report for report in yesterday_reports}

            location_details = []
            grand_total_dict = { 'c': 0, 'b': 0, 'a': 0, 'd': 0, 'e': 0, 'f': 0, 'i': 0, 'g': 0, 'h': 0 }

            for report in today_reports:
                details = {}
                details['location_name'] = report.location.name
                details['c'] = report.opening_cash or 0
                details['b'] = report.total_sales or 0
                details['a'] = report.expected_cash or 0
                details['d'] = report.closing_cash or 0
                details['e'] = report.cash_diff or 0
                details['f'] = (report.donation_total or 0) + (report.other_total or 0)
                details['i'] = report.next_day_opening_cash or 0
                details['g'] = details['d'] + details['f']
                details['h'] = details['g'] - details['i']

                yesterday_report = yesterday_data.get(report.location_id)
                if yesterday_report:
                    expected = yesterday_report.next_day_opening_cash or 0
                    actual = report.opening_cash or 0
                    diff = actual - expected
                    details['j_status'] = '相符' if diff == 0 else '不符'
                    details['j_diff'] = diff
                else:
                    details['j_status'] = '昨日無資料'
                    details['j_diff'] = 0
                
                location_details.append(details)
                for key in grand_total_dict:
                    grand_total_dict[key] += details.get(key, 0)

            results = location_details # 將處理好的資料傳給 results
            
            class GrandTotal:
                def __init__(self, **entries): self.__dict__.update(entries)
            grand_total = GrandTotal(**grand_total_dict)

    return render_template('report/query.html', 
                           form=form, 
                           results=results, 
                           report_type=report_type,
                           grand_total=grand_total)

