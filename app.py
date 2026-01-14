"""
Scarlet Scheduler AI - v1.3.0
An intelligent course scheduling assistant for Rutgers University students.

v1.3.0 Changes:
- Fixed Gemini API model names to match actual available models
- Added exponential backoff for rate limiting (429 errors)
- Added request throttling to avoid rate limits
- Improved error handling and logging
- Cache working model to reduce API discovery overhead
"""

import os
import re
import json
import logging
import requests
import time
from typing import List, Dict, Optional, Tuple
from flask import Flask, render_template, request, jsonify, session
from config import get_config, validate_config
from data_adapter import DataServiceFactory
from scheduler_strategies import DeepSeekSchedulerStrategy
from scheduler_core import ScheduleConstraints, Course
from prerequisite_parser import PrerequisiteParser

# --- VERSION ---
VERSION = "1.3.0"

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
    logger.info(f"Data file found at: {found_data_path}")

# Log version at startup
logger.info(f"🚀 Scarlet Scheduler v{VERSION} starting...")

# Load Major/Minor Requirements
catalog_db = {}
major_path = os.path.join(base_dir, majors_filename)
if os.path.exists(major_path):
    try:
        with open(major_path, 'r', encoding='utf-8') as f:
            catalog_db = json.load(f)
        if "majors" not in catalog_db:
            catalog_db = {"majors": catalog_db, "minors": {}, "certificates": {}}
        m = len(catalog_db.get('majors', {}))
        mi = len(catalog_db.get('minors', {}))
        c = len(catalog_db.get('certificates', {}))
        logger.info(f"✅ Loaded Catalog: {m} Majors, {mi} Minors, {c} Certs.")
    except Exception as e:
        logger.error(f"❌ Failed to load catalog: {e}")
else:
    logger.warning("⚠️ major_requirements.json NOT FOUND. Run pdf_scraper.py first.")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# --- CONSTANTS ---
GREETINGS = ["hello", "hi", "hey", "greetings", "sup", "yo", "what's up", "howdy"]
COURSE_CODE_PATTERN = re.compile(r'(\d{2,3})[:\s\-]?(\d{3})')

# Common course name mappings
COURSE_ALIASES = {
    "cs": "198",
    "computer science": "198",
    "comp sci": "198",
    "math": "640",
    "calc": "640",
    "calculus": "640",
    "econ": "220",
    "economics": "220",
    "physics": "750",
    "phys": "750",
    "chem": "160",
    "chemistry": "160",
    "bio": "119",
    "biology": "119",
    "psych": "830",
    "psychology": "830",
    "expos": "355",
    "writing": "355",
    "stats": "960",
    "statistics": "960",
    "data science": "198",
    "data structures": "198:112",
    "intro to cs": "198:111",
    "linear algebra": "640:250",
    "discrete": "640:477",
    "algorithms": "198:344",
    "calc 1": "640:151",
    "calc 2": "640:152",
    "calc 3": "640:251",
    "diff eq": "640:244",
}

# Common course number mappings
COMMON_COURSES = {
    # Computer Science
    "intro to computer science": "198:111",
    "intro to cs": "198:111",
    "cs 111": "198:111",
    "cs111": "198:111",
    "computer science 111": "198:111",
    "data structures": "198:112",
    "cs 112": "198:112",
    "cs112": "198:112",
    "discrete structures": "198:205",
    "discrete math": "198:205",
    "cs 205": "198:205",
    "systems programming": "198:211",
    "cs 211": "198:211",
    "design and analysis of algorithms": "198:344",
    "algorithms": "198:344",
    
    # Math/Calculus
    "calc 1": "640:151",
    "calc1": "640:151",
    "calculus 1": "640:151",
    "calculus i": "640:151",
    "calc i": "640:151",
    "calc 2": "640:152",
    "calc2": "640:152",
    "calculus 2": "640:152",
    "calculus ii": "640:152",
    "calc ii": "640:152",
    "calc 3": "640:251",
    "calc3": "640:251",
    "calculus 3": "640:251",
    "multivariable calculus": "640:251",
    "linear algebra": "640:250",
    "intro to linear algebra": "640:250",
    "intro linear algebra": "640:250",
    
    # Economics
    "intro to econ": "220:102",
    "intro econ": "220:102",
    "intro to economics": "220:102",
    "intro to microeconomics": "220:102",
    "introduction to microeconomics": "220:102",
    "principles of economics micro": "220:102",
    "principles of microeconomics": "220:102",
    "microeconomics": "220:102",
    "micro econ": "220:102",
    "micro": "220:102",
    "econ 102": "220:102",
    "intro to macroeconomics": "220:103",
    "introduction to macroeconomics": "220:103",
    "principles of economics macro": "220:103",
    "principles of macroeconomics": "220:103",
    "macroeconomics": "220:103",
    "macro econ": "220:103",
    "macro": "220:103",
    "econ 103": "220:103",
    
    # Physics
    "general physics 1": "750:203",
    "physics 1": "750:203",
    "physics i": "750:203",
    "general physics 2": "750:204",
    "physics 2": "750:204",
    "physics ii": "750:204",
    
    # Chemistry
    "general chemistry 1": "160:161",
    "gen chem 1": "160:161",
    "gen chem": "160:161",
    "chem 1": "160:161",
    "general chemistry 2": "160:162",
    "gen chem 2": "160:162",
    "chem 2": "160:162",
    
    # Biology
    "intro to biology": "119:115",
    "general biology": "119:115",
    "bio 115": "119:115",
    
    # Writing
    "expository writing": "355:101",
    "expos": "355:101",
    "expo": "355:101",
    "college writing": "355:101",
    "english comp": "355:101",
    
    # Psychology
    "intro to psychology": "830:101",
    "intro to psych": "830:101",
    "intro psych": "830:101",
    "general psychology": "830:101",
    "psych 101": "830:101",
    
    # Statistics
    "intro to statistics": "960:211",
    "intro to stats": "960:211",
    "basic statistics": "960:211",
    "stats 211": "960:211",
}


