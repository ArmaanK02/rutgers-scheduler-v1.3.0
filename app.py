"""
Scarlet Scheduler AI - v2.4.0 (Chat History & Model Fixes)
"""

import os
import re
import json
import logging
import requests
import time
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any

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
VERSION = "2.4.0"

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
        logger.info(f"Loaded catalog with {len(catalog_db.get('majors', {}))} majors")
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


class GeminiAgent:
    """AI-First Agent that uses Gemini API as the primary intelligence layer."""
    
    def __init__(self, api_keys, course_repository=None):
        self.api_keys = api_keys if isinstance(api_keys, list) else ([api_keys] if api_keys else [])
        self.course_repository = course_repository
        self.working_model = None
        self.last_request_time = 0
        self.min_request_interval = 0.5  # seconds
        
        # Priority list as requested by user
        # Note: 2.5 models might require specific beta endpoints or availability checks
        self.models = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.5-pro"
        ]
        
        logger.info(f"GeminiAgent initialized with {len(self.api_keys)} API key(s)")

    def _rate_limit_wait(self):
        """Ensure minimum time between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _call_gemini(self, prompt: str, system_instruction: str = None, max_retries: int = 3) -> Optional[str]:
        """Call Gemini API with exponential backoff and system instructions."""
        if not self.api_keys:
            logger.warning("No API keys configured")
            return None
        
        # Use v1beta for newest models and systemInstruction support
        api_version = "v1beta"
        
        for api_key in self.api_keys:
            for model in self.models:
                
                for attempt in range(max_retries):
                    self._rate_limit_wait()
                    
                    url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={api_key}"
                    
                    payload = {
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 2048
                        }
                    }
                    
                    if system_instruction:
                        payload["systemInstruction"] = {
                            "parts": [{"text": system_instruction}]
                        }
                    
                    try:
                        response = requests.post(
                            url,
                            headers={"Content-Type": "application/json"},
                            json=payload,
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            data = response.json()
                            if 'candidates' in data and data['candidates']:
                                text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                                return text.strip()
                        
                        elif response.status_code == 400:
                            # If 400 Bad Request (often due to systemInstruction not supported by specific model/version)
                            # Fallback: remove systemInstruction and prepend to prompt
                            if system_instruction:
                                logger.warning(f"Model {model} refused systemInstruction. Retrying without it.")
                                prompt = f"{system_instruction}\n\nUser Request: {prompt}"
                                system_instruction = None # Clear for retry
                                continue # Retry loop with modified payload
                            else:
                                logger.warning(f"API error 400 for {model}: {response.text[:200]}")
                                break # Break inner loop to try next model

                        elif response.status_code == 403:
                            # 403 is usually API key issue or Model access denied
                            logger.warning(f"API error 403 for {model}: {response.text[:100]}")
                            break # Try next model (or key)

                        elif response.status_code == 404:
                            # Model not found
                            logger.warning(f"API error 404 for {model}: Model not found.")
                            break # Try next model

                        elif response.status_code == 429:
                            # Rate limit
                            time.sleep((2 ** attempt) * 1)
                            continue
                            
                        else:
                            logger.warning(f"API error {response.status_code} for {model}: {response.text[:100]}")
                            break # Try next model
                            
                    except Exception as e:
                        logger.error(f"API exception for {model}: {e}")
                        break # Try next model
        
        return None

    def _get_course_database_summary(self) -> str:
        if not self.course_repository:
            return "Course database not available."
        
        try:
            all_courses = self.course_repository.data_cache[:100]  # First 100 courses
            course_list = []
            for entry in all_courses:
                subject = entry.get('subject', '')
                number = entry.get('courseNumber', '')
                title = entry.get('title', '')
                code = f"{subject}:{number}"
                course_list.append(f"{code} - {title}")
            
            return f"Available courses (sample): {', '.join(course_list[:50])}..." if course_list else "No courses in database."
        except Exception as e:
            return "Course database error."

    def analyze_intent(self, user_text: str, conversation_history: List[Dict] = None, user_history: List[Dict] = None, major_context: str = "") -> Dict:
        conversation_history = conversation_history or []
        user_history = user_history or []
        
        history_text = "\n".join([
            f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')[:200]}"
            for msg in conversation_history[-5:]
        ])
        
        history_courses = [h.get('short_code', '') for h in user_history[:20]]
        course_db_context = self._get_course_database_summary()
        
        system_instruction = """You are an intelligent course scheduling assistant for Rutgers University. 
