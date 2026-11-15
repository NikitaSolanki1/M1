from flask import Blueprint
from flask import request
from models import Account
from extension import db
from flask import redirect, render_template, url_for, session


access_blueprint = Blueprint('access', __name__)


@access_blueprint.route('/register', methods=['POST', 'GET'])
def sign_up():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        user = Account(name=name, email=email, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('access.sign_in'))
    return render_template('/access/register.html')


@access_blueprint.route('/login', methods=['POST', 'GET'])
def sign_in():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = Account.query.filter_by(email=email).first()
        if user and user.password == password:
            if user.role != 'admin' and user.is_active is False:
                return render_template('/access/login.html', error='Your account is blocked.')
            if user.role == 'examinor' and not user.is_verified:
                return render_template('/access/login.html', error='Your account is waiting for admin approval.')
            session['user_id'] = user.id
            session['role'] = user.role
            if user.role == 'admin':
                return redirect(url_for('control.control_home'))
            if user.role == 'examinor':
                return redirect(url_for('marker.marker_home'))
            if user.role == 'student':
                return redirect(url_for('learner.learner_home'))
        else:
            return render_template('/access/login.html', error='Wrong email or password')

    error = None
    if request.args.get('pending'):
        error = 'Your account is waiting for admin approval.'
    return render_template('/access/login.html', error=error)
