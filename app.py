from flask import Flask, render_template, redirect, url_for, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)

class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    xp_reward = db.Column(db.Integer, default=50)
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(username=request.form['username'], password=request.form['password'])
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    missions = Mission.query.filter_by(user_id=current_user.id, completed=False).all()
    return render_template('dashboard.html', user=current_user, missions=missions)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/generate-missions')
@login_required
def generate_missions():
    missions = [
        Mission(title="25 минути учене", xp_reward=50, user_id=current_user.id),
        Mission(title="Завърши домашното по математика", xp_reward=70, user_id=current_user.id),
        Mission(title="Прочети 1 глава от книга", xp_reward=60, user_id=current_user.id)
    ]
    db.session.add_all(missions)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/complete-mission/<int:mission_id>', methods=['POST'])
@login_required
def complete_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    if mission.user_id == current_user.id and not mission.completed:
        mission.completed = True
        current_user.xp += mission.xp_reward
        if current_user.xp >= current_user.level * 100:
            current_user.level += 1
        db.session.commit()
    return 'OK'


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