Always respond in valid JSON format."""

        prompt = f"""Analyze this request and extract info.

REQUEST: "{user_text}"
HISTORY: {history_text}
TAKEN: {', '.join(history_courses)}
AVAILABLE: {course_db_context}

Extract JSON:
{{
    "courses": ["198:111"],
    "course_names": ["intro cs"],
    "major": "cs",
    "constraints": {{ "no_days": ["F"], "preferred_times": ["morning"], "credits_target": 15 }},
    "intent": "schedule|recommend|search|chat",
    "needs_recommendation": true,
    "fill_schedule": false
}}"""

        ai_response = self._call_gemini(prompt, system_instruction)
        
        if ai_response:
            try:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    return {
                        "codes": parsed.get("courses", []),
                        "course_names": parsed.get("course_names", []),
                        "subjects": [],
                        "constraints": {
                            "no_days": parsed.get("constraints", {}).get("no_days", []),
                            "preferred_times": parsed.get("constraints", {}).get("preferred_times", []),
                            "max_courses": parsed.get("constraints", {}).get("max_courses"),
                            "credits_target": parsed.get("constraints", {}).get("credits_target")
                        },
                        "is_conversational": parsed.get("intent") in ["chat", "question"],
                        "is_schedule_request": parsed.get("intent") in ["schedule", "fill_schedule"],
                        "needs_recommendations": parsed.get("needs_recommendation", False),
                        "fill_schedule": parsed.get("fill_schedule", False),
                        "detected_major": parsed.get("major"),
                        "explanation": "",
                        "confidence": 0.9
                    }
            except Exception as e:
                logger.warning(f"AI Parse Error: {e}")
        
        # Fallback
        return {
            "codes": [], "course_names": [], "subjects": [],
            "constraints": {"no_days": [], "preferred_times": [], "max_courses": None, "credits_target": None},
            "is_conversational": True, "is_schedule_request": False,
            "needs_recommendations": False, "fill_schedule": False,
            "detected_major": None, "explanation": "", "confidence": 0.3
        }

    def search_courses_ai(self, query: str, limit: int = 10) -> List[str]:
        if not self.course_repository: return []
        
        prompt = f"""Find Rutgers course codes for: "{query}".
Return ONLY a JSON array of strings, e.g. ["198:111", "640:151"]. Max {limit} results."""

        ai_response = self._call_gemini(prompt)
        if ai_response:
            try:
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match: return json.loads(json_match.group())[:limit]
            except: pass
        return []

    def get_course_recommendations_ai(self, major: str = None, user_history: List[Dict] = None, constraints: Dict = None) -> List[str]:
        user_history = user_history or []
        history_courses = [h.get('short_code', '') for h in user_history]
        
        prompt = f"""Recommend 5 Rutgers courses for Major: {major}.
Taken: {', '.join(history_courses)}.
Constraints: {json.dumps(constraints)}.
Return ONLY a JSON array of strings: ["198:111", "640:151"]"""

        ai_response = self._call_gemini(prompt)
        if ai_response:
            try:
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match: return json.loads(json_match.group())
            except: pass
        return []

    def generate_conversational_response(self, user_text: str, intent: Dict, conversation_history: List[Dict] = None, 
                                        schedules_found: int = 0, courses_found: List[Course] = None, 
                                        user_history: List[Dict] = None) -> str:
        
        course_info = "\n".join([f"- {c.code}: {c.title}" for c in (courses_found or [])[:5]])
        
        prompt = f"""You are Scarlet Scheduler. Respond to: "{user_text}".
