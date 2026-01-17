import json
import os
import requests
import time
from typing import List, Dict, Optional
from scheduler_core import Course, Section, TimeSlot
from config import get_config

Config = get_config()

class DataRepository:
    def __init__(self, data_file: str):
        self.data_file = data_file
        # Define cache path relative to data_file location
        self.cache_file = os.path.join(os.path.dirname(data_file), 'course_title_cache.json')
        self.data_cache = []
        self.title_lookup = {}  # Cache for code -> title
        
        # Load local data first
        self.load_data()
        self.load_title_cache()
        
    def load_data(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    self.data_cache = json.load(f)
                    # Populate title lookup from current semester data
                    for entry in self.data_cache:
                        code = f"{entry.get('subject')}:{entry.get('courseNumber')}"
                        school = entry.get('schoolCode', '01') 
                        full_code = f"{school}:{code}"
                        
                        raw_title = entry.get('title', '')
                        title = self._format_title(raw_title)
                        
                        self.title_lookup[code] = title
                        self.title_lookup[full_code] = title
            except Exception as e:
                print(f"Error loading data: {e}")
                self.data_cache = []
        else:
            print("Data file not found. Please scrape data first.")
            self.data_cache = []

    def load_title_cache(self):
        """Load persistent title cache if it exists."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cached_titles = json.load(f)
                    self.title_lookup.update(cached_titles)
                print(f"Loaded {len(cached_titles)} titles from persistent cache.")
            except Exception as e:
                print(f"Error loading cache file: {e}")

    def save_title_cache(self):
        """Save title lookup to persistent cache."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.title_lookup, f)
            print("Saved title cache to disk.")
        except Exception as e:
            print(f"Error saving cache file: {e}")

    def fetch_historical_titles(self):
        """
        Smart fetcher:
        1. Checks if we already have a robust cache (e.g. > 1000 titles).
        2. If cached, ONLY checks for NEW semesters (current + next year).
        3. If empty, performs full fetch (2023-present).
        """
        # Heuristic: If we have many titles, assume we have historical data
        has_history = len(self.title_lookup) > 2000 
        
        base_url = "https://sis.rutgers.edu/soc/api/courses.json"
        
        # Determine what to fetch
        if has_history:
            print("Cache populated. Checking for NEW data only...")
            # Check only current and next year
            current_year = 2026 # Simulating current time context
            years = [current_year, current_year + 1]
        else:
            print("Cache cold. Building full historical database (2023-Present)...")
            years = [2023, 2024, 2025, 2026] 
            
        # Seasons: 1=Spring, 7=Summer, 9=Fall
        seasons = [1, 7, 9]
        
        updated = False
        
        for year in years:
            for term in seasons:
                # Skip clearly future terms
                if year > 2026 and term > 1: continue 
                
                # If we have history, maybe skip older checks? 
                # For now, just fetch the targeted years.
                
                print(f"Checking {term}/{year}...")
                params = {
                    'year': year,
                    'term': term,
                    'campus': 'NB'
                }
                
                try:
                    # Short timeout to quickly skip if semester data isn't published
                    resp = requests.get(base_url, params=params, timeout=3)
                    
                    if resp.status_code == 200:
                        courses = resp.json()
                        if not courses: 
                            continue # Empty list means data not ready
                            
                        print(f"  -> Found {len(courses)} courses. Processing...")
                        count_new = 0
                        
                        for c in courses:
                            school = c.get('schoolCode', '01')
                            subject = c.get('subject')
                            number = c.get('courseNumber')
                            raw_title = c.get('title')
                            
                            if school and subject and number and raw_title:
                                full_code = f"{school}:{subject}:{number}"
                                short_code = f"{subject}:{number}"
                                title = self._format_title(raw_title)
                                
                                # Update if new
                                if full_code not in self.title_lookup:
                                    self.title_lookup[full_code] = title
                                    self.title_lookup[short_code] = title
                                    count_new += 1
                                    updated = True
                        
                        if count_new > 0:
                            print(f"  -> Added {count_new} new titles.")
                    
                    # Be nice to the API
                    time.sleep(0.2)
                    
                except Exception as e:
                    # Likely timeout or connection error -> skip semester
                    # print(f"Skipping {term}/{year}: {e}") 
                    pass
        
        if updated:
            self.save_title_cache()
            print(f"Update complete. Total titles: {len(self.title_lookup)}")
        else:
            print("No new data found.")

    def _format_title(self, title: str) -> str:
        """Helper to title case the course name."""
        if not title: return ""
        words = title.lower().split()
        return " ".join(w.capitalize() for w in words)

    def get_course_title(self, code: str) -> str:
        """
        Returns the title for a course code from the cache.
        Tries exact match first, then loose match (subject:number).
        """
        if code in self.title_lookup:
            return self.title_lookup[code]
            
        parts = code.split(':')
        if len(parts) >= 2:
            short_code = f"{parts[-2]}:{parts[-1]}"
            if short_code in self.title_lookup:
                return self.title_lookup[short_code]
                
        return "Unknown Title"

    def get_courses(self, codes: List[str]) -> List[Course]:
        found_courses = []
        for code in codes:
            parts = code.split(':')
            if len(parts) >= 2:
                subj = parts[-2]
                num = parts[-1]
                
                for entry in self.data_cache:
                    if str(entry['subject']) == subj and str(entry['courseNumber']) == num:
                        found_courses.append(self._map_to_domain(entry))
                        break
        return found_courses

    def search_courses(self, query: str) -> List[Course]:
        query = query.lower()
        results = []
        for entry in self.data_cache:
            title = entry.get('title', '').lower()
            code = f"{entry.get('subject')}:{entry.get('courseNumber')}"
            
            if query in title or query in code:
                results.append(self._map_to_domain(entry))
                
        return results

    def _map_to_domain(self, entry: Dict) -> Course:
        sections = []
        for sect in entry.get('sections', []):
            section_data = {
                'number': sect.get('number', sect.get('sectionNumber', 'UNKNOWN')),
                'index': sect.get('index', '00000'),
                'instructors': sect.get('instructors', []),
                'meetingTimes': sect.get('meetingTimes', []),
                'openStatus': sect.get('openStatus', True)
            }
            sections.append(Section(section_data))
            
        return Course(
            title=entry.get('title', 'Unknown Title'),
            code=f"{entry.get('subject', '')}:{entry.get('courseNumber', '')}",
            sections=sections,
            prereqs=set(),  
            credits=float(entry.get('credits', entry.get('creditHours', 3.0)))
        )

    def _time_to_minutes(self, hhmm: str) -> int:
        try:
            hhmm = str(hhmm).replace(':', '')
            if len(hhmm) == 3: hhmm = '0' + hhmm
            hours = int(hhmm[:2])
            mins = int(hhmm[2:])
            return hours * 60 + mins
        except:
            return 0

class DataServiceFactory:
    _repo = None
    
    @staticmethod
    def get_repository():
        if DataServiceFactory._repo is None:
            DataServiceFactory._repo = DataRepository(Config.DATA_FILE_PATH)
        return DataServiceFactory._repo