#课程接口
import random
import string

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import Course, Enrollment, User
from app.utils.decorators import role_required

courses_bp = Blueprint('courses', __name__)


def _generate_invite_code(length=8):
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


@courses_bp.route('/')
@login_required
def index():
    if current_user.role == 'admin':
        courses = Course.query.order_by(Course.created_at.desc()).all()
    elif current_user.role == 'teacher':
        courses = Course.query.filter_by(teacher_id=current_user.id)\
            .order_by(Course.created_at.desc()).all()
    else:
        enrolled_ids = [e.course_id for e in current_user.enrollments.all()]
        courses = Course.query.filter(Course.id.in_(enrolled_ids))\
            .order_by(Course.created_at.desc()).all() if enrolled_ids else []
    return render_template('courses/index.html', courses=courses)


@courses_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required('teacher', 'admin')
def create():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        semester = request.form.get('semester', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('课程名称不能为空。')
            return render_template('courses/create.html')

        # Generate unique invite code
        invite_code = _generate_invite_code()
        while Course.query.filter_by(invite_code=invite_code).first():
            invite_code = _generate_invite_code()

        course = Course(
            name=name,
            teacher_id=current_user.id,
            invite_code=invite_code,
            semester=semester,
            description=description
        )
        db.session.add(course)
        db.session.commit()
        flash(f'课程 "{name}" 创建成功！邀请码：{invite_code}')
        return redirect(url_for('courses.index'))

    return render_template('courses/create.html')


@courses_bp.route('/<int:course_id>')
@login_required
def detail(course_id):
    course = Course.query.get_or_404(course_id)
    from app.models import Assignment
    students = User.query.join(Enrollment).filter(
        Enrollment.course_id == course.id
    ).order_by(User.username).all()
    assignments = course.assignments.order_by(
        Assignment.created_at.desc()
    ).all()
    return render_template('courses/detail.html', course=course,
                           students=students, assignments=assignments)


@courses_bp.route('/<int:course_id>/archive', methods=['POST'])
@login_required
@role_required('teacher', 'admin')
def archive(course_id):
    course = Course.query.get_or_404(course_id)
    course.is_archived = not course.is_archived
    db.session.commit()
    state = '已归档' if course.is_archived else '已取消归档'
    flash(f'课程 "{course.name}" {state}。')
    return redirect(url_for('courses.detail', course_id=course.id))


@courses_bp.route('/join', methods=['GET', 'POST'])
@login_required
@role_required('student')
def join():
    if request.method == 'POST':
        invite_code = request.form.get('invite_code', '').strip().upper()
        course = Course.query.filter_by(invite_code=invite_code).first()

        if not course:
            flash('邀请码无效。')
            return render_template('courses/join.html')

        if course.is_archived:
            flash('该课程已归档，无法加入。')
            return render_template('courses/join.html')

        existing = Enrollment.query.filter_by(
            student_id=current_user.id, course_id=course.id
        ).first()
        if existing:
            flash('你已加入该课程。')
            return redirect(url_for('courses.detail', course_id=course.id))

        enrollment = Enrollment(student_id=current_user.id, course_id=course.id)
        db.session.add(enrollment)
        db.session.commit()
        flash(f'成功加入课程 "{course.name}"！')
        return redirect(url_for('courses.detail', course_id=course.id))

    return render_template('courses/join.html')