Context: Found {schedules_found} schedules.
Courses identified: {course_info}.
Be helpful and concise."""

        ai_response = self._call_gemini(prompt)
        return ai_response if ai_response else "I'm looking into that for you."


ai_agent = GeminiAgent(Config.GEMINI_API_KEYS, course_repository=repo)


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
    
    # If no ID, find latest chat or create new if none exist
    if not active_chat:
        active_chat = Chat.query.filter_by(user_id=current_user.id).order_by(Chat.updated_at.desc()).first()
    
    if not active_chat:
        active_chat = Chat(user_id=current_user.id, title="New Chat")
        db.session.add(active_chat)
        db.session.commit()

    # Fetch all chats for the sidebar
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

# --- API ROUTES ---

@app.route('/api/new_chat', methods=['POST'])
@login_required
def new_chat():
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
        chat.updated_at = datetime.now(timezone.utc)
        if chat.title == "New Chat":
            chat.title = text[:30] + "..."
            
    user_msg = Message(chat_id=chat.id, role='user', content=text)
    db.session.add(user_msg)
    db.session.flush()
    
    previous_messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.asc()).all()
    conversation_history = [{"role": msg.role, "content": msg.content} for msg in previous_messages[-10:]]
    user_history = current_user.get_history()
    
    ai_result = ai_agent.analyze_intent(text, conversation_history, user_history)
    
    # Logic to fetch courses and schedule...
    courses_obj = []
    if ai_result.get('codes'):
        current_repo = DataServiceFactory.get_repository()
        courses_obj = current_repo.get_courses(ai_result['codes'])

    schedules_data = []
    if courses_obj:
        scheduler = DeepSeekSchedulerStrategy()
        constraints = ScheduleConstraints(no_days=ai_result['constraints']['no_days'])
        schedules = scheduler.generate_schedules(courses_obj, constraints)
        if schedules:
            schedules_data = _format_schedules_helper(schedules, courses_obj)
            
    response_text = ai_agent.generate_conversational_response(
        text, ai_result, conversation_history, len(schedules_data), courses_obj, user_history
    )

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

# --- HELPER FUNCTIONS ---

def _calculate_schedule_benefits(schedule_data: List[Dict]) -> Dict[str, Any]:
    """Calculate benefits/characteristics of a schedule."""
    benefits = []
    
    # Collect all time slots
    all_times = []
    campuses = set()
    days_with_classes = set()
    morning_classes = 0
    afternoon_classes = 0
    evening_classes = 0
    total_credits = 0
    
    for course_info in schedule_data:
        total_credits += course_info.get('credits', 3)
        campuses.add(course_info.get('campus', 'Unknown'))
        
        for time_info in course_info.get('times', []):
            day = time_info.get('day', '')
            if day:
                days_with_classes.add(day)
            
            start_time = time_info.get('start_minutes', 0)
            if 480 <= start_time < 720:  # 8 AM - 12 PM
                morning_classes += 1
            elif 720 <= start_time < 1020:  # 12 PM - 5 PM
                afternoon_classes += 1
            elif start_time >= 1020:  # 5 PM+
                evening_classes += 1
    
    # Calculate benefits
    days_without_classes = 5 - len(days_with_classes)
    if days_without_classes > 0:
        day_names = {'M': 'Monday', 'T': 'Tuesday', 'W': 'Wednesday', 'TH': 'Thursday', 'F': 'Friday'}
        free_days = [day_names.get(d, d) for d in ['M', 'T', 'W', 'TH', 'F'] if d not in days_with_classes]
        if free_days:
            benefits.append(f"No classes on {', '.join(free_days)}")
    
    if len(campuses) <= 2 and 'Unknown' not in campuses:
        campus_list = list(campuses)
        if len(campus_list) == 1:
            benefits.append(f"All classes on {campus_list[0]} campus")
        else:
            benefits.append(f"Classes on only {len(campus_list)} campuses ({', '.join(campus_list)})")
    
    if morning_classes == 0:
        benefits.append("No morning classes")
    if evening_classes == 0:
        benefits.append("No evening classes")
    
    # Check if spread out (classes on 4+ days)
    if len(days_with_classes) >= 4:
        benefits.append("Well-distributed schedule")
    elif len(days_with_classes) <= 2:
        benefits.append("Compact schedule (fewer days)")
    
    return {
        'benefits': benefits,
        'total_credits': total_credits,
        'campuses': list(campuses),
        'days_with_classes': len(days_with_classes),
        'no_morning': morning_classes == 0,
        'no_evening': evening_classes == 0
    }

def _format_schedules_helper(schedules, courses_obj):
    """Format schedules with readable time information and benefits."""
    results = []
    for schedule in schedules[:50]:  # Increased limit
        schedule_data = []
        for section in schedule:
            course = next((c for c in courses_obj for s in c.sections if s.index == section.index), None)
            if not course:
                continue
                
            # Format time slots with detailed information
            formatted_times = []
            for time_slot in section.time_slots:
                # Convert minutes to readable time
                start_hour = time_slot.start_time // 60
                start_min = time_slot.start_time % 60
                end_hour = time_slot.end_time // 60
                end_min = time_slot.end_time % 60
                
                # Format as 12-hour time
                start_period = "AM" if start_hour < 12 else "PM"
                end_period = "AM" if end_hour < 12 else "PM"
                if start_hour == 0:
                    start_hour = 12
                elif start_hour > 12:
                    start_hour -= 12
                if end_hour == 0:
                    end_hour = 12
                elif end_hour > 12:
                    end_hour -= 12
                
                time_info = {
                    'day': time_slot.day,
                    'time_str': f"{start_hour}:{start_min:02d}{start_period}-{end_hour}:{end_min:02d}{end_period}",
                    'start_minutes': time_slot.start_time,
                    'end_minutes': time_slot.end_time,
                    'campus': time_slot.campus if time_slot.campus != "UNKNOWN" else "Unknown",
                    'room': getattr(time_slot, 'room', '')
                }
                formatted_times.append(time_info)
            
            # Get primary campus (most common)
            campuses = [t['campus'] for t in formatted_times if t['campus'] != 'Unknown']
            primary_campus = max(set(campuses), key=campuses.count) if campuses else "Unknown"
            
            schedule_data.append({
                'course': course.code if course else "Unknown",
                'title': course.title if course else "",
                'index': section.index,
                'section_number': section.section_number if hasattr(section, 'section_number') else "Unknown",
                'times': formatted_times,
                'instructors': section.instructors if hasattr(section, 'instructors') else [],
                'campus': primary_campus,
                'credits': getattr(course, 'credits', 3.0)
            })
        
        # Calculate benefits for this schedule
        benefits = _calculate_schedule_benefits(schedule_data)
        
        results.append({
            'courses': schedule_data,
            'benefits': benefits
        })
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
    
    history = current_user.get_history()
    taken_codes = {h['short_code'] for h in history}
    
    # Check if we have structured requirements
    structured_reqs = major_data.get('structured_requirements')
    
    if structured_reqs:
        # Use structured requirements for detailed tracking
        result = {
            'progress': 0,
            'completed': [],
            'remaining': [],
            'total_reqs': 0,
            'core_requirements': {
                'completed': [],
                'remaining': [],
                'total': 0
            },
            'electives': {
                'lower_level': {'completed': [], 'remaining': [], 'required': 0, 'total': 0},
                'upper_level': {'completed': [], 'remaining': [], 'required': 0, 'total': 0},
                'general': {'completed': [], 'remaining': [], 'required': 0, 'total': 0}
            },
            'total_credits': structured_reqs.get('total_credits'),
            'notes': structured_reqs.get('notes', '')
        }
        
        # Process core requirements
        if structured_reqs.get('core_requirements'):
            for course in structured_reqs['core_requirements']:
                code = course.get('code', '')
                short_code = code.split(':')[-2] + ':' + code.split(':')[-1] if ':' in code else code
                result['total_reqs'] += 1
                result['core_requirements']['total'] += 1
                
                if short_code in taken_codes:
                    result['completed'].append(short_code)
                    result['core_requirements']['completed'].append({
                        'code': short_code,
                        'name': course.get('name', ''),
                        'prerequisites': course.get('prerequisites', [])
                    })
                else:
                    result['remaining'].append(short_code)
                    result['core_requirements']['remaining'].append({
                        'code': short_code,
                        'name': course.get('name', ''),
                        'prerequisites': course.get('prerequisites', [])
                    })
        
        # Process electives
        if structured_reqs.get('electives'):
            for level in ['lower_level', 'upper_level', 'general']:
                elective_data = structured_reqs['electives'].get(level, {})
                required_count = elective_data.get('required_count', 0)
                courses = elective_data.get('courses', [])
                
                result['electives'][level]['required'] = required_count
                result['electives'][level]['total'] = len(courses)
                
                completed_count = 0
                for course in courses:
                    code = course.get('code', '')
                    short_code = code.split(':')[-2] + ':' + code.split(':')[-1] if ':' in code else code
                    
                    if short_code in taken_codes:
                        completed_count += 1
                        result['electives'][level]['completed'].append({
                            'code': short_code,
                            'name': course.get('name', ''),
                            'prerequisites': course.get('prerequisites', [])
                        })
                    else:
                        result['electives'][level]['remaining'].append({
                            'code': short_code,
                            'name': course.get('name', ''),
                            'prerequisites': course.get('prerequisites', [])
                        })
                
                # Calculate progress for this elective category
                if required_count > 0:
                    result['electives'][level]['progress'] = min(100, int((completed_count / required_count) * 100))
                else:
                    result['electives'][level]['progress'] = 0
        
        # Calculate overall progress
        if result['total_reqs'] > 0:
            result['progress'] = int((len(result['completed']) / result['total_reqs']) * 100)
        
        # Add elective progress to overall
        elective_progress = 0
        elective_total = 0
        for level in ['lower_level', 'upper_level', 'general']:
            req_count = result['electives'][level]['required']
            if req_count > 0:
                completed = len(result['electives'][level]['completed'])
                elective_progress += completed
                elective_total += req_count
        
        if elective_total > 0:
            # Weighted progress: core + electives
            core_weight = len(result['completed']) if result['total_reqs'] > 0 else 0
            total_weight = result['total_reqs'] + elective_total
            if total_weight > 0:
                result['progress'] = int(((core_weight + elective_progress) / total_weight) * 100)
        
        return jsonify(result)
    else:
        # Fallback to simple requirements list
        requirements = major_data.get('requirements', [])
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
            'total_reqs': len(requirements),
            'core_requirements': {'completed': [], 'remaining': [], 'total': 0},
            'electives': {
                'lower_level': {'completed': [], 'remaining': [], 'required': 0, 'total': 0},
                'upper_level': {'completed': [], 'remaining': [], 'required': 0, 'total': 0},
                'general': {'completed': [], 'remaining': [], 'required': 0, 'total': 0}
            }
        })

@app.route('/api/what_if', methods=['POST'])
@login_required
def what_if_analysis():
    major = request.json.get('major')
    major_data = catalog_db.get('majors', {}).get(major, {})
    requirements = major_data.get('requirements', [])
    
    history = current_user.get_history()
    taken_codes = {h['short_code'] for h in history}
    
    matched_courses = []
    remaining_courses = []
    
    for req in requirements:
        if req in taken_codes:
            matched_courses.append(req)
        else:
            remaining_courses.append(req)
            
    match_score = int((len(matched_courses) / len(requirements) * 100)) if requirements else 0
    
    return jsonify({
        'match_score': match_score,
        'matched': matched_courses,
        'remaining': remaining_courses,
        'total_requirements': len(requirements)
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'version': VERSION,
        'ai_enabled': bool(Config.GEMINI_API_KEYS),
        'catalog_loaded': bool(catalog_db.get('majors'))
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)