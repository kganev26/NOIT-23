from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ===========================
# MODELS
# ===========================
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    xp = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    study_programs = db.relationship('StudyProgram', backref='user', lazy=True)
    missions = db.relationship('Mission', backref='user', lazy=True)

class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    duration = db.Column(db.Integer)
    xp_reward = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    remaining_seconds = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class StudyProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20))
    subjects = db.Column(db.String(500)) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===========================
# AUTH ROUTES
# ===========================
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            # Flashing the message specifically as an 'error'
            flash('Invalid username or password!', 'error')
            
    return render_template('login.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('User already exists!', 'error')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ===========================
# DASHBOARD & MISSION ROUTES
# ===========================
@app.route('/dashboard')
@login_required
def dashboard():
    missions = Mission.query.filter_by(user_id=current_user.id, completed=False).all()
    raw_programs = StudyProgram.query.filter_by(user_id=current_user.id).all()
    
    # Transposed format for table: {'Monday_1': 'Math'}
    formatted_program = {}
    for p in raw_programs:
        subject_list = p.subjects.split(',') if p.subjects else []
        for index, subject in enumerate(subject_list):
            key = f"{p.day}_{index + 1}"
            formatted_program[key] = subject
    
    return render_template('dashboard.html', 
                           missions=missions, 
                           user=current_user, 
                           programs=formatted_program)
import random # Add this at the top with your other imports

@app.route('/generate_missions', methods=['POST'])
@login_required
def generate_missions():
    # 1. Overwrite: Delete existing incomplete missions for this user
    Mission.query.filter_by(user_id=current_user.id, completed=False).delete()

    # 2. Get the day selected by the user
    selected_day = request.form.get('selected_day')
    
    # 3. Get the program for that day
    program = StudyProgram.query.filter_by(user_id=current_user.id, day=selected_day).first()
    
    if program and program.subjects:
        # Split and clean the subjects list
        subject_list = [s.strip() for s in program.subjects.split(',') if s.strip()]
        
        # 4. RANDOM LOGIC: Shuffle the list and pick the first 3
        random.shuffle(subject_list)
        selected_subjects = subject_list[:3] # Takes up to 3 subjects
        
        for subject in selected_subjects:
            new_mission = Mission(
                title=f"Study Session: {subject}",
                duration=45,
                xp_reward=50,
                user_id=current_user.id
            )
            db.session.add(new_mission)
        
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/mission/<int:mission_id>')
@login_required
def mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    if mission.completed: return redirect(url_for('dashboard'))
    if not mission.remaining_seconds:
        mission.remaining_seconds = mission.duration * 60
        db.session.commit()
    return render_template('mission.html', mission=mission)

@app.route('/complete_mission/<int:mission_id>', methods=['POST'])
@login_required
def complete_mission(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    mission.completed = True
    mission.remaining_seconds = 0
    current_user.xp += mission.xp_reward
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/study_program', methods=['POST'])
@login_required
def study_program():
    StudyProgram.query.filter_by(user_id=current_user.id).delete()
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    for day in days:
        subjects = []
        for i in range(1, 9):
            val = request.form.get(f'{day}_{i}')
            subjects.append(val if val else "")
        while subjects and not subjects[-1]: subjects.pop()
        if subjects:
            new_prog = StudyProgram(day=day, subjects=','.join(subjects), user_id=current_user.id)
            db.session.add(new_prog)
    db.session.commit()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)