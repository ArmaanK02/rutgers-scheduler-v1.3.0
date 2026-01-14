"""
PDF Catalog Scraper for Rutgers Course Requirements
Extracts major, minor, and certificate information from the Rutgers catalog PDF.
"""

import json
import re
import os
import sys

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        from pypdf import PdfReader
        return True
    except ImportError:
        print("Error: pypdf not installed.")
        print("Install it with: pip install pypdf")
        return False

def scrape_catalog_pdf(pdf_filename):
    """
    Scrape the Rutgers catalog PDF to extract major/minor/certificate requirements.
    
    Args:
        pdf_filename: Name of the PDF file (should be in the same directory)
    """
    if not check_dependencies():
        sys.exit(1)
    
    from pypdf import PdfReader
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_path = os.path.join(script_dir, pdf_filename)
    output_path = os.path.join(script_dir, 'major_requirements.json')

    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF not found at: {pdf_path}")
        print(f"   Please download the Rutgers catalog PDF and place it in: {script_dir}")
        return False

    print(f"✅ Reading {pdf_filename}...")
    
    try:
        reader = PdfReader(pdf_path)
        full_text = ""
        
        # --- PHASE 1: FULL TEXT EXTRACTION ---
        print(f"  Document has {len(reader.pages)} pages. Scanning all...")
        for i, page in enumerate(reader.pages):
            full_text += page.extract_text() + "\n"
            if i % 200 == 0 and i > 0:
                print(f"    Processed {i} pages...")

        catalog_db = {
            "majors": {},
            "minors": {},
            "certificates": {}
        }

        # --- PHASE 2: SUMMARY LIST PARSING ---
        # Based on typical catalog structure:
        # Majors: Pages 14-16 (Index 13-15)
        # Minors: Pages 17-19 (Index 16-18)
        # Certs:  Pages 20-23 (Index 19-22)
        
        print("  Parsing Summary Lists from specific page ranges...")

        def parse_pages(start_page, end_page, category_key):
            """Parse a range of pages for program names."""
            start_idx = start_page - 1
            end_idx = end_page
            
            chunk_text = ""
            for i in range(start_idx, min(end_idx, len(reader.pages))):
                chunk_text += reader.pages[i].extract_text() + "\n"
            
            lines = chunk_text.split('\n')
            count = 0
            
            # School indicator mapping
            school_map = {
                "": "SAS", 
                "*": "SEBS", 
                "**": "MGSA", 
                "***": "SMLR", 
                "****": "EJB", 
                "*****": "GSE", 
                "******": "SCI", 
                "*******": "RBS", 
                "********": "SAS/SCI"
            }

            for line in lines:
                line = line.strip()
                clean_line = line.replace('•', '').strip()
                
                # Skip invalid lines
                if len(clean_line) < 4:
                    continue
                if "Rutgers University" in clean_line:
                    continue
                if "Programs of Study" in clean_line:
                    continue
                if re.match(r'^\d+\s*/\s*\d+$', clean_line):
                    continue
                
                # Parse Name and School (asterisks indicate school)
                match = re.search(r'([^*]+)(\*+)$', clean_line)
                if match:
                    name = match.group(1).strip()
                    stars = match.group(2)
                    school = school_map.get(stars, "Unknown")
                else:
                    name = clean_line
                    school = "SAS"  # Default
                
                # Store
                if name and name not in catalog_db[category_key]:
                    catalog_db[category_key][name] = {
                        "school": school, 
                        "requirements": []
                    }
                    count += 1
            
            print(f"    Pages {start_page}-{end_page}: Found {count} {category_key}.")

        # Run Parsers (adjust page numbers based on actual PDF structure)
        parse_pages(14, 17, "majors")
        parse_pages(17, 20, "minors")
        parse_pages(20, 24, "certificates")

        total_majors = len(catalog_db['majors'])
        total_minors = len(catalog_db['minors'])
        total_certs = len(catalog_db['certificates'])
        
        print(f"  Total Discovered: {total_majors} Majors, {total_minors} Minors, {total_certs} Certificates.")

        # --- PHASE 3: REQUIREMENTS EXTRACTION ---
        print("  Extracting requirements (course codes)...")
        
        def extract_reqs(name):
            """Find requirements for a program by searching the full text."""
            # Skip the table of contents area
            body_text = full_text[100000:] if len(full_text) > 100000 else full_text
            
            # Look for program header followed by requirements
            header_regex = re.compile(
                rf"{re.escape(name)}.*?(?:Requirements|Curriculum|Courses)", 
                re.IGNORECASE
            )
            match = header_regex.search(body_text)
            
            if match:
                start = match.end()
                chunk = body_text[start:start+4000]
                # Find course codes (XXX:XXX format)
                codes = re.findall(r'\b(\d{3}:\d{3})\b', chunk)
                return list(set(codes))[:25]
            return []

        # Update database with requirements
        for cat in ["majors", "minors", "certificates"]:
            for name in catalog_db[cat]:
                reqs = extract_reqs(name)
                if reqs:
                    catalog_db[cat][name]["requirements"] = reqs

        # Count programs with requirements
        with_reqs = sum(
            1 for cat in catalog_db.values() 
            for prog in cat.values() 
            if prog.get('requirements')
        )
        print(f"  Found requirements for {with_reqs} programs.")

        # Save output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(catalog_db, f, indent=2)
        print(f"✅ Saved catalog database to: {output_path}")
        return True

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_sample_catalog():
    """
    Create a sample catalog with common majors for testing.
    Use this if you don't have the PDF.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, 'major_requirements.json')
    
    sample_data = {
        "majors": {
            "Computer Science": {
                "school": "SAS",
                "requirements": [
                    "198:111", "198:112", "198:205", "198:206", 
                    "198:211", "198:344", "640:151", "640:152", 
                    "640:250", "640:477"
                ]
            },
            "Data Science": {
                "school": "SAS",
                "requirements": [
                    "198:142", "198:210", "960:291", "960:295",
                    "198:336", "960:465", "640:151", "640:152"
                ]
            },
            "Economics": {
                "school": "SAS",
                "requirements": [
                    "220:102", "220:103", "220:320", "220:321", 
                    "220:322", "220:301", "220:308", "640:135"
                ]
            },
            "Mathematics": {
                "school": "SAS",
                "requirements": [
                    "640:151", "640:152", "640:251", "640:250",
                    "640:311", "640:350", "640:477", "640:421"
                ]
            },
            "Business Analytics and Information Technology": {
                "school": "RBS",
                "requirements": [
                    "010:272", "010:275", "220:102", "220:103",
                    "640:135", "960:285"
                ]
            },
            "Biological Sciences": {
                "school": "SAS",
                "requirements": [
                    "119:115", "119:116", "160:161", "160:162",
                    "119:117", "160:171"
                ]
            },
            "Psychology": {
                "school": "SAS",
                "requirements": [
                    "830:101", "830:200", "830:271", "830:301",
                    "960:211"
                ]
            },
            "Mechanical Engineering": {
                "school": "SOE",
                "requirements": [
                    "650:291", "650:311", "650:361", "650:381",
                    "640:151", "640:152", "640:251", "750:203"
                ]
            },
            "Electrical and Computer Engineering": {
                "school": "SOE",
                "requirements": [
                    "332:221", "332:222", "332:223", "332:224",
                    "332:331", "640:151", "640:152", "640:251"
                ]
            },
            "Communication": {
                "school": "SCI",
                "requirements": [
                    "447:201", "447:302", "447:315", "447:380",
                    "447:384"
                ]
            }
        },
        "minors": {
            "Computer Science": {
                "school": "SAS",
                "requirements": ["198:111", "198:112", "198:205", "198:206"]
            },
            "Mathematics": {
                "school": "SAS",
                "requirements": ["640:151", "640:152", "640:250", "640:251"]
            },
            "Economics": {
                "school": "SAS",
                "requirements": ["220:102", "220:103", "220:320"]
            },
            "Business Administration": {
                "school": "RBS",
                "requirements": ["010:272", "010:275", "220:102"]
            },
            "Psychology": {
                "school": "SAS",
                "requirements": ["830:101", "830:200", "830:271"]
            }
        },
        "certificates": {
            "Data Science": {
                "school": "SAS",
                "requirements": ["198:142", "960:291", "198:210"]
            },
            "Computational Economics": {
                "school": "SAS",
                "requirements": ["220:102", "220:103", "198:111"]
            }
        }
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sample_data, f, indent=2)
    
    print(f"✅ Created sample catalog at: {output_path}")
    print(f"   Contains {len(sample_data['majors'])} majors, "
          f"{len(sample_data['minors'])} minors, "
          f"{len(sample_data['certificates'])} certificates")
    return True


def find_catalog_pdf():
    """Auto-detect Rutgers catalog PDF in current directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Look for PDF files that might be the catalog
    pdf_patterns = [
        "rutgers-catalog*.pdf",
        "rutgers_catalog*.pdf",
        "catalog*.pdf",
        "*catalog*.pdf",
    ]
    
    import glob
    for pattern in pdf_patterns:
        matches = glob.glob(os.path.join(script_dir, pattern))
        if matches:
            # Return the first match
            return os.path.basename(matches[0])
    
    # If no pattern matched, look for any PDF file
    all_pdfs = glob.glob(os.path.join(script_dir, "*.pdf"))
    if len(all_pdfs) == 1:
        return os.path.basename(all_pdfs[0])
    elif len(all_pdfs) > 1:
        print("Multiple PDF files found:")
        for i, pdf in enumerate(all_pdfs):
            print(f"  {i+1}. {os.path.basename(pdf)}")
        print("\nPlease specify which one to use:")
        print("  python pdf_scraper.py <filename.pdf>")
        return None
    
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_name = sys.argv[1]
        scrape_catalog_pdf(pdf_name)
    else:
        # Try to auto-detect PDF
        detected_pdf = find_catalog_pdf()
        if detected_pdf:
            print(f"📄 Auto-detected PDF: {detected_pdf}")
            scrape_catalog_pdf(detected_pdf)
        else:
            print("Usage: python pdf_scraper.py <catalog.pdf>")
            print("\nNo PDF found in current directory.")
            print("Either:")
            print("  1. Place the Rutgers catalog PDF in this folder and run again")
            print("  2. Run with a specific filename: python pdf_scraper.py catalog.pdf")
            print("\nCreating sample catalog instead...")
            create_sample_catalog()
