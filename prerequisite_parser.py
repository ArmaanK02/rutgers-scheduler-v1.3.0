import re
from typing import List, Dict

class PrerequisiteParser:
    @staticmethod
    def parse_copy_paste(raw_text: str) -> List[Dict]:
        """
        Extracts course details from raw text.
        """
        parsed_courses = []
        clean_text = re.sub(r'\s+', ' ', raw_text)
        
        code_pattern = re.compile(r'(\d{2}):(\d{3}):(\d{3})')
        matches = list(code_pattern.finditer(clean_text))
        
        seen_codes = set()
        
        for match in matches:
            full_code = match.group(0)
            if full_code in seen_codes: continue
            seen_codes.add(full_code)
            
            start_idx = match.start()
            end_idx = match.end()
            
            # Look behind for Term
            lookbehind = clean_text[max(0, start_idx-30):start_idx]
            term = "Unknown"
            term_match = re.search(r'(Fall|Spring|Summer|Winter|Placement)(\s*\d{4})?', lookbehind, re.IGNORECASE)
            if term_match:
                term = term_match.group(0).strip()
            
            # Look ahead for Credits/Grade
            lookahead = clean_text[end_idx:end_idx+30]
            credits = "?"
            grade = "?"
            
            # Pattern: Digit + Text
            cg_match = re.match(r'\s*(\d\.?5?)\s*([A-Za-z\+\s,]+)', lookahead)
            if cg_match:
                credits = cg_match.group(1)
                grade_raw = cg_match.group(2).strip()
                # Simple cleanup
                grade_parts = grade_raw.split()
                if grade_parts:
                    grade = grade_parts[0].replace(',', '')
                    if len(grade) > 2 and grade not in ["PAS", "NGR"]:
                        grade = grade[:2] # A+ -> A+
            
            parsed_courses.append({
                "code": full_code,
                "short_code": f"{match.group(2)}:{match.group(3)}",
                "semester": term,
                "credits": credits,
                "grade": grade,
                "title": "", # Populated by app.py
                "core": []   # Populated by app.py
            })
            
        return parsed_courses

    @staticmethod
    def filter_completed_courses(recommended: List[str], history: List[Dict]) -> List[str]:
        taken = set()
        for h in history:
            taken.add(h['short_code'])
            taken.add(h['code'])
        return [c for c in recommended if c not in taken]
