from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Length, Regexp, NumberRange

class LoginForm(FlaskForm):
    """使用者登入表單"""
    username = StringField('帳號', validators=[DataRequired(message="請輸入帳號。")])
    password = PasswordField('密碼', validators=[DataRequired(message="請輸入密碼。")])
    submit = SubmitField('登入')

class LocationForm(FlaskForm):
    """據點新增/編輯表單"""
    name = StringField('據點名稱', validators=[DataRequired(message="請輸入據點名稱。"), Length(max=50)])
    slug = StringField('URL Slug', validators=[
        DataRequired(message="請輸入 URL Slug。"), 
        Length(max=50),
        # 使用正規表示式來驗證 slug 格式是否正確
        Regexp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', message='Slug 只能包含小寫英文、數字和連字號 (-)，且不能以連字號開頭或結尾。')
    ])
    submit = SubmitField('儲存')

class StartDayForm(FlaskForm):
    """開店作業表單"""
    opening_cash = FloatField('開店準備金 (元)', validators=[
        DataRequired(message="請輸入開店準備金。"),
        NumberRange(min=0, message="準備金不能為負數。")
    ])
    location_notes = TextAreaField('備註 (選填)', validators=[Length(max=200)])
    submit = SubmitField('確認開始營業')

class CloseDayForm(FlaskForm):
    """日結作業表單 - 這個表單比較特別，我們只需要 CSRF token，欄位由前端 JS 動態處理"""
    # 我們可以定義一個隱藏欄位來接收前端計算的總額，但在此案例中，我們主要目的是取得 CSRF token
    # 因此，即使沒有明確的欄位，Flask-WTF 也會幫我們處理 token
    submit = SubmitField('送出盤點結果並預覽報表')

class ConfirmReportForm(FlaskForm):
    """確認報表的表單，主要用於 CSRF 保護"""
    submit = SubmitField('確認存檔並結束本日營業')