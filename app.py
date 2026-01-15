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
# Initialize repository early for AI agent
repo = DataServiceFactory.get_repository()
def load_history_background():
    logger.info("⏳ Starting background fetch of historical course titles...")
    repo.fetch_historical_titles()
    logger.info("✅ Background fetch complete.")

threading.Thread(target=load_history_background, daemon=True).start()


# --- DEPRECATED: OLD REGEX-BASED CODE (No longer used - AI handles this now) ---
# The system now uses AI-powered analysis via GeminiAgent
# Keeping minimal definitions to avoid linter errors for deprecated code
GREETINGS = []  # Deprecated - not used
COURSE_ALIASES = {}  # Deprecated - not used
COMMON_COURSES = {}  # Deprecated - not used
MAJOR_FRESHMAN_COURSES = {}  # Deprecated - not used

# --- DEPRECATED: OLD REGEX-BASED INTENT ANALYZER (No longer used) ---
class IntentAnalyzer:
    """DEPRECATED: Old regex-based intent analyzer. 
    No longer used - replaced by AI-powered GeminiAgent.analyze_intent()"""
    
    def __init__(self):
        self.day_mappings = {
            "monday": "M", "mon": "M", 
            "tuesday": "T", "tues": "T", "tue": "T",
            "wednesday": "W", "wed": "W",
            "thursday": "TH", "thurs": "TH", "thu": "TH",
            "friday": "F", "fri": "F"
        }

    def analyze(self, user_text: str) -> Dict:
        """DEPRECATED - Use GeminiAgent.analyze_intent() instead"""
        return {
            "codes": [],
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

    def _extract_course_codes(self, text: str) -> List[str]:
        """DEPRECATED - Use AI-powered analysis instead"""
        return []


class GeminiAgent:
    """AI-First Agent that uses Gemini API as the primary intelligence layer."""
    
    def __init__(self, api_keys, course_repository=None):
        self.api_keys = api_keys if isinstance(api_keys, list) else ([api_keys] if api_keys else [])
        self.course_repository = course_repository
        self.working_model = None
        self.last_request_time = 0
        self.min_request_interval = 0.5  # seconds
        
        # Models to try in order of preference (newer models first)
        self.models = [
            "gemini-3-pro",
            "gemini-3-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash-exp",
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
        
        models_to_try = [self.working_model] if self.working_model else self.models
        
        # Try different API endpoints for different model versions
        api_endpoints = [
            "v1beta",  # For newer models (2.0+, 3.0+)
            "v1",      # Fallback for older models
        ]
        
        for api_key in self.api_keys:
            for model in models_to_try:
                if not model:
                    continue
                
                # Try different API versions
                success = False
                for api_version in api_endpoints:
                    if success:
                        break
                        
                    for attempt in range(max_retries):
                        self._rate_limit_wait()
                        
                        url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={api_key}"
                        
                        payload = {
                            "contents": [{
                                "parts": [{"text": prompt}]
                            }],
                            "generationConfig": {
                                "temperature": 0.7,
                                "maxOutputTokens": 2048,
                                "topP": 0.95,
                                "topK": 40,
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
                                    self.working_model = model  # Cache working model
                                    logger.info(f"Gemini API success with model {model} using {api_version}")
                                    success = True
                                    return text.strip()
                            
                            elif response.status_code == 429:
                                wait_time = (2 ** attempt) * 2
                                logger.warning(f"Rate limited, waiting {wait_time}s...")
                                time.sleep(wait_time)
                                continue
                            
                            elif response.status_code == 404:
                                # Try next API version if this one fails
                                if api_version == api_endpoints[-1]:
                                    logger.warning(f"Model {model} not found with any API version, trying next model...")
                                break  # Break to try next API version
                            
                            elif response.status_code == 403:
                                logger.error(f"API key forbidden (403) - API may not be enabled for model {model}")
                                # Don't break here, try next model
                                break
                            
                            else:
                                error_text = response.text[:200] if hasattr(response, 'text') else str(response)
                                logger.warning(f"API error {response.status_code} for {model} ({api_version}): {error_text}")
                                # Try next API version
                                break
                                
                        except requests.Timeout:
                            logger.warning(f"Request timeout for model {model} ({api_version})")
                            # Try next API version
                            break
                        except Exception as e:
                            logger.error(f"API exception for {model} ({api_version}): {e}")
                            # Try next API version
                            break
                
                # If we found a working model, break out of model loop
                if self.working_model == model:
                    break
            
            # If we found a working model, break out of API key loop
            if self.working_model:
                break
        
        if not self.working_model:
            logger.error("All models failed. Check API key and model availability.")
        
        return None

    def _get_course_database_summary(self) -> str:
        """Get a summary of available courses for AI context."""
        if not self.course_repository:
            return "Course database not available."
        
        try:
            # Get a sample of courses for context (limit to avoid token limits)
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
            logger.error(f"Error getting course database summary: {e}")
            return "Course database error."

    def analyze_intent(self, user_text: str, conversation_history: List[Dict] = None, user_history: List[Dict] = None, major_context: str = "") -> Dict:
        """Analyze user intent using AI with full context."""
        conversation_history = conversation_history or []
        user_history = user_history or []
        
        # Build conversation context
        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')[:200]}"
                for msg in conversation_history[-5:]  # Last 5 messages
            ])
        
        # Build user course history context
        history_courses = []
        if user_history:
            history_courses = [h.get('short_code', '') for h in user_history[:20]]  # Last 20 courses
        
        # Get course database context
        course_db_context = self._get_course_database_summary()
        
        system_instruction = """You are an intelligent course scheduling assistant for Rutgers University. 
Your role is to understand student requests, extract course information, and provide helpful recommendations.
Always respond in valid JSON format when extracting structured data."""

        prompt = f"""Analyze this student's request and extract structured information.

STUDENT REQUEST: "{user_text}"

CONVERSATION HISTORY:
{history_text if history_text else "No previous conversation"}

STUDENT'S COURSE HISTORY (already taken):
{', '.join(history_courses) if history_courses else "No courses taken yet"}

MAJOR CONTEXT: {major_context if major_context else "Not specified"}

AVAILABLE COURSES (sample from database):
{course_db_context}

Extract the following information and respond ONLY with valid JSON:
{{
    "courses": ["198:111", "640:151"],  // Array of course codes in format XXX:YYY (extract from natural language)
    "course_names": ["intro to cs", "calculus 1"],  // Natural language course names mentioned
    "major": "computer science",  // Student's major if mentioned
    "constraints": {{
        "no_days": ["F"],  // Days to avoid: M, T, W, TH, F
        "preferred_times": ["morning", "afternoon"],  // Time preferences
        "max_courses": 5,  // Maximum number of courses
        "credits_target": 15  // Target credits
    }},
    "intent": "schedule" | "recommend" | "search" | "conversational" | "question" | "fill_schedule",
    "needs_recommendation": true,  // True if student needs course recommendations
    "fill_schedule": false,  // True if student wants to fill schedule to full credit load
    "is_freshman": false,  // True if student mentions being a freshman
    "explanation": "Brief explanation of what the student wants"
}}

IMPORTANT:
- Extract course codes from natural language (e.g., "CS 111" -> "198:111", "calc 1" -> "640:151")
- If course codes are ambiguous, include them in course_names and set needs_recommendation to true
- Be intelligent about understanding scheduling constraints from natural language
- If the request is conversational (greeting, question), set intent to "conversational" or "question"
"""

        ai_response = self._call_gemini(prompt, system_instruction)
        
        if ai_response:
            try:
                # Extract JSON from response
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    
                    # Map to our intent structure
                    result = {
                        "codes": parsed.get("courses", []),
                        "course_names": parsed.get("course_names", []),
                        "subjects": [],
                        "constraints": {
                            "no_days": parsed.get("constraints", {}).get("no_days", []),
                            "preferred_times": parsed.get("constraints", {}).get("preferred_times", []),
                            "max_courses": parsed.get("constraints", {}).get("max_courses"),
                            "credits_target": parsed.get("constraints", {}).get("credits_target")
                        },
                        "is_conversational": parsed.get("intent") in ["conversational", "question"],
                        "is_schedule_request": parsed.get("intent") in ["schedule", "fill_schedule"],
                        "needs_recommendations": parsed.get("needs_recommendation", False) or parsed.get("fill_schedule", False),
                        "fill_schedule": parsed.get("fill_schedule", False) or parsed.get("intent") == "fill_schedule",
                        "detected_major": parsed.get("major"),
                        "is_freshman": parsed.get("is_freshman", False),
                        "explanation": parsed.get("explanation", ""),
                        "confidence": 0.9 if parsed.get("courses") or parsed.get("course_names") else 0.6
                    }
                    
                    logger.info(f"AI Intent Analysis: {result}")
                    return result
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Could not parse AI response: {e}, raw response: {ai_response[:200]}")
        
        # Fallback to basic structure if AI fails
        return {
            "codes": [],
            "course_names": [],
            "subjects": [],
            "constraints": {"no_days": [], "preferred_times": [], "max_courses": None, "credits_target": None},
            "is_conversational": True,
            "is_schedule_request": False,
            "needs_recommendations": False,
            "fill_schedule": False,
            "detected_major": None,
            "is_freshman": False,
            "explanation": "",
            "confidence": 0.3
        }

    def search_courses_ai(self, query: str, limit: int = 10) -> List[str]:
        """Use AI to search for courses matching the query."""
        if not self.course_repository:
            return []
        
        course_db_context = self._get_course_database_summary()
        
        system_instruction = """You are a course search assistant. Find courses that match the student's query and return course codes in JSON format."""
        
        prompt = f"""Find courses matching this query: "{query}"

AVAILABLE COURSES:
{course_db_context}

Respond with JSON array of course codes that match:
["198:111", "640:151", ...]

Only return course codes in format XXX:YYY. Return up to {limit} courses."""

        ai_response = self._call_gemini(prompt, system_instruction)
        
        if ai_response:
            try:
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match:
                    courses = json.loads(json_match.group())
                    return courses[:limit]
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Could not parse course search response: {e}")
        
        # Fallback to repository search
        if self.course_repository:
            found_courses = self.course_repository.search_courses(query)
            return [c.code for c in found_courses[:limit]]
        
        return []

    def get_course_recommendations_ai(self, major: str = None, user_history: List[Dict] = None, constraints: Dict = None) -> List[str]:
        """Use AI to recommend courses based on major, history, and constraints."""
        user_history = user_history or []
        constraints = constraints or {}
        
        history_courses = [h.get('short_code', '') for h in user_history]
        course_db_context = self._get_course_database_summary()
        
        # Get major requirements if available
        major_reqs = []
        if major:
            for major_name, major_data in catalog_db.get("majors", {}).items():
                if major.lower() in major_name.lower():
                    major_reqs = major_data.get("requirements", [])
                    break
        
        system_instruction = """You are an academic advisor. Recommend courses based on the student's major, completed courses, and preferences."""
        
        fill_schedule = constraints.get('fill_schedule', False)
        credits_target = constraints.get('credits_target', None)
        
        prompt = f"""Recommend courses for a student at Rutgers University.

STUDENT'S MAJOR: {major if major else "Not specified"}

MAJOR REQUIREMENTS: {', '.join(major_reqs[:20]) if major_reqs else "Not available"}

COMPLETED COURSES (DO NOT RECOMMEND THESE - THEY ARE ALREADY TAKEN):
{', '.join(history_courses) if history_courses else "None - student has not taken any courses yet"}

CONSTRAINTS: {json.dumps(constraints)}

AVAILABLE COURSES:
{course_db_context}

{"FILL SCHEDULE REQUEST: The student wants to fill their schedule to reach a normal credit load." if fill_schedule else ""}
{"TARGET CREDITS: " + str(credits_target) if credits_target else ""}

CRITICAL: Recommend {"5-7" if fill_schedule else "3-5"} courses that:
1. Fit the student's major requirements OR are SAS core requirements (if no major specified)
2. Are appropriate next steps given their completed courses (prerequisites should be satisfied)
3. DO NOT include any courses from the COMPLETED COURSES list above
4. Respect any constraints mentioned (e.g., no Friday classes)
{"5. Help reach a full-time credit load (12-18 credits)" if fill_schedule else ""}

{"For filling schedule, prioritize:" if fill_schedule else ""}
{"- SAS core requirements the student hasn't completed (WCD, CCD, AH, NS, etc.)" if fill_schedule else ""}
{"- General education courses" if fill_schedule else ""}
{"- Courses that fit the student's major" if fill_schedule and major else ""}

Respond with JSON array of course codes:
["198:111", "640:151", ...]"""

        ai_response = self._call_gemini(prompt, system_instruction)
        
        if ai_response:
            try:
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match:
                    courses = json.loads(json_match.group())
                    return courses
            except (json.JSONDecodeError, AttributeError) as e:
                logger.warning(f"Could not parse recommendations: {e}")
        
        # Fallback to catalog
        if major_reqs:
            return major_reqs[:5]
        
        return []

    def generate_conversational_response(self, user_text: str, intent: Dict, conversation_history: List[Dict] = None, 
                                        schedules_found: int = 0, courses_found: List[Course] = None, 
                                        user_history: List[Dict] = None) -> str:
        """Generate intelligent conversational response using AI."""
        conversation_history = conversation_history or []
        courses_found = courses_found or []
        user_history = user_history or []
        
        # Build context
        history_text = "\n".join([
            f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')[:150]}"
            for msg in conversation_history[-3:]
        ])
        
        # Build course history context
        history_courses = []
        if user_history:
            history_courses = [f"{h.get('short_code', '')} - {h.get('title', '')}" for h in user_history[:20]]
        
        course_info = ""
        if courses_found:
            course_info = "\n".join([f"- {c.code}: {c.title}" for c in courses_found[:5]])
        
        system_instruction = """You are a friendly, helpful course scheduling assistant for Rutgers University. 
You have access to the student's course history. When recommending courses, ALWAYS check their completed courses first 
and DO NOT recommend courses they have already taken. Reference their completed courses naturally in your response.
Provide natural, conversational responses that are helpful and specific. Be concise but informative."""

        prompt = f"""Generate a helpful response to the student's request.

STUDENT REQUEST: "{user_text}"

CONVERSATION CONTEXT:
{history_text if history_text else "No previous conversation"}

STUDENT'S COMPLETED COURSES (IMPORTANT - DO NOT RECOMMEND THESE):
{chr(10).join(history_courses) if history_courses else "No courses completed yet"}

INTENT ANALYSIS:
- Courses requested: {', '.join(intent.get('codes', []))}
- Major: {intent.get('detected_major', 'Not specified')}
- Needs recommendations: {intent.get('needs_recommendations', False)}
- Schedules found: {schedules_found}

COURSES FOUND FOR SCHEDULING:
{course_info if course_info else "No courses found yet"}

IMPORTANT INSTRUCTIONS:
1. If the student asks about their course history or what they've taken, reference the COMPLETED COURSES list above
2. When recommending courses, check the COMPLETED COURSES list and DO NOT recommend anything already taken
3. If recommending next steps, mention what they've already completed and suggest logical next courses
4. Be specific and reference actual course codes when possible

Generate a natural, helpful response (2-4 sentences). Be specific about courses and next steps.
If schedules were found, mention it. Reference their completed courses when relevant."""

        ai_response = self._call_gemini(prompt, system_instruction)
        
        if ai_response:
            return ai_response.strip()
        
        # Fallback response
        if schedules_found > 0:
            return f"I found {schedules_found} possible schedule(s) for you! Check the schedules below."
        elif intent.get('codes'):
            return f"I'm working on finding schedules for {', '.join(intent['codes'])}. Let me search the database..."
        else:
            return "I'm here to help you build your schedule! Tell me which courses you'd like to take, or your major for recommendations."


# Initialize AI agent with course repository (using repo from above)
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
        chat.updated_at = datetime.now(timezone.utc)
        if chat.title == "New Chat":
            chat.title = text[:30] + "..."
            
    user_msg = Message(chat_id=chat.id, role='user', content=text)
    db.session.add(user_msg)
    db.session.flush()  # Flush to get timestamp
    
    # Get conversation history
    previous_messages = Message.query.filter_by(chat_id=chat.id).order_by(Message.timestamp.asc()).all()
    conversation_history = [
        {"role": msg.role, "content": msg.content}
        for msg in previous_messages[-10:]  # Last 10 messages for context
    ]
    
    # Get user's course history
    user_history = current_user.get_history()
    
    # Analyze intent using AI with full context
    ai_result = ai_agent.analyze_intent(
        text, 
        conversation_history=conversation_history,
        user_history=user_history,
        major_context=""  # Could be extracted from user profile in future
    )
    logger.info(f"AI Intent analysis: {ai_result}")
    
    response_text = ""
    schedules_data = []
    courses_obj = []
    
    # Handle course search if course names were mentioned but codes weren't found
    if ai_result.get('course_names') and not ai_result.get('codes'):
        # Use AI to search for courses
        for course_name in ai_result['course_names'][:3]:  # Limit to 3 searches
            found_codes = ai_agent.search_courses_ai(course_name, limit=5)
            ai_result['codes'].extend(found_codes)
        ai_result['codes'] = list(set(ai_result['codes']))  # Remove duplicates
    
    # Check if user wants to fill schedule to normal credit load
    fill_schedule = ai_result.get('fill_schedule', False) or any(phrase in text.lower() for phrase in [
        "fill", "complete", "full schedule", "normal credit", "full credit load", 
        "reach", "get to", "make it", "fill the rest"
    ])
    credits_target = ai_result.get('constraints', {}).get('credits_target', 15 if fill_schedule else None)
    
    # Handle recommendations
    if ai_result.get('needs_recommendations') or fill_schedule:
        if ai_result.get('detected_major') or fill_schedule:
            # Get AI-powered recommendations
            recommended_codes = ai_agent.get_course_recommendations_ai(
                major=ai_result.get('detected_major'),
                user_history=user_history,
                constraints={
                    **ai_result.get('constraints', {}),
                    'fill_schedule': fill_schedule,
                    'credits_target': credits_target
                }
            )
            if recommended_codes:
                ai_result['codes'].extend(recommended_codes)
                ai_result['codes'] = list(set(ai_result['codes']))
    
    # Get courses from database
    if ai_result.get('codes'):
        current_repo = DataServiceFactory.get_repository()
        courses_obj = current_repo.get_courses(ai_result['codes'])
        
        # If courses not found, try AI search for alternatives
        if not courses_obj and ai_result.get('course_names'):
            logger.info("Courses not found, trying AI search for alternatives...")
            for course_name in ai_result['course_names'][:2]:
                alternative_codes = ai_agent.search_courses_ai(course_name, limit=3)
                if alternative_codes:
                    alt_courses = current_repo.get_courses(alternative_codes)
                    if alt_courses:
                        courses_obj.extend(alt_courses)
                        break
        
        # If user wants to fill schedule and we have few courses, add more
        if fill_schedule and courses_obj:
            current_credits = sum(getattr(c, 'credits', 3) for c in courses_obj)
            if credits_target and current_credits < credits_target:
                needed_credits = credits_target - current_credits
                logger.info(f"Filling schedule: have {current_credits} credits, need {needed_credits} more")
                
                # Get additional course recommendations
                additional_codes = ai_agent.get_course_recommendations_ai(
                    major=ai_result.get('detected_major'),
                    user_history=user_history,
                    constraints={
                        **ai_result.get('constraints', {}),
                        'credits_target': needed_credits,
                        'fill_schedule': True
                    }
                )
                
                if additional_codes:
                    # Filter out already selected courses
                    existing_codes = {c.code for c in courses_obj}
                    new_codes = [code for code in additional_codes if code not in existing_codes]
                    
                    if new_codes:
                        additional_courses = current_repo.get_courses(new_codes[:5])  # Limit to 5 additional
                        courses_obj.extend(additional_courses)
                        logger.info(f"Added {len(additional_courses)} additional courses to reach credit target")
    
    # Generate schedules if we have courses
    if courses_obj:
        scheduler = DeepSeekSchedulerStrategy()
        constraints = ScheduleConstraints(no_days=ai_result['constraints']['no_days'])
        schedules = scheduler.generate_schedules(courses_obj, constraints)
        
        if schedules:
            schedules_data = _format_schedules_helper(schedules, courses_obj)
    
    # Generate AI-powered conversational response
    response_text = ai_agent.generate_conversational_response(
        user_text=text,
        intent=ai_result,
        conversation_history=conversation_history,
        schedules_found=len(schedules_data),
        courses_found=courses_obj,
        user_history=user_history  # Pass course history to response generator
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