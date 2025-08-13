from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, TextAreaField, SelectMultipleField, widgets
from wtforms.validators import DataRequired, Length, Regexp, EqualTo, ValidationError
# *** 修正點：在這裡匯入 Role 模型 ***
from .models import User, Role

class LoginForm(FlaskForm):
    username = StringField('帳號', validators=[DataRequired(message="請輸入帳號。")])
    password = PasswordField('密碼', validators=[DataRequired(message="請輸入密碼。")])
    submit = SubmitField('登入')

class LocationForm(FlaskForm):
    name = StringField('據點名稱', validators=[DataRequired(message="請輸入據點名稱。"), Length(max=50)])
    slug = StringField('URL Slug', validators=[
        DataRequired(message="請輸入 URL Slug。"), 
        Length(max=50),
        Regexp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', message='Slug 只能包含小寫英文、數字和連字號 (-)，且不能以連字號開頭或結尾。')
    ])
    submit = SubmitField('儲存')

class StartDayForm(FlaskForm):
    opening_cash = FloatField('開店準備金 (元)', validators=[
        DataRequired(message="請輸入開店準備金。")
    ])
    location_notes = TextAreaField('備註 (選填)', validators=[Length(max=200)])
    submit = SubmitField('確認開始營業')

class CloseDayForm(FlaskForm):
    submit = SubmitField('送出盤點結果並預覽報表')

class ConfirmReportForm(FlaskForm):
    submit = SubmitField('確認存檔並結束本日營業')

class RoleForm(FlaskForm):
    """新增/編輯角色的表單"""
    name = StringField('角色名稱', validators=[DataRequired(), Length(1, 64)])
    permissions = SelectMultipleField(
        '權限', 
        coerce=str, 
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField('儲存')

class UserForm(FlaskForm):
    """新增/編輯使用者的表單"""
    username = StringField('使用者名稱', validators=[DataRequired(), Length(1, 64), Regexp('^[A-Za-z][A-Za-z0-9_.]*$', 0, '使用者名稱只能包含字母、數字、點或底線')])
    password = PasswordField('密碼', validators=[
        EqualTo('password2', message='兩次輸入的密碼必須相符。')
    ])
    password2 = PasswordField('確認密碼')
    roles = SelectMultipleField(
        '角色', 
        coerce=int,
        widget=widgets.ListWidget(prefix_label=False), 
        option_widget=widgets.CheckboxInput()
    )
    submit = SubmitField('儲存')

    def __init__(self, user=None, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.original_user = user
        # 現在 Role 已經被匯入，所以這裡可以正常運作
        self.roles.choices = [(r.id, r.name) for r in Role.query.order_by('name').all()]

    def validate_username(self, field):
        if self.original_user is None or self.original_user.username != field.data:
            if User.query.filter_by(username=field.data).first():
                 raise ValidationError('此使用者名稱已被使用。')
