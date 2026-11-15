from flask import Flask, render_template, session
from flask import redirect, url_for
app = Flask(__name__)
app.secret_key = 'sdfsfsdfad'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clear_exam.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from extension import db
from access import access_blueprint
from models import *
from control import control_blueprint
from marker import marker_blueprint
from learner import learner_blueprint
app.register_blueprint(access_blueprint, url_prefix='/access')
app.register_blueprint(control_blueprint, url_prefix='/control')
app.register_blueprint(marker_blueprint, url_prefix='/marker')
app.register_blueprint(learner_blueprint, url_prefix='/learner')
db.init_app(app)


@app.route('/logout', methods=['POST', 'GET'])
def sign_out():
    session.pop('user_id', None)
    return redirect(url_for('home_page'))


@app.route('/')
def home_page():
    return render_template('index.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        old_user = Account.query.filter_by(email='admin@gmail.com').first()
        if not old_user:
            new_admin = Account(name='admin', email='admin@gmail.com', password='admin', role='admin')
            db.session.add(new_admin)
            db.session.commit()

    app.run(debug=True)
