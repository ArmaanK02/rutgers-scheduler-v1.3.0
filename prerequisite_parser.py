from typing import List, Dict, Callable
import re
import logging

logger = logging.getLogger(__name__)

class PrerequisiteParser:
    """
    Parses degree navigator or transcript text to extract taken courses.
    v2.3.0 - Robust Multi-Pass Strategy
    """
    @staticmethod
    def parse_copy_paste(text: str, title_resolver: Callable[[str], str] = None) -> List[Dict]:
        """
        Parses raw text from Degree Navigator copy-paste.
        Strategy: Find Course Codes first, then look for context.
        """
        taken_courses = []
        
        if not text:
            return []

        # Normalize text to handle newlines as spaces for regex continuity if needed, 
        # but sometimes structure is preserved in lines. Let's try scanning line by line first, 
        # then fallback to blob.
        # Actually, DN copy-paste is often a mess of tabs/newlines.
        # Let's tokenize by "01:198:111" patterns.
        
        # Regex to find ANY Rutgers-like course code: 2 digits : 3 digits : 3 digits
        # Allows for alphanumeric (e.g. TR:T01:EC1)
        code_pattern = re.compile(r'(\w{2}):(\w{3}):(\w{3})')
        
        # Split text into chunks based on course codes to isolate "metadata" for each course
        # We find all matches iteratvely
        matches = list(code_pattern.finditer(text))
        
        for i, match in enumerate(matches):
            school, subject, number = match.groups()
            full_code = f"{school}:{subject}:{number}"
            short_code = f"{subject}:{number}"
            
            start_idx = match.start()
            end_idx = match.end()
            
            # Context Window: Look at text BEFORE and AFTER this match
            # The "Term" is usually BEFORE (e.g. "Fall 2024 01:..." or "2024 01:...")
            # The "Credits" and "Grade" are usually AFTER (e.g. "01:... 3.0 A")
            
            # Look behind (up to 50 chars) for Term
            prev_text_limit = max(0, start_idx - 50)
            prev_chunk = text[prev_text_limit:start_idx]
            
            # Look ahead (up to 50 chars) for Credits/Grade
            next_text_limit = min(len(text), end_idx + 50)
            next_chunk = text[end_idx:next_text_limit]
            
            # --- Extract Term ---
            # Look for "Fall 2024", "Spring 23", "2024"
            term = "Unknown"
            term_match = re.search(r'(?:Fall|Spring|Summer|Winter)?\s*20\d{2}', prev_chunk, re.IGNORECASE)
            if term_match:
                term = term_match.group(0).strip()
            # Special case for "PFall" typo or mashed text "Fall 202501" (where 01 is school code)
            # The chunk strategy handles "Fall 2025" nicely even if "01" follows immediately 
            # because we split at start_idx (which is start of 01).
            
            # --- Extract Credits ---
            # Look for 1-3 digits, maybe decimal: "3", "3.0", "4", "1.5"
            # Usually appears right after code.
            credits = 3.0
            credit_match = re.search(r'^\s*([0-9]+(?:\.[0-9]+)?)', next_chunk)
            if credit_match:
                try:
                    val = float(credit_match.group(1))
                    if 0 <= val <= 12: # Sanity check
                        credits = val
                except: pass
                
            # --- Extract Grade ---
            # Look for Grade codes. "A", "B+", "PA", "TR".
            # Often follows credits.
            grade = "Completed"
            # Regex for grade: A-F with +/- OR PA/NC/TR/TZ/TF/NG
            # We skip the credits part in next_chunk to find grade
            grade_search_start = credit_match.end() if credit_match else 0
            grade_chunk = next_chunk[grade_search_start:]
            
            grade_match = re.search(r'\s([A-C][+]?|[DF]|PA|NC|TR|TZ|TF|NG)\b', grade_chunk)
            if grade_match:
                grade = grade_match.group(1).strip()
            
            # --- Resolve Title ---
            title = "Unknown Title"
            if title_resolver:
                title = title_resolver(full_code)

            taken_courses.append({
                "code": full_code,
                "short_code": short_code,
                "credits": credits,
                "status": "Completed",
                "grade": grade,
                "term": term,
                "title": title
            })
            
        # Special Handling for Placements (Prefix "Placement")
        # These don't match standard code pattern usually
        placement_pattern = re.compile(r'Placement(\w{2}):(\w{3}):(\w{3})')
        for match in placement_pattern.finditer(text):
             taken_courses.append({
                "code": f"PL:{match.group(2)}:{match.group(3)}",
                "short_code": f"{match.group(2)}:{match.group(3)}",
                "credits": 0.0,
                "status": "Placement",
                "grade": "PL",
                "term": "Placement",
                "title": "Placement Test"
            })

        return taken_courses

    @staticmethod
    def filter_completed_courses(target_courses: List[str], history: List[Dict]) -> List[str]:
        completed_codes = set()
        for c in history:
            completed_codes.add(c.get('short_code'))
            completed_codes.add(c.get('code'))
            
        needed = []
        for target in target_courses:
            parts = target.split(':')
            if len(parts) == 3:
                short_target = f"{parts[1]}:{parts[2]}"
            else:
                short_target = target
            
            if short_target not in completed_codes:
                needed.append(target)
                
        return needed