"""
Scarlet Scheduler AI - v2.2.1 (Fixed AI Agent)
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
VERSION = "2.2.1"

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

# Major-specific course recommendations
MAJOR_FRESHMAN_COURSES = {
    "computer science": ["198:111", "640:151", "355:101"],
    "cs": ["198:111", "640:151", "355:101"],
    "data science": ["198:142", "640:151", "960:211"],
    "mathematics": ["640:151", "640:250", "355:101"],
    "math": ["640:151", "640:250", "355:101"],
    "economics": ["220:102", "640:135", "355:101"],
    "econ": ["220:102", "640:135", "355:101"],
    "business": ["010:272", "220:102", "355:101"],
    "biology": ["119:115", "160:161", "355:101"],
    "bio": ["119:115", "160:161", "355:101"],
    "chemistry": ["160:161", "160:171", "640:151"],
    "chem": ["160:161", "160:171", "640:151"],
    "physics": ["750:203", "640:151", "355:101"],
    "psychology": ["830:101", "355:101", "960:211"],
    "psych": ["830:101", "355:101", "960:211"],
    "engineering": ["440:127", "640:151", "750:203"],
}

# --- LOGIC CLASSES ---

class IntentAnalyzer:
    """Local intent analyzer for extracting course codes and constraints."""
    
    def __init__(self):
        self.day_mappings = {
            "monday": "M", "mon": "M", 
            "tuesday": "T", "tues": "T", "tue": "T",
            "wednesday": "W", "wed": "W",
            "thursday": "TH", "thurs": "TH", "thu": "TH",
            "friday": "F", "fri": "F"
        }

    def analyze(self, user_text: str) -> Dict:
        lower = user_text.lower().strip()
        result = {
            "codes": self._extract_course_codes(user_text),
            "subjects": [],
            "constraints": {"no_days": [], "preferred_times": [], "max_courses": None, "credits_target": None},
            "is_conversational": False,
            "is_schedule_request": False,
            "needs_recommendations": False,
            "detected_major": None,
            "is_freshman": False,
            "explanation": "",
            "confidence": 0.0
        }
        
        # Detect schedule-related keywords
        if any(w in lower for w in ["schedule", "plan", "classes", "courses", "need", "take", "register"]):
            result["is_schedule_request"] = True
        
        # Detect greetings
        if any(w in lower for w in GREETINGS) and len(lower.split()) < 4:
            result["is_conversational"] = True
        
        # Detect major mentions
        for major_key in MAJOR_FRESHMAN_COURSES.keys():
            if major_key in lower:
                result["detected_major"] = major_key
                result["needs_recommendations"] = True
                break
        
        # Detect freshman/sophomore/etc
        if any(w in lower for w in ["freshman", "first year", "1st year", "new student"]):
            result["is_freshman"] = True
            result["needs_recommendations"] = True
        
        # Extract day constraints
        if "no friday" in lower or "free friday" in lower or "fridays off" in lower:
            result["constraints"]["no_days"].append("F")
        if "no monday" in lower or "mondays off" in lower:
            result["constraints"]["no_days"].append("M")
        for day_name, day_code in self.day_mappings.items():
            if f"no {day_name}" in lower:
                if day_code not in result["constraints"]["no_days"]:
                    result["constraints"]["no_days"].append(day_code)
        
        # Set confidence
        if result["codes"]:
            result["confidence"] = 0.9
        elif result["detected_major"]:
            result["confidence"] = 0.7
        elif result["is_schedule_request"]:
            result["confidence"] = 0.5
        else:
            result["confidence"] = 0.2
            
        return result

    def _extract_course_codes(self, text: str) -> List[str]:
        codes = []
        
        # Match full course codes like 198:111 or 01:198:111
        full_pattern = re.compile(r'(?:\d{2}:)?(\d{2,3}):(\d{3})')
        for match in full_pattern.finditer(text):
            codes.append(f"{match.group(1)}:{match.group(2)}")
        
        # Match common course names
        lower_text = text.lower()
        for name, code in COMMON_COURSES.items():
            if name in lower_text:
                if code not in codes:
                    codes.append(code)
        
        # Match "CS 111" style
        cs_pattern = re.compile(r'\b(cs|math|econ|phys|chem|bio|psych)\s*(\d{3})\b', re.IGNORECASE)
        for match in cs_pattern.finditer(text):
            subject = COURSE_ALIASES.get(match.group(1).lower(), match.group(1))
            code = f"{subject}:{match.group(2)}"
            if code not in codes:
                codes.append(code)
        
        return list(set(codes))


class GeminiAgent:
    """AI Agent that uses Gemini API for intelligent responses."""
    
    def __init__(self, api_keys):
        self.api_keys = api_keys if isinstance(api_keys, list) else ([api_keys] if api_keys else [])
        self.local_analyzer = IntentAnalyzer()
        self.working_model = None
        self.last_request_time = 0
        self.min_request_interval = 1.0  # seconds
        
        # Models to try in order of preference
        self.models = [
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-pro",
        ]
        
        logger.info(f"GeminiAgent initialized with {len(self.api_keys)} API key(s)")

    def _rate_limit_wait(self):
        """Ensure minimum time between API requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _call_gemini(self, prompt: str, max_retries: int = 3) -> Optional[str]:
        """Call Gemini API with exponential backoff."""
        if not self.api_keys:
            logger.warning("No API keys configured")
            return None
        
        models_to_try = [self.working_model] if self.working_model else self.models
        
        for api_key in self.api_keys:
            for model in models_to_try:
                if not model:
                    continue
                    
                for attempt in range(max_retries):
                    self._rate_limit_wait()
                    
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    
                    payload = {
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": 1024,
                        }
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
                                self.working_model = model  # Cache working model
                                logger.info(f"Gemini API success with model {model}")
                                return text.strip()
                        
                        elif response.status_code == 429:
                            # Rate limited - exponential backoff
                            wait_time = (2 ** attempt) * 2
                            logger.warning(f"Rate limited, waiting {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        
                        elif response.status_code == 404:
                            logger.warning(f"Model {model} not found, trying next...")
                            break  # Try next model
                        
                        elif response.status_code == 403:
                            logger.error(f"API key forbidden (403) - API may not be enabled")
                            break  # Try next key
                        
                        else:
                            logger.warning(f"API error {response.status_code}: {response.text[:200]}")
                            
                    except requests.Timeout:
                        logger.warning(f"Request timeout for model {model}")
                    except Exception as e:
                        logger.error(f"API exception: {e}")
                
                # If we got here without success, try next model
                if model == self.working_model:
                    self.working_model = None  # Reset cached model
        
        return None

    def analyze_intent(self, user_text: str, history_context: str = "", major_context: str = "") -> Dict:
        """Analyze user intent using local analysis + AI enhancement."""
        # First, use local analyzer for basic extraction
        local_result = self.local_analyzer.analyze(user_text)
        
        # If we found codes or clear intent locally, return that
        if local_result["codes"] or local_result["detected_major"]:
            return local_result
        
        # For ambiguous queries, try Gemini for enhancement
        if local_result["is_schedule_request"] and not local_result["codes"]:
            ai_prompt = f"""You are a Rutgers University course scheduling assistant. 
Analyze this student request and extract:
1. Any course codes mentioned (format: XXX:YYY like 198:111)
2. The student's major if mentioned
3. Any scheduling constraints (no Fridays, mornings only, etc.)

Student request: "{user_text}"

Respond in JSON format only:
{{"courses": ["198:111"], "major": "computer science", "constraints": ["no_friday"], "needs_recommendation": true}}

If unsure, set needs_recommendation to true."""

            ai_response = self._call_gemini(ai_prompt)
            if ai_response:
                try:
                    # Try to parse JSON from response
                    json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        if parsed.get("courses"):
                            local_result["codes"] = parsed["courses"]
                        if parsed.get("major"):
                            local_result["detected_major"] = parsed["major"].lower()
                            local_result["needs_recommendations"] = True
                        if "no_friday" in parsed.get("constraints", []):
                            local_result["constraints"]["no_days"].append("F")
                except (json.JSONDecodeError, AttributeError) as e:
                    logger.warning(f"Could not parse AI response: {e}")
        
        return local_result

    def get_major_recommendations(self, major: str, is_freshman: bool = True) -> List[str]:
        """Get course recommendations for a major."""
        major_lower = major.lower()
        
        # Check our predefined recommendations
        if major_lower in MAJOR_FRESHMAN_COURSES:
            return MAJOR_FRESHMAN_COURSES[major_lower]
        
        # Check the catalog database
        for major_name, major_data in catalog_db.get("majors", {}).items():
            if major_lower in major_name.lower():
                reqs = major_data.get("requirements", [])
                # Return first 3-4 intro courses
                return reqs[:4] if reqs else []
        
        # Default to common freshman courses
        return ["355:101", "640:151"]  # Expos and Calc

    def generate_response(self, user_text: str, intent: Dict, schedules_found: int = 0) -> str:
        """Generate an intelligent response based on intent analysis."""
        
        # If we have codes and found schedules
        if intent["codes"] and schedules_found > 0:
            course_list = ", ".join(intent["codes"])
            constraints_text = ""
            if intent["constraints"]["no_days"]:
                day_names = {"M": "Monday", "T": "Tuesday", "W": "Wednesday", "TH": "Thursday", "F": "Friday"}
                excluded = [day_names.get(d, d) for d in intent["constraints"]["no_days"]]
                constraints_text = f" with no classes on {', '.join(excluded)}"
            
            return f"I found {schedules_found} possible schedules for {course_list}{constraints_text}. Click 'View Generated Schedules' to see your options!"
        
        # If we have codes but no schedules
        if intent["codes"] and schedules_found == 0:
            return f"I couldn't find any conflict-free schedules for {', '.join(intent['codes'])} with your constraints. Try removing some courses or relaxing your day preferences."
        
        # If we detected a major and need recommendations
        if intent["needs_recommendations"] and intent["detected_major"]:
            major = intent["detected_major"]
            recommended = self.get_major_recommendations(major, intent.get("is_freshman", True))
            
            if recommended:
                year_text = "freshman" if intent.get("is_freshman") else "student"
                course_list = ", ".join(recommended)
                
                # Try AI for a more personalized response
                ai_prompt = f"""A {year_text} {major} major at Rutgers is asking for course recommendations.
Recommended courses: {course_list}
Write a friendly 2-3 sentence response explaining why these courses are good starting points.
Be specific to Rutgers and the {major} major."""
                
                ai_response = self._call_gemini(ai_prompt)
                if ai_response:
                    return f"{ai_response}\n\nRecommended courses: **{course_list}**\n\nWould you like me to create a schedule with these courses?"
                else:
                    return f"For a {year_text} {major} major, I recommend starting with: **{course_list}**. These courses build the foundation for your major. Would you like me to create a schedule with these?"
            else:
                return f"I found your major ({major}) but don't have specific recommendations. Please tell me which courses you'd like to schedule, like 'Schedule 198:111 and 640:151'."
        
        # If it's a scheduling request but we couldn't understand it
        if intent["is_schedule_request"]:
            # Try AI for clarification
            ai_prompt = f"""A student asked: "{user_text}"
This seems like a course scheduling request but I couldn't identify specific courses.
Write a helpful response asking them to specify course codes (like 198:111) or course names (like 'Intro to CS').
Keep it brief and friendly."""
            
            ai_response = self._call_gemini(ai_prompt)
            if ai_response:
                return ai_response
            else:
                return "I'd love to help with your schedule! Please tell me which courses you need. You can use course codes like '198:111' or names like 'Intro to CS', 'Calc 1', etc."
        
        # Conversational/greeting response
        if intent["is_conversational"]:
            return "Hi there! I'm your Rutgers course scheduling assistant. Tell me which courses you want to take, or let me know your major and I can suggest courses for you!"
        
        # Default fallback
        return "I'm here to help you build your schedule! You can:\n• Give me course codes like '198:111' or 'Calc 1'\n• Tell me your major (e.g., 'I'm a CS major')\n• Add constraints like 'no Friday classes'"

    def chat_fallback(self, user_text: str) -> str:
        """Fallback for conversational messages."""
        return self.generate_response(user_text, {"is_conversational": True, "codes": [], "needs_recommendations": False, "detected_major": None, "constraints": {"no_days": []}})


# Initialize AI agent
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
    
    # Analyze intent using AI agent
    ai_result = ai_agent.analyze_intent(text)
    logger.info(f"Intent analysis: codes={ai_result['codes']}, major={ai_result.get('detected_major')}, needs_recs={ai_result.get('needs_recommendations')}")
    
    response_text = ""
    schedules_data = []
    
    # Handle different scenarios
    if ai_result['is_conversational'] and not ai_result['codes'] and not ai_result.get('needs_recommendations'):
        response_text = ai_agent.chat_fallback(text)
    
    elif ai_result.get('needs_recommendations') and ai_result.get('detected_major'):
        # Get recommended courses for the major
        recommended_codes = ai_agent.get_major_recommendations(
            ai_result['detected_major'], 
            ai_result.get('is_freshman', True)
        )
        
        if recommended_codes:
            # Try to schedule the recommended courses
            current_repo = DataServiceFactory.get_repository()
            courses_obj = current_repo.get_courses(recommended_codes)
            
            if courses_obj:
                scheduler = DeepSeekSchedulerStrategy()
                constraints = ScheduleConstraints(no_days=ai_result['constraints']['no_days'])
                schedules = scheduler.generate_schedules(courses_obj, constraints)
                
                if schedules:
                    schedules_data = _format_schedules_helper(schedules, courses_obj)
                    response_text = ai_agent.generate_response(text, ai_result, len(schedules))
                else:
                    response_text = ai_agent.generate_response(text, ai_result, 0)
            else:
                response_text = ai_agent.generate_response(text, ai_result, 0)
        else:
            response_text = ai_agent.generate_response(text, ai_result, 0)
    
    elif ai_result['codes']:
        # Schedule specific courses
        current_repo = DataServiceFactory.get_repository()
        courses_obj = current_repo.get_courses(ai_result['codes'])
        
        if not courses_obj:
            response_text = f"I couldn't find these courses in the database: {', '.join(ai_result['codes'])}. Please check the course codes and try again."
        else:
            scheduler = DeepSeekSchedulerStrategy()
            constraints = ScheduleConstraints(no_days=ai_result['constraints']['no_days'])
            schedules = scheduler.generate_schedules(courses_obj, constraints)
            
            if schedules:
                schedules_data = _format_schedules_helper(schedules, courses_obj)
                response_text = ai_agent.generate_response(text, ai_result, len(schedules))
            else:
                response_text = ai_agent.generate_response(text, ai_result, 0)
    else:
        # Couldn't understand the request
        response_text = ai_agent.generate_response(text, ai_result, 0)

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

@app.route('/api/degree_graph', methods=['GET'])
@login_required
def degree_graph_data():
    history = current_user.get_history()
    nodes = []
    edges = []
    
    for h in history:
        nodes.append({
            'data': {
                'id': h['short_code'], 
                'label': h['short_code'], 
                'color': '#4caf50'
            }
        })
        
    mock_prereqs = {
        '640:152': ['640:151'],
        '640:251': ['640:152'],
        '198:112': ['198:111'],
        '198:211': ['198:112'],
        '198:344': ['198:211', '198:205']
    }
    
    added_ids = {n['data']['id'] for n in nodes}
    
    for target, prereqs in mock_prereqs.items():
        for p in prereqs:
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