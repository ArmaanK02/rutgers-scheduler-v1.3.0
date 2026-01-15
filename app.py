"""
Scarlet Scheduler AI - v2.2.0 (What-If & Degree Map)
"""

import os
import re
import json
import logging
import requests
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from config import get_config, validate_config
from data_adapter import DataServiceFactory
from scheduler_strategies import DeepSeekSchedulerStrategy
from scheduler_core import ScheduleConstraints, Course
from prerequisite_parser import PrerequisiteParser
from models import db, User, Chat, Message

# --- VERSION ---
VERSION = "2.2.0"

# --- LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- PATH SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')
data_filename = 'rutgers_scheduler_data.json'
majors_filename = 'major_requirements.json'

# Auto-Discovery for Data File
possible_paths = [
    os.path.join(base_dir, data_filename),
    os.path.join(os.getcwd(), data_filename),
    os.path.join(os.path.dirname(base_dir), data_filename)
]
found_data_path = next((p for p in possible_paths if os.path.exists(p)), None)

Config = get_config()
if found_data_path:
    Config.DATA_FILE_PATH = found_data_path

# Load Major/Minor Requirements
catalog_db = {}
major_path = os.path.join(base_dir, majors_filename)
if os.path.exists(major_path):
    try:
        with open(major_path, 'r', encoding='utf-8') as f:
            catalog_db = json.load(f)
        if "majors" not in catalog_db:
            catalog_db = {"majors": catalog_db, "minors": {}, "certificates": {}}
    except Exception as e:
        logger.error(f"❌ Failed to load catalog: {e}")

# --- APP INITIALIZATION ---
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Database Setup
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(base_dir, "scheduler.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Login Manager Setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Create DB Tables
with app.app_context():
    db.create_all()

# --- BACKGROUND DATA LOAD ---
repo = DataServiceFactory.get_repository()
def load_history_background():
    logger.info("⏳ Starting background fetch of historical course titles...")
    repo.fetch_historical_titles()
    logger.info("✅ Background fetch complete.")

threading.Thread(target=load_history_background, daemon=True).start()


# --- CONSTANTS & HELPERS ---
GREETINGS = ["hello", "hi", "hey", "greetings", "sup", "yo", "what's up", "howdy"]
COURSE_CODE_PATTERN = re.compile(r'(\d{2,3})[:\s\-]?(\d{3})')
COURSE_ALIASES = {
    "cs": "198", "computer science": "198", "math": "640", "calc": "640",
    "econ": "220", "physics": "750", "chem": "160", "bio": "119",
    "psych": "830", "expos": "355", "stats": "960"
}
COMMON_COURSES = {
    "intro to cs": "198:111", "data structures": "198:112",
    "calc 1": "640:151", "calc 2": "640:152", "calc 3": "640:251",
    "linear algebra": "640:250", "expos": "355:101"
}

# --- LOGIC CLASSES ---
class IntentAnalyzer:
    def __init__(self):
        self.day_mappings = {"monday": "M", "mon": "M", "tues": "T", "tue": "T", "wed": "W", "thurs": "TH", "thu": "TH", "fri": "F"}
        self.time_constraints = {"morning": (0, 720), "afternoon": (720, 1020), "evening": (1020, 1440)}

    def analyze(self, user_text: str) -> Dict:
        lower = user_text.lower().strip()
        result = {
            "codes": self._extract_course_codes(user_text),
            "subjects": [],
            "constraints": {"no_days": [], "preferred_times": [], "max_courses": None, "credits_target": None},
            "is_conversational": False,
            "is_schedule_request": False,
            "needs_recommendations": False,
            "explanation": "",
            "confidence": 0.0
        }
        
        if any(w in lower for w in ["schedule", "plan", "classes"]): result["is_schedule_request"] = True
        if any(w in lower for w in GREETINGS) and len(lower.split()) < 4: result["is_conversational"] = True
        
        if "no friday" in lower or "free friday" in lower: result["constraints"]["no_days"].append("F")
        if "no monday" in lower: result["constraints"]["no_days"].append("M")
        
        result["confidence"] = 0.8 if result["codes"] else 0.2
        return result

    def _extract_course_codes(self, text: str) -> List[str]:
        codes = []
        full_pattern = re.compile(r'(\d{2,3}):(\d{3})')
        for match in full_pattern.finditer(text):
            codes.append(f"{match.group(1)}:{match.group(2)}")
        
        for name, code in COMMON_COURSES.items():
            if name in text.lower():
                codes.append(code)
        return list(set(codes))

class GeminiAgent:
    def __init__(self, api_keys):
        self.api_keys = api_keys if isinstance(api_keys, list) else ([api_keys] if api_keys else [])
        self.local_analyzer = IntentAnalyzer()

    def analyze_intent(self, user_text: str, history_context: str = "", major_context: str = "") -> Dict:
        return self.local_analyzer.analyze(user_text)

    def chat_fallback(self, user_text: str) -> str:
        return "I'm here to help with scheduling! Mention some courses like 'CS 111' or 'Calc 1'."

    def summarize_success(self, found_codes, constraints, count):
        return f"Found {count} schedules for {', '.join(found_codes)}."

    def explain_failure(self, failed_codes, constraints):
        return f"Could not find valid schedules for {', '.join(failed_codes)} with current constraints."

ai_agent = GeminiAgent(Config.GEMINI_API_KEYS)


# --- AUTH ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))
            
        new_user = User(username=username, password_hash=generate_password_hash(password, method='scrypt'))
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('chat_interface'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('chat_interface'))
        else:
            flash('Invalid credentials.')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


# --- APP ROUTES ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat_interface'))
    return render_template('home.html')

@app.route('/chat')
@login_required
def chat_interface():
    chat_id = request.args.get('id')
    active_chat = None
    
    if chat_id:
        active_chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    
    if not active_chat:
        active_chat = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.updated_at.desc()).first()
    
    chats = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.updated_at.desc()).all()
    
    return render_template('chat.html', chats=chats, active_chat=active_chat, user=current_user)

