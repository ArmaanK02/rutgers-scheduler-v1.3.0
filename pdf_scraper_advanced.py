"""
Advanced AI-Powered PDF Catalog Scraper for Rutgers Course Requirements
Uses Gemini AI to intelligently parse complex requirement structures including:
- Prerequisites
- Elective requirements (upper/lower level)
- Core vs elective courses
- Complex requirement patterns
"""

import json
import re
import os
import sys
import requests
import time
from typing import Dict, List, Optional, Any

# Gemini API Configuration
GEMINI_API_KEY = "AIzaSyBuiHjB2k4F3bUcgMqvo5f2yFnE6pBfYjg"
GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        from pypdf import PdfReader
        return True
    except ImportError:
        print("Error: pypdf not installed.")
        print("Install it with: pip install pypdf")
        return False

def call_gemini_api(prompt: str, system_instruction: str = None, max_retries: int = 3) -> Optional[str]:
    """Call Gemini API with the provided prompt."""
    for model in GEMINI_MODELS:
        for attempt in range(max_retries):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.3,  # Lower temperature for more structured output
                        "maxOutputTokens": 4096,
                        "topP": 0.95,
                        "topK": 40,
                    }
                }
                
                if system_instruction:
                    payload["systemInstruction"] = {
                        "parts": [{"text": system_instruction}]
                    }
                
                response = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'candidates' in data and data['candidates']:
                        text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                        return text.strip()
                elif response.status_code == 404:
                    break  # Try next model
                elif response.status_code == 429:
                    wait_time = (2 ** attempt) * 2
                    print(f"    Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"    API error {response.status_code}, trying next model...")
                    break
                    
            except Exception as e:
                print(f"    Error with {model}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                break
    
    return None

def extract_program_section_text(full_text: str, program_name: str) -> Optional[str]:
    """Extract the text section for a specific program."""
    # Try multiple patterns to find the program section
    patterns = [
        rf"{re.escape(program_name)}\s*(?:Major|Minor|Certificate)?\s*(?:Requirements|Curriculum|Program|Overview)",
        rf"{re.escape(program_name)}[^\n]*(?:Requirements|Curriculum|Program)",
        rf"Program:\s*{re.escape(program_name)}",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            start = match.start()
            # Extract a large chunk (up to 10000 chars) to get full requirements
            end = min(start + 10000, len(full_text))
            section_text = full_text[start:end]
            
            # Try to find where the next program starts
            next_program = re.search(r'\n\s*[A-Z][A-Za-z\s&,]+(?:Major|Minor|Certificate|Program)', section_text[5000:])
            if next_program:
                section_text = section_text[:5000 + next_program.start()]
            
            return section_text
    
    return None

def parse_requirements_with_ai(section_text: str, program_name: str, program_type: str) -> Dict[str, Any]:
    """Use AI to parse complex requirement structures from text."""
    
    system_instruction = """You are an expert at parsing university course catalog requirements. 
Extract structured information about course requirements including:
- Core/required courses
- Elective courses (with upper/lower level distinctions)
- Prerequisites
- Course groupings
- Complex patterns like "choose X from Y" or "7 electives (4 upper level, 3 lower level)"

Always respond with valid JSON only."""

    prompt = f"""Parse the course requirements for the {program_type} "{program_name}" from the following text.

TEXT:
{section_text[:8000]}

Extract all requirements and structure them as JSON with this format:
{{
    "core_requirements": [
        {{"code": "220:102", "name": "Introduction to Microeconomics", "credits": 3, "prerequisites": []}},
        {{"code": "220:103", "name": "Introduction to Macroeconomics", "credits": 3, "prerequisites": ["220:102"]}}
    ],
    "electives": {{
        "lower_level": {{
            "required_count": 3,
            "courses": [
                {{"code": "220:201", "name": "Course Name", "credits": 3, "prerequisites": []}}
            ]
        }},
        "upper_level": {{
            "required_count": 4,
            "courses": [
                {{"code": "220:320", "name": "Course Name", "credits": 3, "prerequisites": ["220:102", "220:103"]}}
            ]
        }},
        "general": {{
            "required_count": 0,
            "courses": []
        }}
    }},
    "total_credits": 45,
    "notes": "Any additional requirements or notes"
}}

IMPORTANT:
- Extract ALL course codes mentioned (format: XXX:YYY or XX:XXX:YYY)
- Identify prerequisites by looking for phrases like "Prerequisite:", "Prerequisites:", "Prereq:", or course codes mentioned before "or" in requirement descriptions
- Distinguish between required/core courses and electives
- For electives, identify if they specify upper level (300-400 level) or lower level (100-200 level)
- Extract course names when available
- If a requirement says "choose 7 electives (4 upper level, 3 lower level)", structure it accordingly
- If prerequisites are not explicitly stated, leave prerequisites as empty array
- Return ONLY valid JSON, no additional text"""

    ai_response = call_gemini_api(prompt, system_instruction)
    
    if ai_response:
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return parsed
        except json.JSONDecodeError as e:
            print(f"    ⚠️  Failed to parse AI response for {program_name}: {e}")
            # Fallback: extract course codes manually
            return extract_course_codes_fallback(section_text)
    
    # Fallback to simple extraction
    return extract_course_codes_fallback(section_text)

def extract_course_codes_fallback(text: str) -> Dict[str, Any]:
    """Fallback method to extract course codes when AI fails."""
    # Find all course codes (XXX:YYY format)
    codes = re.findall(r'\b(\d{2,3}:\d{3})\b', text)
    unique_codes = list(set(codes))
    
    return {
        "core_requirements": [
            {"code": code, "name": "", "credits": 3, "prerequisites": []}
            for code in unique_codes[:20]
        ],
        "electives": {
            "lower_level": {"required_count": 0, "courses": []},
            "upper_level": {"required_count": 0, "courses": []},
            "general": {"required_count": 0, "courses": []}
        },
        "total_credits": None,
        "notes": ""
    }

def identify_program_names(full_text: str) -> Dict[str, List[str]]:
    """Identify all major, minor, and certificate program names from the PDF."""
    programs = {
        "majors": [],
        "minors": [],
        "certificates": []
    }
    
    # Look for common patterns in catalog structure
    # Majors section
    majors_section = re.search(r'(?:Major Programs|Majors|Undergraduate Majors)[\s\S]{0,50000}', full_text, re.IGNORECASE)
    if majors_section:
        majors_text = majors_section.group(0)
        # Extract program names (lines that look like program names)
        lines = majors_text.split('\n')
        for line in lines:
            line = line.strip()
            # Skip headers, page numbers, etc.
            if len(line) < 4 or len(line) > 100:
                continue
            if re.match(r'^\d+$', line) or 'Page' in line or 'Rutgers' in line:
                continue
            # Look for program-like names (capitalized, not all caps)
            if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+[&,][\s\S]*)?$', line):
                # Remove asterisks and clean
                clean_name = re.sub(r'\*+$', '', line).strip()
                if clean_name and clean_name not in programs["majors"]:
                    programs["majors"].append(clean_name)
    
    # Similar for minors and certificates
    # This is a simplified version - the full implementation would be more sophisticated
    
    return programs

def scrape_catalog_pdf_advanced(pdf_filename: str, use_ai: bool = True, limit: Optional[int] = None):
    """
    Advanced PDF scraper using AI to extract structured requirements.
    
    Args:
        pdf_filename: Name of the PDF file
        use_ai: Whether to use AI parsing (slower but more accurate)
        limit: Limit number of programs to process (for testing)
    """
    if not check_dependencies():
        sys.exit(1)
    
    from pypdf import PdfReader
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(script_dir, pdf_filename)
    output_path = os.path.join(script_dir, 'major_requirements.json')

    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF not found at: {pdf_path}")
        return False

    print(f"✅ Reading {pdf_filename} with advanced AI-powered parser...")
    
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        
        # Extract all text
        print(f"  Document has {len(reader.pages)} pages. Extracting text...")
        for i, page in enumerate(reader.pages):
            full_text += page.extract_text() + "\n"
            if i % 100 == 0 and i > 0:
                print(f"    Processed {i} pages...")
        
        print(f"  Extracted {len(full_text)} characters of text")
        
        # Load existing catalog or create new structure
        catalog_db = {
            "majors": {},
            "minors": {},
            "certificates": {}
        }
        
        # Try to load existing to preserve structure
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    # Get program names from existing structure
                    for cat in ["majors", "minors", "certificates"]:
                        if cat in existing:
                            for name in existing[cat].keys():
                                # Skip invalid entries
                                if len(name) < 4 or "PROGRAMS" in name.upper() or "RUTGERS" in name.upper():
                                    continue
                                if name not in catalog_db[cat]:
                                    catalog_db[cat][name] = {
                                        "school": existing[cat][name].get("school", "SAS"),
                                        "requirements": existing[cat][name].get("requirements", []),
                                        "structured_requirements": None
                                    }
            except:
                pass
        
        # If no existing structure, try to identify programs from PDF
        if not any(catalog_db.values()):
            print("  No existing catalog found. Identifying programs from PDF...")
            programs = identify_program_names(full_text)
            for cat in ["majors", "minors", "certificates"]:
                for name in programs[cat][:50]:  # Limit for testing
                    if name not in catalog_db[cat]:
                        catalog_db[cat][name] = {
                            "school": "SAS",
                            "requirements": [],
                            "structured_requirements": None
                        }
        
        # Process each program
        total_programs = sum(len(catalog_db[cat]) for cat in catalog_db.keys())
        processed = 0
        
        print(f"\n  Processing {total_programs} programs with {'AI' if use_ai else 'basic'} parsing...")
        
        for cat in ["majors", "minors", "certificates"]:
            programs = list(catalog_db[cat].items())
            if limit:
                programs = programs[:limit]
            
            for program_name, program_data in programs:
                processed += 1
                print(f"  [{processed}/{total_programs}] Processing {cat[:-1]}: {program_name}...")
                
                # Extract section text
                section_text = extract_program_section_text(full_text, program_name)
                
                if not section_text:
                    print(f"    ⚠️  Could not find section for {program_name}")
                    continue
                
                # Parse with AI if enabled
                if use_ai:
                    structured_reqs = parse_requirements_with_ai(section_text, program_name, cat[:-1])
                    
                    # Update program data
                    program_data["structured_requirements"] = structured_reqs
                    
                    # Also maintain flat list for backward compatibility
                    all_codes = []
                    if structured_reqs.get("core_requirements"):
                        all_codes.extend([c["code"] for c in structured_reqs["core_requirements"]])
                    if structured_reqs.get("electives"):
                        for level in ["lower_level", "upper_level", "general"]:
                            if structured_reqs["electives"].get(level, {}).get("courses"):
                                all_codes.extend([c["code"] for c in structured_reqs["electives"][level]["courses"]])
                    
                    program_data["requirements"] = list(set(all_codes))
                    
                    print(f"    ✅ Extracted {len(program_data['requirements'])} courses with structured requirements")
                    
                    # Rate limiting
                    time.sleep(1)
                else:
                    # Basic extraction
                    codes = re.findall(r'\b(\d{2,3}:\d{3})\b', section_text)
                    program_data["requirements"] = list(set(codes))[:25]
                    print(f"    ✅ Extracted {len(program_data['requirements'])} courses")
        
        # Save output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(catalog_db, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved enhanced catalog database to: {output_path}")
        print(f"   Processed {processed} programs")
        
        # Statistics
        with_structured = sum(
            1 for cat in catalog_db.values()
            for prog in cat.values()
            if prog.get("structured_requirements")
        )
        print(f"   {with_structured} programs have structured requirements")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_name = sys.argv[1]
        use_ai = "--no-ai" not in sys.argv
        limit = None
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            if idx + 1 < len(sys.argv):
                limit = int(sys.argv[idx + 1])
        
        scrape_catalog_pdf_advanced(pdf_name, use_ai=use_ai, limit=limit)
    else:
        print("Usage: python pdf_scraper_advanced.py <catalog.pdf> [--no-ai] [--limit N]")
        print("\nOptions:")
        print("  --no-ai    Use basic extraction instead of AI parsing")
        print("  --limit N  Process only first N programs (for testing)")

