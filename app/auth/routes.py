from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('courses.index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not getattr(user, 'is_active', True):
                flash('该账号已被禁用，请联系管理员。')
                return render_template('login.html')
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('courses.index'))
        flash('用户名或密码错误。')
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        invite_code = request.form.get('invite_code')

        # Validate invite code
        from app.models import Course
        course = Course.query.filter_by(invite_code=invite_code).first()
        if not course:
            flash('邀请码无效。')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash('用户名已存在。')
            return render_template('register.html')

        user = User(username=username, role='student')
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        from app.models import Enrollment
        enrollment = Enrollment(student_id=user.id, course_id=course.id)
        db.session.add(enrollment)
        db.session.commit()

        flash('注册成功，请登录。')
        return redirect(url_for('auth.login'))

    return render_template('register.html')