@app.route('/history')
@login_required
def history_dashboard():
    history = current_user.get_history()
    return render_template('history.html', history=history, user=current_user)

@app.route('/progress')
@login_required
def progress_dashboard():
    majors = sorted(list(catalog_db.get('majors', {}).keys()))
    return render_template('progress.html', majors=majors, user=current_user)

@app.route('/what-if')
@login_required
def what_if_dashboard():
    majors = sorted(list(catalog_db.get('majors', {}).keys()))
    return render_template('what_if.html', majors=majors, user=current_user)

@app.route('/degree-map')
@login_required
def degree_map_dashboard():
    return render_template('degree_map.html', user=current_user)

# --- API ROUTES ---

@app.route('/api/new_chat', methods=['POST'])
@login_required
def new_chat():
    empty_chat = Chat.query.filter_by(user_id=current_user.id).filter(~Chat.messages.any()).first()
    if empty_chat:
        return jsonify({'id': empty_chat.id, 'message': 'Redirected to existing empty chat'})
    
    chat = Chat(user_id=current_user.id, title="New Chat")
    db.session.add(chat)
    db.session.commit()
    return jsonify({'id': chat.id})

@app.route('/api/delete_chat', methods=['POST'])
@login_required
def delete_chat():
    data = request.json
    chat_id = data.get('chat_id')
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    
    if chat:
        db.session.delete(chat)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Chat not found'}), 404

@app.route('/api/send_message', methods=['POST'])
@login_required
def send_message():
    data = request.json
    chat_id = data.get('chat_id')
    text = data.get('text')
    
    chat = Chat.query.filter_by(id=chat_id, user_id=current_user.id).first()
    if not chat:
        chat = Chat(user_id=current_user.id, title=text[:30] + "...")
        db.session.add(chat)
        db.session.commit()
    else:
        chat.updated_at = datetime.utcnow()
        if chat.title == "New Chat":
            chat.title = text[:30] + "..."
            
    user_msg = Message(chat_id=chat.id, role='user', content=text)
    db.session.add(user_msg)
    
    ai_result = ai_agent.analyze_intent(text)
    
    response_text = ""
    schedules_data = []
    
    if ai_result['is_conversational'] and not ai_result['codes']:
        response_text = ai_agent.chat_fallback(text)
    else:
        codes = ai_result['codes']
        if not codes:
             response_text = "I couldn't identify the courses. Please try course codes like 198:111."
        else:
            current_repo = DataServiceFactory.get_repository()
            courses_obj = current_repo.get_courses(codes)
            
            if not courses_obj:
                response_text = f"Could not find courses: {', '.join(codes)}"
            else:
                scheduler = DeepSeekSchedulerStrategy()
                constraints = ScheduleConstraints(no_days=ai_result['constraints']['no_days'])
                schedules = scheduler.generate_schedules(courses_obj, constraints)
                
                if schedules:
                    response_text = ai_agent.summarize_success([c.code for c in courses_obj], constraints.no_days, len(schedules))
                    schedules_data = _format_schedules_helper(schedules, courses_obj)
                else:
                    response_text = ai_agent.explain_failure([c.code for c in courses_obj], constraints.no_days)

    ai_msg = Message(
        chat_id=chat.id, 
        role='ai', 
        content=response_text,
        meta_data=json.dumps(schedules_data) if schedules_data else None
    )
    db.session.add(ai_msg)
    db.session.commit()
    
    return jsonify({
        'chat_id': chat.id,
        'user_message': {'text': text, 'time': user_msg.timestamp.isoformat()},
        'ai_message': {
            'text': response_text, 
            'schedules': schedules_data,
            'time': ai_msg.timestamp.isoformat()
        }
    })

def _format_schedules_helper(schedules, courses_obj):
    results = []
    for schedule in schedules[:10]:
        schedule_data = []
        for section in schedule:
            course = next((c for c in courses_obj for s in c.sections if s.index == section.index), None)
            schedule_data.append({
                'course': course.code if course else "Unknown",
                'title': course.title if course else "",
                'index': section.index,
                'times': [str(t) for t in section.time_slots]
            })
        results.append(schedule_data)
    return results