class IntentAnalyzer:
    """
    Improved local intent analyzer that works without AI.
    Parses user intent using pattern matching and heuristics.
    """
    
    def __init__(self):
        self.day_mappings = {
            "monday": "M", "mon": "M", "m": "M",
            "tuesday": "T", "tues": "T", "tue": "T",
            "wednesday": "W", "wed": "W",
            "thursday": "TH", "thurs": "TH", "thu": "TH", "th": "TH",
            "friday": "F", "fri": "F",
            "saturday": "S", "sat": "S",
            "sunday": "SU", "sun": "SU"
        }
        
        self.time_constraints = {
            "morning": (0, 720),      # Before noon
            "afternoon": (720, 1020), # 12pm - 5pm
            "evening": (1020, 1440),  # After 5pm
            "early": (0, 600),        # Before 10am
            "late": (900, 1440),      # After 3pm
        }
    
    def analyze(self, user_text: str, history: List[Dict] = None, 
                major_context: str = "") -> Dict:
        """
        Analyze user intent and extract structured information.
        """
        lower_text = user_text.lower().strip()
        history = history or []
        
        result = {
            "codes": [],
            "subjects": [],
            "constraints": {
                "no_days": [],
                "preferred_times": [],
                "max_courses": None,
                "credits_target": None,
            },
            "is_conversational": False,
            "is_schedule_request": False,
            "is_info_request": False,
            "needs_recommendations": False,
            "major_mentioned": None,
            "explanation": "",
            "confidence": 0.0
        }
        
        # Check if purely conversational
        if self._is_conversational(lower_text):
            result["is_conversational"] = True
            return result
        
        # Extract course codes
        result["codes"] = self._extract_course_codes(user_text)
        
        # Extract named courses
        named_courses = self._extract_named_courses(lower_text)
        for code in named_courses:
            if code not in result["codes"]:
                result["codes"].append(code)
        
        # Extract subject areas
        result["subjects"] = self._extract_subjects(lower_text)
        
        # Extract day constraints
        result["constraints"]["no_days"] = self._extract_day_constraints(lower_text)
        
        # Extract time preferences
        result["constraints"]["preferred_times"] = self._extract_time_preferences(lower_text)
        
        # Extract credit/course count targets
        result["constraints"]["max_courses"], result["constraints"]["credits_target"] = \
            self._extract_quantity_constraints(lower_text)
        
        # Check for major mentions
        result["major_mentioned"] = self._extract_major(lower_text)
        
        # Determine request type
        schedule_keywords = ["schedule", "class", "course", "register", "sign up", 
                          "enroll", "take", "need", "want", "planning", "next semester"]
        info_keywords = ["what is", "tell me about", "info", "information", 
                        "prerequisite", "prereq", "credit", "describe"]
        
        if any(kw in lower_text for kw in schedule_keywords):
            result["is_schedule_request"] = True
        if any(kw in lower_text for kw in info_keywords):
            result["is_info_request"] = True
        
        # Check if user needs recommendations
        rec_keywords = ["recommend", "suggest", "fill", "complete", "help me pick",
                       "what should i take", "best courses", "which classes"]
        if any(kw in lower_text for kw in rec_keywords):
            result["needs_recommendations"] = True
        
        # If major mentioned but no specific codes, needs recommendations
        if result["major_mentioned"] and not result["codes"]:
            result["needs_recommendations"] = True
        
        # Calculate confidence
        result["confidence"] = self._calculate_confidence(result)
        
        # Generate explanation
        result["explanation"] = self._generate_explanation(result)
        
        return result
    
    def _is_conversational(self, text: str) -> bool:
        """Check if this is just a greeting or casual chat."""
        greetings = ["hello", "hi", "hey", "greetings", "sup", "yo", "howdy",
                    "good morning", "good afternoon", "good evening", "thanks",
                    "thank you", "bye", "goodbye", "see you"]
        
        # Pure greeting
        if text.strip().lower() in greetings:
            return True
        
        # Greeting with minimal content
        words = text.split()
        if len(words) <= 3 and any(g in text for g in greetings):
            return True
        
        return False
    
    def _extract_course_codes(self, text: str) -> List[str]:
        """Extract course codes from text."""
        codes = []
        
        # Pattern: XXX:YYY or XX:YYY:ZZZ
        full_pattern = re.compile(r'(\d{2,3}):(\d{3}):?(\d{3})?')
        for match in full_pattern.finditer(text):
            if match.group(3):
                # Full code: 01:198:111 -> 198:111
                codes.append(f"{match.group(2)}:{match.group(3)}")
            else:
                codes.append(f"{match.group(1)}:{match.group(2)}")
        
        # Pattern: XXX YYY (with space)
        space_pattern = re.compile(r'\b(\d{3})\s+(\d{3})\b')
        for match in space_pattern.finditer(text):
            code = f"{match.group(1)}:{match.group(2)}"
            if code not in codes:
                codes.append(code)
        
        return list(set(codes))
    
    def _extract_named_courses(self, text: str) -> List[str]:
        """Extract courses mentioned by name."""
        codes = []
        
        for name, code in COMMON_COURSES.items():
            if name in text:
                codes.append(code)
        
        return codes
    
    def _extract_subjects(self, text: str) -> List[str]:
        """Extract subject areas from text."""
        subjects = []
        
        for alias, code in COURSE_ALIASES.items():
            if alias in text and len(alias) > 2:  # Avoid single letters
                if ":" not in code:  # Subject code only
                    # Map to full subject name
                    subject_map = {
                        "198": "Computer Science",
                        "640": "Mathematics",
                        "220": "Economics",
                        "750": "Physics",
                        "160": "Chemistry",
                        "119": "Biology",
                        "830": "Psychology",
                        "355": "Writing",
                        "960": "Statistics",
                    }
                    if code in subject_map:
                        subjects.append(subject_map[code])
        
        return list(set(subjects))
    
    def _extract_day_constraints(self, text: str) -> List[str]:
        """Extract day constraints (e.g., 'no Friday', 'avoid classes on Mondays')."""
        no_days = []
        
        # Words that should NOT be matched as days
        exclude_words = {'morning', 'mornings', 'month', 'months', 'money', 'monkey', 
                        'monitor', 'moment', 'more', 'move', 'most', 'mother'}
        
        negative_words = ['no', 'not', 'avoid', 'skip', 'without', 'free', "don't", "cant", "can't", "cannot"]
        
        has_negative = any(neg in text.lower() for neg in negative_words)
        
        if has_negative:
            for day_name, day_code in self.day_mappings.items():
                if len(day_name) < 3:
                    continue
                    
                day_pattern = rf'\b{day_name}s?\b'
                if re.search(day_pattern, text, re.IGNORECASE):
                    found_match = re.search(day_pattern, text, re.IGNORECASE)
                    if found_match:
                        matched_word = found_match.group(0).lower().rstrip('s')
                        if matched_word not in exclude_words:
                            patterns = [
                                rf'\b(?:no|avoid|skip|without)\s+(?:\w+\s+)*{day_name}',
                                rf'\b{day_name}\w*\s+(?:off|free)',
                                rf"(?:don't|cant|can't|cannot)\s+(?:\w+\s+)*{day_name}",
                            ]
                            for pattern in patterns:
                                if re.search(pattern, text, re.IGNORECASE):
                                    if day_code not in no_days:
                                        no_days.append(day_code)
                                    break
        
        # Pattern: "[day]s off"
        off_pattern = re.compile(r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\s+off', re.IGNORECASE)
        for match in off_pattern.finditer(text):
            day_word = match.group(1).lower()
            if day_word in self.day_mappings:
                day_code = self.day_mappings[day_word]
                if day_code not in no_days:
                    no_days.append(day_code)
        
        # Pattern: "only [days]" - means exclude other days
        only_pattern = re.compile(r'\bonly\s+(?:on\s+)?((?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:s)?(?:\s+(?:and\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)(?:s)?)*)', re.IGNORECASE)
        only_match = only_pattern.search(text)
        if only_match:
            only_days_str = only_match.group(1).lower()
            wanted_days = set()
            for day_name, day_code in self.day_mappings.items():
                if len(day_name) >= 3 and day_name in only_days_str:
                    wanted_days.add(day_code)
            if wanted_days:
                all_days = {'M', 'T', 'W', 'TH', 'F'}
                for day in all_days - wanted_days:
                    if day not in no_days:
                        no_days.append(day)
        
        return list(set(no_days))
    
    def _extract_time_preferences(self, text: str) -> List[str]:
        """Extract time preferences."""
        prefs = []
        
        for time_name in self.time_constraints:
            if time_name in text:
                prefs.append(time_name)
        
        no_time_pattern = re.compile(r'\bno\s+(\w+)', re.IGNORECASE)
        for match in no_time_pattern.finditer(text):
            time_word = match.group(1).lower().rstrip('s')
            if time_word in self.time_constraints:
                prefs.append(f"no_{time_word}")
        
        return prefs
    
    def _extract_quantity_constraints(self, text: str) -> Tuple[Optional[int], Optional[int]]:
        """Extract number of courses or credits target."""
        max_courses = None
        credits_target = None
        
        course_pattern = re.compile(r'(\d+)\s*(?:courses?|classes?)', re.IGNORECASE)
        match = course_pattern.search(text)
        if match:
            max_courses = int(match.group(1))
        
        credit_pattern = re.compile(r'(\d+)\s*credits?', re.IGNORECASE)
        match = credit_pattern.search(text)
        if match:
            credits_target = int(match.group(1))
        
        if "full load" in text or "full schedule" in text:
            credits_target = 15
        
        if "part time" in text or "part-time" in text:
            credits_target = 9
        
        return max_courses, credits_target
    
    def _extract_major(self, text: str) -> Optional[str]:
        """Extract mentioned major/minor."""
        for category in ["majors", "minors"]:
            for name in catalog_db.get(category, {}):
                clean_name = name.lower().strip()
                if len(clean_name) > 4 and clean_name in text:
                    return name
        
        major_aliases = {
            "cs major": "Computer Science",
            "comp sci major": "Computer Science",
            "econ major": "Economics",
            "math major": "Mathematics",
            "bio major": "Biological Sciences",
            "psych major": "Psychology",
        }
        
        for alias, major in major_aliases.items():
            if alias in text:
                return major
        
        return None
    
    def _calculate_confidence(self, result: Dict) -> float:
        """Calculate confidence score for the analysis."""
        score = 0.0
        
        if result["codes"]:
            score += 0.4
        if result["subjects"]:
            score += 0.2
        if result["major_mentioned"]:
            score += 0.2
        if result["is_schedule_request"]:
            score += 0.1
        if result["constraints"]["no_days"]:
            score += 0.1
        
        return min(score, 1.0)
    
    def _generate_explanation(self, result: Dict) -> str:
        """Generate human-readable explanation of parsed intent."""
        parts = []
        
        if result["codes"]:
            parts.append(f"Requested courses: {', '.join(result['codes'])}")
        if result["subjects"]:
            parts.append(f"Subject areas: {', '.join(result['subjects'])}")
        if result["major_mentioned"]:
            parts.append(f"Major: {result['major_mentioned']}")
        if result["constraints"]["no_days"]:
            parts.append(f"Avoid days: {', '.join(result['constraints']['no_days'])}")
        if result["constraints"]["credits_target"]:
            parts.append(f"Target credits: {result['constraints']['credits_target']}")
        
        return "; ".join(parts) if parts else "General scheduling request"


class GeminiAgent:
    """
    Enhanced AI agent with robust rate limiting and proper model handling.
    
    v1.3.0 Changes:
    - Fixed model names to match actual Google API models
    - Added exponential backoff for 429 rate limit errors
    - Added request throttling
    - Cache working model for efficiency
    """
    
    # Rate limiting configuration
    MIN_REQUEST_INTERVAL = 1.0  # Minimum seconds between requests
    INITIAL_BACKOFF = 2.0       # Initial backoff on 429 error
    MAX_BACKOFF = 60.0          # Maximum backoff time
    MAX_RETRIES = 5             # Max retries per request
    
    def __init__(self, api_keys):
        self.api_keys = api_keys if isinstance(api_keys, list) else ([api_keys] if api_keys else [])
        self.current_key_index = 0
        
        # v1beta endpoint is required for newer models
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        
        # FIXED: Use actual model names that exist on Google's API
        # These are confirmed working as of Jan 2026 from the logs
        self.preferred_models = [
            "gemini-2.0-flash-lite",      # Fastest, most reliable for free tier
            "gemini-2.0-flash",           # Good balance of speed/quality
            "gemini-2.5-flash-lite",      # Newer lite model
            "gemini-2.5-flash",           # Newer full model
        ]
        
        # Cache the working model to avoid repeated discovery
        self._working_model = None
        self._last_request_time = 0
        self._current_backoff = self.INITIAL_BACKOFF
        
        self.local_analyzer = IntentAnalyzer()
        self._available_models = []
        
        if self.api_keys:
            self._discover_and_cache_models()
    
    def is_available(self) -> bool:
        """Check if AI is available."""
        return bool(self.api_keys)
    
    def get_api_status(self) -> Dict[str, any]:
        """Get detailed API status for diagnostics."""
        status = {
            "has_keys": bool(self.api_keys),
            "num_keys": len(self.api_keys) if self.api_keys else 0,
            "working_model": self._working_model,
            "available_models": self._available_models,
            "api_enabled": None,  # Will be determined by testing
        }
        
        if self.api_keys:
            # Quick test to see if API is enabled
            key = self._get_current_key()
            try:
                url = f"{self.base_url}?key={key}"
                response = requests.get(url, timeout=5)
                status["api_enabled"] = response.status_code == 200
                if response.status_code == 403:
                    status["error"] = "API not enabled - enable at https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com"
            except Exception as e:
                status["error"] = str(e)
        
        return status

    def _get_current_key(self):
        if not self.api_keys: 
            return None
        return self.api_keys[self.current_key_index % len(self.api_keys)]

    def _rotate_key(self) -> bool:
        """Rotate to the next API key. Returns True if successful."""
        if len(self.api_keys) > 1:
            old_index = self.current_key_index
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            # Only log if we actually rotated to a different key
            if self.current_key_index != old_index:
                logger.info(f"🔄 Rotating to API Key #{self.current_key_index + 1}")
                # Reset backoff when rotating keys
                self._current_backoff = self.INITIAL_BACKOFF
                return True
        return False
    
    def _throttle_request(self):
        """Ensure minimum time between requests to avoid rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.MIN_REQUEST_INTERVAL:
            sleep_time = self.MIN_REQUEST_INTERVAL - elapsed
            logger.debug(f"Throttling: waiting {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_request_time = time.time()
    
    def _handle_rate_limit(self, retry_count: int) -> float:
        """Calculate backoff time for rate limit. Returns sleep duration."""
        # Exponential backoff with jitter
        backoff = min(
            self._current_backoff * (2 ** retry_count),
            self.MAX_BACKOFF
        )
        # Add some jitter (±20%)
        import random
        jitter = backoff * 0.2 * (random.random() * 2 - 1)
        sleep_time = backoff + jitter
        
        logger.info(f"⏳ Rate limited. Waiting {sleep_time:.1f}s before retry...")
        return sleep_time

    def _discover_and_cache_models(self):
        """Query Google to discover available models and cache them."""
        key = self._get_current_key()
        if not key:
            return
        
        try:
            url = f"{self.base_url}?key={key}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                self._available_models = [
                    m['name'].replace('models/', '') 
                    for m in data.get('models', []) 
                    if 'generateContent' in m.get('supportedGenerationMethods', [])
                ]
                logger.info(f"🔎 Available Gemini Models: {self._available_models}")
                
                # Reorder preferred models based on availability
                available_set = set(self._available_models)
                working_models = [m for m in self.preferred_models if m in available_set]
                
                if working_models:
                    self._working_model = working_models[0]
                    logger.info(f"✅ Selected primary model: {self._working_model}")
                else:
                    # Try to find any flash model
                    for model in self._available_models:
                        if 'flash' in model.lower() and 'lite' in model.lower():
                            self._working_model = model
                            logger.info(f"✅ Auto-selected model: {self._working_model}")
                            break
            elif response.status_code == 403:
                logger.error("❌ 403 Forbidden - The Generative Language API may not be enabled.")
                logger.error("   Enable it at: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
            else:
                logger.warning(f"Failed to list models: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Model discovery error: {e}")

    def _generate(self, prompt_text: str, timeout: int = 30) -> Optional[str]:
        """
        Generate text using Gemini API with proper rate limiting and backoff.
        """
        if not self.api_keys:
            return None
        
        # Get models to try (prioritize cached working model)
        models_to_try = []
        if self._working_model:
            models_to_try.append(self._working_model)
        for m in self.preferred_models:
            if m not in models_to_try:
                models_to_try.append(m)
        
        keys_tried = set()
        retry_count = 0
        
        while retry_count < self.MAX_RETRIES:
            current_key = self._get_current_key()
            if not current_key:
                return None
            
            # Track which keys we've tried
            key_index = self.current_key_index
            if key_index in keys_tried and len(keys_tried) >= len(self.api_keys):
                # We've tried all keys
                break
            
            # Throttle requests
            self._throttle_request()
            
            headers = {'Content-Type': 'application/json'}
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1024,
                }
            }
            
            for model in models_to_try:
                url = f"{self.base_url}/{model}:generateContent?key={current_key}"
                
                try:
                    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if 'candidates' in data and data['candidates']:
                            # Success! Cache this model as working
                            if model != self._working_model:
                                self._working_model = model
                                logger.info(f"✅ Caching working model: {model}")
                            
                            # Reset backoff on success
                            self._current_backoff = self.INITIAL_BACKOFF
                            
                            text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                            if text:
                                logger.info(f"✅ Success with model: {model}")
                                return text
                    
                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        logger.warning(f"⚠️ Rate Limited (429) on {model}")
                        sleep_time = self._handle_rate_limit(retry_count)
                        time.sleep(sleep_time)
                        retry_count += 1
                        break  # Break inner loop to retry with same key after waiting
                    
                    elif response.status_code == 404:
                        # Model not found - try next model
                        logger.debug(f"Model {model} not found (404)")
                        continue
                    
                    elif response.status_code == 403:
                        # Forbidden - API not enabled or key invalid
                        logger.warning(f"❌ Forbidden (403) on {model} - API may not be enabled")
                        keys_tried.add(key_index)
                        if self._rotate_key():
                            break  # Try next key
                        continue
                    
                    elif response.status_code == 400:
                        # Bad request - log and try next model
                        error_msg = response.json().get('error', {}).get('message', 'Unknown error')
                        logger.warning(f"❌ Bad Request (400) on {model}: {error_msg[:100]}")
                        continue
                    
                    else:
                        logger.warning(f"❌ Error {response.status_code} on {model}")
                        continue
                
                except requests.Timeout:
                    logger.warning(f"⏱️ Timeout on {model}")
                    continue
                except requests.RequestException as e:
                    logger.error(f"🔌 Connection error on {model}: {e}")
                    continue
            else:
                # All models failed for this key, rotate
                keys_tried.add(key_index)
                if not self._rotate_key():
                    break  # No more keys to try
                retry_count += 1
        
        logger.error("❌ All API attempts exhausted.")
        return None

    def analyze_intent(self, user_text: str, history_context: str = "", 
                      major_context: str = "") -> Dict:
        """
        Analyze user intent using AI with local fallback.
        """
        # First, try local analysis
        local_result = self.local_analyzer.analyze(user_text)
        
        # If high confidence or no AI available, use local result
        if local_result["confidence"] >= 0.6 or not self.is_available():
            logger.info(f"Using local analysis (confidence: {local_result['confidence']:.2f})")
            return self._convert_local_to_legacy(local_result)
        
        # Try AI for complex queries
        prompt = self._build_intent_prompt(user_text, history_context, major_context)
        raw_text = self._generate(prompt)
        
        if not raw_text:
            logger.info("AI unavailable, using local analysis")
            return self._convert_local_to_legacy(local_result)
        
        try:
            text = raw_text.replace("```json", "").replace("```", "").strip()
            ai_result = json.loads(text)
            
            # Merge AI results with local results
            return self._merge_results(local_result, ai_result)
            
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response, using local analysis")
            return self._convert_local_to_legacy(local_result)
    
    def _build_intent_prompt(self, user_text: str, history_context: str, 
                            major_context: str) -> str:
        """Build a comprehensive intent analysis prompt."""
        return f"""You are an expert Rutgers University academic advisor.

STUDENT CONTEXT:
- Completed Courses: {history_context if history_context else "None provided"}
- Major/Minor Info: {major_context if major_context else "None specified"}

TASK: Analyze this student request and extract scheduling intent.

Student said: "{user_text}"

ANALYSIS RULES:
1. Extract ONLY explicitly mentioned course codes (format: XXX:YYY like 198:111)
2. Identify subject areas mentioned (Computer Science, Math, Economics, etc.)
3. Extract scheduling constraints ONLY if explicitly stated
4. Determine if user wants specific courses or recommendations

Return ONLY valid JSON:
{{"codes": [], "subjects": [], "constraints": [], "is_conversational": false, "needs_recommendations": false, "explanation": ""}}"""
    
    def _convert_local_to_legacy(self, local_result: Dict) -> Dict:
        """Convert local analysis to legacy format expected by app.py"""
        return {
            "codes": local_result["codes"],
            "subjects": local_result["subjects"],
            "constraints": local_result["constraints"]["no_days"],
            "is_conversational": local_result["is_conversational"],
            "needs_recommendations": local_result["needs_recommendations"],
            "explanation": local_result["explanation"]
        }
    
    def _merge_results(self, local: Dict, ai: Dict) -> Dict:
        """Merge local and AI analysis results."""
        merged = {
            "codes": list(set(local["codes"] + ai.get("codes", []))),
            "subjects": list(set(local["subjects"] + ai.get("subjects", []))),
            "constraints": list(set(
                local["constraints"]["no_days"] + 
                ai.get("constraints", [])
            )),
            "is_conversational": local["is_conversational"] or ai.get("is_conversational", False),
            "needs_recommendations": local["needs_recommendations"] or ai.get("needs_recommendations", False),
            "explanation": ai.get("explanation", local["explanation"])
        }
        
        if "recommended_courses" in ai and ai["recommended_courses"]:
            for code in ai["recommended_courses"]:
                if code not in merged["codes"]:
                    merged["codes"].append(code)
        
        return merged

    def chat_fallback(self, user_text: str) -> str:
        """Generate a helpful response for conversational queries."""
        if not self.is_available():
            return self._get_static_response(user_text)
        
        prompt = f"""You are a friendly Rutgers University course scheduling assistant.
The student said: "{user_text}"

Provide a helpful, concise response. If they seem to need scheduling help, 
encourage them to tell you which courses they need or what major they're in.

Keep the response under 100 words."""
        
        response = self._generate(prompt)
        return response if response else self._get_static_response(user_text)
    
    def _get_static_response(self, user_text: str) -> str:
        """Provide helpful static responses when AI is unavailable."""
        lower = user_text.lower()
        
        if any(g in lower for g in GREETINGS):
            return ("Hello! I'm your Rutgers course scheduler. "
                   "Tell me which courses you need (like '198:111' or 'Intro to CS'), "
                   "and I'll help you build a schedule. You can also mention your major "
                   "for personalized recommendations!")
        
        if "help" in lower:
            return ("I can help you schedule courses! Try:\n"
                   "• 'Schedule CS 111 and Calc 1'\n"
                   "• 'I'm a CS major, need 15 credits, no Fridays'\n"
                   "• 'What CS courses should I take?'\n"
                   "You can also import your course history using the import button.")
        
        if "thank" in lower:
            return "You're welcome! Let me know if you need help with anything else."
        
        return ("I'm here to help with course scheduling! "
               "Tell me which courses you need or what major you're in.")

    def explain_failure(self, failed_codes: List[str], constraints: List[str]) -> str:
        """Explain why scheduling failed."""
        if not self.is_available():
            return (f"I couldn't find a valid schedule for {', '.join(failed_codes)}. "
                   f"This usually means the sections conflict with each other or "
                   f"don't meet your constraints ({', '.join(constraints) if constraints else 'none'}). "
                   f"Try removing a course or relaxing your constraints.")
        
        prompt = f"""The scheduling failed for courses: {failed_codes}
Constraints: {constraints if constraints else 'None'}

Write a brief, helpful message (under 50 words) explaining:
1. These courses likely have time conflicts
2. Suggest trying with fewer courses or different constraints"""
        
        response = self._generate(prompt)
        return response if response else (
            f"I couldn't find a valid schedule for {', '.join(failed_codes)}. "
            "Try removing a course or relaxing your day/time constraints."
        )

    def summarize_success(self, found_codes: List[str], constraints: List[str], 
                         count: int) -> str:
        """Generate success message."""
        if not self.is_available():
            constraint_str = f" with your constraints ({', '.join(constraints)})" if constraints else ""
            return f"Great news! I found {count} schedule option{'s' if count > 1 else ''} for {', '.join(found_codes)}{constraint_str}."
        
        prompt = f"""Successfully generated {count} schedules for: {found_codes}
Constraints applied: {constraints if constraints else 'None'}

Write a brief, cheerful confirmation (under 30 words)."""
        
        response = self._generate(prompt)
        return response if response else (
            f"Found {count} schedule option{'s' if count > 1 else ''} for your courses!"
        )


class CourseRecommender:
    """Recommends courses based on major requirements and history."""
    
    def __init__(self, catalog: Dict, repo):
        self.catalog = catalog
        self.repo = repo
    
    def get_recommendations(self, major: str, history: List[Dict], 
                           max_courses: int = 5) -> List[str]:
        """Get course recommendations for a major."""
        taken_codes = set()
        for h in history:
            taken_codes.add(h.get('short_code', ''))
            taken_codes.add(h.get('code', ''))
        
        # Find major requirements
        major_data = self.catalog.get('majors', {}).get(major, {})
        requirements = major_data.get('requirements', [])
        
        recommendations = []
        for req in requirements:
            if req not in taken_codes and len(recommendations) < max_courses:
                # Verify course exists this semester
                courses = self.repo.get_courses([req])
                if courses:
                    recommendations.append(req)
        
        return recommendations


# Initialize AI agent
ai_agent = GeminiAgent(Config.GEMINI_API_KEYS)


# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    repo = DataServiceFactory.get_repository()
    has_data = hasattr(repo, 'data_cache') and len(repo.data_cache) > 0
    
    return jsonify({
        'status': 'healthy',
        'version': VERSION,
        'ai_available': ai_agent.is_available(),
        'ai_model': ai_agent._working_model,
        'data_loaded': has_data,
        'catalog_loaded': bool(catalog_db.get('majors'))
    })


@app.route('/api/diagnostics', methods=['GET'])
def api_diagnostics():
    """
    Detailed API diagnostics endpoint.
    Visit http://localhost:5000/api/diagnostics in your browser to check status.
    """
    status = ai_agent.get_api_status()
    
    # Add helpful fix instructions if API is not enabled
    if status.get('api_enabled') == False or status.get('error'):
        status['fix_instructions'] = {
            'option_1': 'Enable API at: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com',
            'option_2': 'Create new key at: https://aistudio.google.com/apikey (choose "Create API key in new project")',
            'docs': 'See README.md for detailed instructions'
        }
    
    return jsonify(status)


@app.route('/api/parse_history', methods=['POST'])
def parse_history():
    """Parse and store course history from Degree Navigator."""
    try:
        data = request.get_json()
        raw_text = data.get('text', '')
        taken_courses = PrerequisiteParser.parse_copy_paste(raw_text)
        
        # Enrich with course titles
        repo = DataServiceFactory.get_repository()
        lookup_map = {}
        if hasattr(repo, 'data_cache'):
            for c in repo.data_cache:
                s = str(c.get('subject', ''))
                n = str(c.get('courseNumber', ''))
                lookup_map[f"{s}:{n}"] = c.get('title', '')
        
        for c in taken_courses:
            c['title'] = lookup_map.get(c['short_code'], 'Unknown Title')
        
        session['course_history'] = taken_courses
        
        return jsonify({
            'message': f"Imported {len(taken_courses)} courses.",
            'courses': taken_courses
        })
        
    except Exception as e:
        logger.error(f"Parse Error: {e}")
        return jsonify({'message': 'Failed to parse text.'}), 500


@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    """Clear stored course history."""
    session.pop('course_history', None)
    return jsonify({'message': 'History cleared.'})


@app.route('/api/chat', methods=['POST'])
def chat_endpoint():
    """Main chat endpoint for scheduling requests."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        text_input = str(data.get('message') or data.get('text') or "").strip()
        
        if not text_input:
            return jsonify({'message': "Please type something!"})

        logger.info(f"User Query: {text_input}")
        
        # Get history context
        history = session.get('course_history', [])
        history_codes = [h['short_code'] for h in history] if history else []
        history_str = ", ".join(history_codes)

        # Build major context
        full_major_context = ""
        lower_input = text_input.lower()
        for category in ["majors", "minors", "certificates"]:
            cat_data = catalog_db.get(category, {})
            for name, details in cat_data.items():
                if name.lower() in lower_input:
                    full_major_context += f"{category[:-1].capitalize()} in {name}: {json.dumps(details)}. "

        # Analyze intent
        ai_result = ai_agent.analyze_intent(
            text_input, 
            history_context=history_str, 
            major_context=full_major_context
        )
        logger.info(f"Intent Analysis: {ai_result}")
        
        # Handle conversational queries
        if ai_result.get("is_conversational") and not ai_result.get("codes") and not ai_result.get("subjects"):
            reply = ai_agent.chat_fallback(text_input)
            return jsonify({'message': reply, 'schedules': []})

        final_codes = ai_result.get("codes", [])
        subjects = ai_result.get("subjects", [])
        raw_constraints = ai_result.get("constraints", [])
        
        # Filter out already-taken courses
        final_codes = PrerequisiteParser.filter_completed_courses(final_codes, history)
        
        # Parse day constraints
        local_no_days = []
        for c in raw_constraints:
            c_lower = c.lower() if isinstance(c, str) else ""
            if "fri" in c_lower: local_no_days.append("F")
            if "mon" in c_lower: local_no_days.append("M")
            if "tue" in c_lower: local_no_days.append("T")
            if "wed" in c_lower: local_no_days.append("W")
            if "thu" in c_lower: local_no_days.append("TH")
        
        local_no_days = list(set(local_no_days))
        
        # Get course repository
        repo = DataServiceFactory.get_repository()
        
        # Handle subject-based searches
        needs_subject_search = (
            ai_result.get("needs_recommendations") or
            (subjects and not final_codes)
        )
        
        if needs_subject_search and subjects:
            for subj in subjects:
                found = repo.search_courses(subj)
                valid = [c for c in found if c.code not in history_codes]
                valid.sort(key=lambda x: x.code.split(':')[1] if ':' in x.code else x.code)
                
                for c in valid[:5]:
                    if c.code not in final_codes:
                        final_codes.append(c.code)
        
        # Handle recommendation requests
        if ai_result.get("needs_recommendations") and not final_codes:
            detected_major = None
            
            for name in catalog_db.get('majors', {}).keys():
                if name.lower() in lower_input:
                    detected_major = name
                    break
            
            if detected_major:
                recommender = CourseRecommender(catalog_db, repo)
                final_codes = recommender.get_recommendations(detected_major, history, 5)
        
        final_codes = list(set(final_codes))
        
        if not final_codes:
            msg = "I couldn't identify which courses you need. "
            if ai_result.get("explanation"):
                msg += ai_result["explanation"]
            else:
                msg += "Try specifying course codes (like 198:111) or mention a subject area."
            return jsonify({'message': msg, 'schedules': []})
        
        # Get course objects
        courses_obj = repo.get_courses(final_codes)
        found_real_codes = [c.code for c in courses_obj]
        
        missing_codes = set(final_codes) - set(found_real_codes)
        if missing_codes:
            logger.warning(f"Could not find courses: {missing_codes}")
        
        if not courses_obj:
            return jsonify({
                'message': f"Could not find any of the requested courses: {', '.join(final_codes)}",
                'schedules': []
            })
        
        # Generate schedules
        scheduler = DeepSeekSchedulerStrategy()
        constraints = ScheduleConstraints(no_days=local_no_days)
        
        valid_schedules = scheduler.generate_schedules(courses_obj, constraints)
        results = []
        status_msg = ""
        relaxed = False
        
        if valid_schedules:
            results = _format_schedules(valid_schedules, courses_obj)
            status_msg = ai_agent.summarize_success(found_real_codes, raw_constraints, len(results))
        else:
            # Try without day constraints
            if local_no_days:
                logger.info("Pass 1 failed. Trying Pass 2 (relaxed constraints)...")
                relaxed_schedules = scheduler.generate_schedules(
                    courses_obj, 
                    ScheduleConstraints(no_days=[])
                )
                
                if relaxed_schedules:
                    results = _format_schedules(relaxed_schedules, courses_obj)
                    relaxed = True
                    status_msg = (
                        f"I couldn't find a schedule with your constraints "
                        f"({', '.join(raw_constraints)}), but I found {len(results)} "
                        f"option{'s' if len(results) > 1 else ''} without those restrictions."
                    )
                else:
                    status_msg = ai_agent.explain_failure(found_real_codes, raw_constraints)
            else:
                status_msg = ai_agent.explain_failure(found_real_codes, raw_constraints)
        
        if missing_codes:
            status_msg += f" Note: Could not find {', '.join(missing_codes)} in this semester's offerings."
        
        return jsonify({
            "message": status_msg,
            "schedules": results,
            "count": len(results),
            "relaxed_constraints": relaxed
        })

    except Exception as e:
        logger.error(f"Chat Error: {e}", exc_info=True)
        return jsonify({
            'message': 'Sorry, something went wrong. Please try again.',
            'error': str(e)
        }), 500


def _format_schedules(schedules: List, courses_obj: List[Course]) -> List[Dict]:
    """Format schedule data for frontend."""
    results = []
    
    for schedule in schedules:
        schedule_data = []
        for section in schedule:
            course_title = "Unknown Course"
            course_code_str = "000:000"
            
            for c in courses_obj:
                for s in c.sections:
                    if s.index == section.index:
                        course_title = c.title
                        course_code_str = c.code
                        break
            
            schedule_data.append({
                'course': course_code_str,
                'title': course_title,
                'index': section.index,
                'instructors': section.instructors,
                'times': [str(t) for t in section.time_slots]
            })
        
        results.append(schedule_data)
    
    return results


@app.route('/api/search', methods=['GET'])
def search_courses():
    """Search for courses by query."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': [], 'message': 'Please provide a search query.'})
    
    repo = DataServiceFactory.get_repository()
    results = repo.search_courses(query)
    
    return jsonify({
        'results': [
            {
                'code': c.code,
                'title': c.title,
                'sections_count': len(c.sections)
            }
            for c in results[:20]
        ],
        'count': len(results)
    })


@app.route('/api/majors', methods=['GET'])
def list_majors():
    """List available majors."""
    majors = list(catalog_db.get('majors', {}).keys())
    majors = [m for m in majors if len(m) < 50 and not m.startswith("*")]
    return jsonify({'majors': sorted(majors)})


if __name__ == '__main__':
    issues = validate_config()
    if issues:
        logger.warning(f"Configuration issues: {issues}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(
        host='0.0.0.0',
        port=port,
        debug=Config.DEBUG
    )
