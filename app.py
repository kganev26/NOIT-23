from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import json
import random
import google.generativeai as genai

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
    duration = db.Column(db.Integer)      # <--- Make sure this line exists!
    xp_reward = db.Column(db.Integer)
    completed = db.Column(db.Boolean, default=False)
    remaining_seconds = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class StudyProgram(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20))
    subjects = db.Column(db.String(500)) 
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_ai = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
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
    
    # --- AI ANALYTICS LOGIC ---
    # Get all missions (completed and incomplete) to calculate stats
    all_missions = Mission.query.filter_by(user_id=current_user.id).all()
    
    subject_stats = {}
    for m in all_missions:
        # Extract subject name from title (e.g., "Study Session: Math" -> "Math")
        subj = m.title.replace("Study Session: ", "")
        if subj not in subject_stats:
            subject_stats[subj] = {'total': 0, 'completed': 0}
        
        subject_stats[subj]['total'] += 1
        if m.completed:
            subject_stats[subj]['completed'] += 1

    # Find the weakest subject (lowest completion percentage)
    weakest_subject = "None yet"
    lowest_rate = 101
    
    for subj, stats in subject_stats.items():
        rate = (stats['completed'] / stats['total']) * 100
        if rate < lowest_rate:
            lowest_rate = rate
            weakest_subject = subj

    # Re-using your existing program logic
    raw_programs = StudyProgram.query.filter_by(user_id=current_user.id).all()
    formatted_program = {}
    for p in raw_programs:
        subject_list = p.subjects.split(',') if p.subjects else []
        for index, subject in enumerate(subject_list):
            key = f"{p.day}_{index + 1}"
            formatted_program[key] = subject
    
    return render_template('dashboard.html', 
                           missions=missions, 
                           user=current_user, 
                           programs=formatted_program,
                           weakest_subject=weakest_subject,
                           stats=subject_stats)

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
                title=f"{subject}",
                duration=45,
                xp_reward=50,
                user_id=current_user.id
            )
            db.session.add(new_mission)
        
        db.session.commit()
    
    return redirect(url_for('dashboard'))

@app.route('/pause_mission/<int:mission_id>', methods=['POST'])
@login_required
def pause_mission(mission_id):
    # This receives the JSON from your JavaScript fetch/beacon
    data = request.get_json()
    mission = Mission.query.get_or_404(mission_id)
    
    # Security check: make sure the mission belongs to the current user
    if mission.user_id == current_user.id:
        new_seconds = data.get('remaining_seconds')
        if new_seconds is not None:
            mission.remaining_seconds = int(new_seconds)
            db.session.commit()
            return jsonify({"status": "success", "saved": mission.remaining_seconds})
            
    return jsonify({"status": "error"}), 400

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

@app.route('/add_bonus_xp', methods=['POST'])
@login_required
def add_bonus_xp():
    data = request.get_json()
    amount = data.get('xp', 2)
    subject = data.get('subject', 'General')

    # Security: Max bonus per request to prevent cheating
    if amount > 10: amount = 10

    current_user.xp += amount
    
    # Logic to track "Daily Subject Master"
    # (You could add a column to User to track which subject they worked on most today)
    
    db.session.commit()
    return jsonify({"status": "success", "new_total": current_user.xp})

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
@app.route('/ai_assistant')
@login_required
def ai_assistant():
    # 1. Get the stats and weakest subject
    weakest_subject = get_weakest_subject(current_user.id)
    
    # --- IMPORTANT: Re-calculate or fetch subject_stats for the table here ---
    all_missions = Mission.query.filter_by(user_id=current_user.id).all()
    subject_stats = {}
    for m in all_missions:
        subj = m.title.replace("Study Session: ", "")
        if subj not in subject_stats:
            subject_stats[subj] = {'total': 0, 'completed': 0}
        subject_stats[subj]['total'] += 1
        if m.completed:
            subject_stats[subj]['completed'] += 1

    # 2. FETCH THE CHAT HISTORY (This is likely what's missing)
    chat_history = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp.asc()).all()
    
    return render_template('ai_assistant.html', 
                           stats=subject_stats, 
                           weakest_subject=weakest_subject, 
                           chat_history=chat_history) # <--- Make sure this is here!

genai.configure(api_key="AIzaSyBbjFzB7w2ONN42ktboJIxS_jhoHDHOFQU")
# This alias should work because it appeared in your 'Available Models' list
def get_weakest_subject(user_id):
    all_missions = Mission.query.filter_by(user_id=user_id).all()
    if not all_missions:
        return "None yet"
        
    subject_stats = {}
    for m in all_missions:
        subj = m.title.replace("Study Session: ", "")
        if subj not in subject_stats:
            subject_stats[subj] = {'total': 0, 'completed': 0}
        subject_stats[subj]['total'] += 1
        if m.completed:
            subject_stats[subj]['completed'] += 1

    weakest_subject = "None yet"
    lowest_rate = 101
    
    for subj, stats in subject_stats.items():
        rate = (stats['completed'] / stats['total']) * 100
        if rate < lowest_rate:
            lowest_rate = rate
            weakest_subject = subj
            
    return weakest_subject

@app.route('/ask_ai', methods=['POST'])
@login_required
def ask_ai():
    user_input = request.form.get('message')
    if not user_input:
        return redirect(url_for('ai_assistant'))

    # 1. COOLDOWN CHECK (Prevent 429 Rate Limits)
    # Check if the user sent a message in the last 10 seconds
    last_msg = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp.desc()).first()
    if last_msg and (datetime.utcnow() - last_msg.timestamp) < timedelta(seconds=10):
        # Optional: You could use flash() here to show a message on the UI
        return redirect(url_for('ai_assistant'))

    # 2. SAVE USER MESSAGE
    user_msg = ChatMessage(content=user_input, is_ai=False, user_id=current_user.id)
    db.session.add(user_msg)
    db.session.commit() # Commit here so the user sees their message immediately

    # 3. GET CONTEXT (Weakest Subject)
    weakest_subject = get_weakest_subject(current_user.id)

    # 4. PREPARE THE PROMPT
    prompt = f"""
    Ти си персонален AI асистент за обучение в приложението 'Focus'. 
    Статус на потребителя:
    - Най-слаб предмет: {weakest_subject}
    - Текущо XP: {current_user.xp}
    - Ниво: {current_user.level}

    Въпрос: "{user_input}"

    Инструкции:
    1. Отговори на български език.
    2. Бъди мотивиращ и кратък.
    3. Ако въпросът е свързан с учене, дай конкретен съвет.
    4. Ако е за най-слабия им предмет ({weakest_subject}), дай допълнителна доза кураж.
    """

    # 5. CALL GEMINI API
    try:
        # Using the stable alias from your ListModels output
        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content(prompt)
        ai_response_text = response.text
    except Exception as e:
        error_msg = str(e)
        print(f"Gemini API Error: {error_msg}")
        
        if "429" in error_msg:
            ai_response_text = "Достигнахте лимита на съобщенията. Моля, изчакайте 30-60 секунди и опитайте пак."
        elif "404" in error_msg:
            ai_response_text = "Грешка: Моделът не е намерен. Моля, проверете името на модела в app.py."
        else:
            ai_response_text = "В момента имам технически затруднения. Моля, опитайте след малко."

    # 6. SAVE AI RESPONSE
    ai_msg = ChatMessage(content=ai_response_text, is_ai=True, user_id=current_user.id)
    db.session.add(ai_msg)
    db.session.commit()

    return redirect(url_for('ai_assistant'))

import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)