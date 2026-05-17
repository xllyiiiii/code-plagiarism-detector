"""Initialize database with demo accounts and sample data."""
from datetime import datetime
from app import create_app, db
from app.models import User, Course, Enrollment, Assignment

app = create_app()

with app.app_context():
    # Clear existing data
    db.drop_all()
    db.create_all()

    # ---- Users ----
    admin = User(username='admin', role='admin', display_name='系统管理员')
    admin.set_password('admin123')

    teacher = User(username='teacher', role='teacher', display_name='张老师', email='teacher@test.com')
    teacher.set_password('teacher123')

    s1 = User(username='student1', role='student', display_name='张三', email='zhangsan@test.com')
    s1.set_password('123456')
    s2 = User(username='student2', role='student', display_name='李四', email='lisi@test.com')
    s2.set_password('123456')
    s3 = User(username='student3', role='student', display_name='王五', email='wangwu@test.com')
    s3.set_password('123456')

    db.session.add_all([admin, teacher, s1, s2, s3])
    db.session.flush()

    # ---- Course ----
    course = Course(
        name='2026 春 · 数据结构',
        teacher_id=teacher.id,
        invite_code='DS2026',
        semester='2025-2026-2',
        description='数据结构课程实验作业'
    )
    db.session.add(course)
    db.session.flush()

    # ---- Enrollments ----
    db.session.add_all([
        Enrollment(student_id=s1.id, course_id=course.id),
        Enrollment(student_id=s2.id, course_id=course.id),
        Enrollment(student_id=s3.id, course_id=course.id),
    ])
    db.session.flush()

    # ---- Assignment ----
    assignment = Assignment(
        course_id=course.id,
        title='实验一：二叉树的遍历',
        description='实现二叉树的前序、中序、后序遍历，并提交源代码。',
        due_date=datetime(2026, 6, 15, 23, 59, 59),
        allowed_extensions='py,java,c,cpp',
        similarity_threshold=0.70
    )
    db.session.add(assignment)

    db.session.commit()

    print('=' * 50)
    print('  测试账号已就绪')
    print('=' * 50)
    print()
    print('  角色      用户名      密码')
    print('  ───────  ─────────  ─────────')
    print('  管理员    admin       admin123')
    print('  教师      teacher     teacher123')
    print('  学生1     student1    123456')
    print('  学生2     student2    123456')
    print('  学生3     student3    123456')
    print()
    print('  课程邀请码: DS2026')
    print('=' * 50)