@app.route('/api/parse_history', methods=['POST'])
@login_required
def parse_history():
    data = request.get_json()
    repo = DataServiceFactory.get_repository()
    
    taken_courses = PrerequisiteParser.parse_copy_paste(
        data.get('text', ''), 
        title_resolver=repo.get_course_title
    )
    
    existing = current_user.get_history()
    existing_codes = {c['short_code'] for c in existing}
    
    added_count = 0
    for course in taken_courses:
        if course['short_code'] not in existing_codes:
            existing.append(course)
            added_count += 1
            
    current_user.set_history(existing)
    db.session.commit()
    return jsonify({'message': f"Added {added_count} new courses to your history."})

@app.route('/api/clear_history', methods=['POST'])
@login_required
def clear_history():
    current_user.set_history([])
    db.session.commit()
    return jsonify({'success': True, 'message': 'History cleared.'})

@app.route('/api/add_manual_course', methods=['POST'])
@login_required
def add_manual_course():
    data = request.json
    code = data.get('code')
    title = data.get('title')
    force = data.get('force', False)
    
    if not title and not force:
        repo = DataServiceFactory.get_repository()
        found_title = repo.get_course_title(code)
        
        if found_title == "Unknown Title":
            return jsonify({'status': 'title_needed', 'message': 'Title not found'})
        else:
            title = found_title

    course = {
        "code": code,
        "short_code": code.split(':')[-2] + ":" + code.split(':')[-1] if code.count(':') >= 2 else code,
        "credits": float(data.get('credits', 3.0)),
        "status": "Completed",
        "title": title or "Manual Entry",
        "term": data.get('term', ''),
        "grade": data.get('grade', '')
    }
    
    history = current_user.get_history()
    history.append(course)
    current_user.set_history(history)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/api/check_progress', methods=['POST'])
@login_required
def check_progress():
    major = request.json.get('major')
    major_data = catalog_db.get('majors', {}).get(major, {})
    requirements = major_data.get('requirements', [])
    
    history = current_user.get_history()
    taken_codes = {h['short_code'] for h in history}
    
    completed = []
    remaining = []
    
    for req in requirements:
        if req in taken_codes:
            completed.append(req)
        else:
            remaining.append(req)
            
    progress_percent = int((len(completed) / len(requirements) * 100)) if requirements else 0
    
    return jsonify({
        'progress': progress_percent,
        'completed': completed,
        'remaining': remaining,
        'total_reqs': len(requirements)
    })

# --- NEW WHAT-IF LOGIC ---
@app.route('/api/what_if', methods=['POST'])
@login_required
def what_if_analysis():
    major = request.json.get('major')
    major_data = catalog_db.get('majors', {}).get(major, {})
    
    # We need a robust list of requirements
    # Assuming 'requirements' list in JSON contains course codes strings
    requirements = major_data.get('requirements', [])
    
    history = current_user.get_history()
    taken_codes = {h['short_code'] for h in history}
    
    matched_courses = []
    remaining_courses = []
    
    for req in requirements:
        # Check if requirement matches any taken course
        # Simple match for now, could be improved with regex/wildcards
        if req in taken_codes:
            matched_courses.append(req)
        else:
            remaining_courses.append(req)
            
    # Calculate simple match score
    match_score = int((len(matched_courses) / len(requirements) * 100)) if requirements else 0
    
    return jsonify({
        'match_score': match_score,
        'matched': matched_courses,
        'remaining': remaining_courses,
        'total_requirements': len(requirements)
    })

# --- NEW DEGREE MAP LOGIC ---
@app.route('/api/degree_graph', methods=['GET'])
@login_required
def degree_graph_data():
    # Construct a simple graph for visualization
    # Nodes: All courses in history + courses in current major (if selected, or just generic example)
    # Edges: Prerequisites (Need a prereq DB source, mocking for demo)
    
    history = current_user.get_history()
    nodes = []
    edges = []
    
    # Add History Nodes
    for h in history:
        nodes.append({
            'data': {
                'id': h['short_code'], 
                'label': h['short_code'], 
                'color': '#4caf50' # Green for taken
            }
        })
        
    # Example Mock Prerequisites (Ideally this comes from a DB)
    # Let's say Calc 1 (640:151) -> Calc 2 (640:152) -> Calc 3 (640:251)
    mock_prereqs = {
        '640:152': ['640:151'],
        '640:251': ['640:152'],
        '198:112': ['198:111'],
        '198:211': ['198:112'],
        '198:344': ['198:211', '198:205']
    }
    
    added_ids = {n['data']['id'] for n in nodes}
    
    # Add hypothetical edges if nodes exist
    for target, prereqs in mock_prereqs.items():
        for p in prereqs:
            # Add nodes if missing (as grey 'future' nodes)
            if p not in added_ids:
                nodes.append({'data': {'id': p, 'label': p, 'color': '#888'}})
                added_ids.add(p)
            if target not in added_ids:
                nodes.append({'data': {'id': target, 'label': target, 'color': '#888'}})
                added_ids.add(target)
            
            edges.append({
                'data': {
                    'source': p, 
                    'target': target
                }
            })
            
    return jsonify({'elements': nodes + edges})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)