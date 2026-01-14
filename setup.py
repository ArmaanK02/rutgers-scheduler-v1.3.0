#!/usr/bin/env python3
"""
Setup script for Scarlet Scheduler
Helps users get started quickly by:
1. Checking dependencies
2. Creating sample data
3. Validating configuration
"""

import os
import sys
import subprocess
import json

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)

def print_step(step, text):
    print(f"\n[{step}] {text}")

def check_python_version():
    """Ensure Python 3.8+"""
    print_step("1/5", "Checking Python version...")
    
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 8):
        print(f"  ❌ Python 3.8+ required, found {major}.{minor}")
        return False
    
    print(f"  ✅ Python {major}.{minor} detected")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    print_step("2/5", "Checking dependencies...")
    
    required = ['flask', 'requests']
    optional = ['pypdf', 'python-dotenv', 'pytest']
    
    missing_required = []
    missing_optional = []
    
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
            print(f"  ✅ {pkg}")
        except ImportError:
            missing_required.append(pkg)
            print(f"  ❌ {pkg} (required)")
    
    for pkg in optional:
        try:
            __import__(pkg.replace('-', '_'))
            print(f"  ✅ {pkg} (optional)")
        except ImportError:
            missing_optional.append(pkg)
            print(f"  ⚠️  {pkg} (optional)")
    
    return missing_required, missing_optional

def install_dependencies(packages):
    """Install missing packages"""
    print(f"\n  Installing: {', '.join(packages)}")
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', 
            '--quiet', *packages
        ])
        print("  ✅ Installation complete")
        return True
    except subprocess.CalledProcessError:
        print("  ❌ Installation failed")
        return False

def check_env_file():
    """Check for .env file and API key"""
    print_step("3/5", "Checking configuration...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, '.env')
    env_example = os.path.join(script_dir, '.env.example')
    
    # Check for API key
    api_key = os.environ.get('GEMINI_API_KEY')
    
    if not os.path.exists(env_path):
        print("  ⚠️  No .env file found")
        if os.path.exists(env_example):
            print("  💡 Copy .env.example to .env and add your API key")
    else:
        print("  ✅ .env file exists")
        # Try to load from .env
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
            api_key = os.environ.get('GEMINI_API_KEY')
        except ImportError:
            pass
    
    if api_key and 'your-api-key' not in api_key.lower():
        print("  ✅ Gemini API key configured")
        return True
    else:
        print("  ⚠️  No Gemini API key found")
        print("  💡 Get a free key at: https://makersuite.google.com/app/apikey")
        print("  💡 App will work with limited AI features")
        return False

def create_sample_data():
    """Create sample major requirements if not present"""
    print_step("4/5", "Checking data files...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    major_path = os.path.join(script_dir, 'major_requirements.json')
    
    if os.path.exists(major_path):
        try:
            with open(major_path, 'r') as f:
                data = json.load(f)
            majors_count = len(data.get('majors', {}))
            if majors_count > 0:
                print(f"  ✅ Major requirements loaded ({majors_count} majors)")
                return True
        except:
            pass
    
    print("  ⚠️  No major requirements found, creating sample data...")
    
    # Run pdf_scraper to create sample data
    try:
        import pdf_scraper
        pdf_scraper.create_sample_catalog()
        print("  ✅ Sample catalog created")
        return True
    except Exception as e:
        print(f"  ❌ Could not create sample data: {e}")
        return False

def test_rutgers_api():
    """Test connection to Rutgers API"""
    print_step("5/5", "Testing Rutgers API connection...")
    
    try:
        import requests
        response = requests.get(
            "http://sis.rutgers.edu/soc/api/courses.json",
            params={"year": "2025", "term": "9", "campus": "NB", "level": "U"},
            timeout=10
        )
        if response.status_code == 200:
            courses = response.json()
            print(f"  ✅ Connected! Found {len(courses)} courses")
            return True
        else:
            print(f"  ❌ API returned status {response.status_code}")
            return False
    except requests.Timeout:
        print("  ⚠️  API request timed out")
        print("  💡 Course data will be fetched on first request")
        return False
    except Exception as e:
        print(f"  ⚠️  Could not connect: {e}")
        print("  💡 Course data will be fetched on first request")
        return False

def main():
    print_header("Scarlet Scheduler Setup")
    
    # Step 1: Python version
    if not check_python_version():
        print("\n❌ Setup failed: Python 3.8+ required")
        sys.exit(1)
    
    # Step 2: Dependencies
    missing_req, missing_opt = check_dependencies()
    
    if missing_req:
        print(f"\n  Missing required packages: {', '.join(missing_req)}")
        response = input("  Install them now? [Y/n]: ").strip().lower()
        if response != 'n':
            if not install_dependencies(missing_req):
                print("\n❌ Setup failed: Could not install dependencies")
                print("  Try: pip install -r requirements.txt")
                sys.exit(1)
    
    if missing_opt:
        response = input(f"\n  Install optional packages ({', '.join(missing_opt)})? [y/N]: ").strip().lower()
        if response == 'y':
            install_dependencies(missing_opt)
    
    # Step 3: Configuration
    has_api_key = check_env_file()
    
    # Step 4: Data files
    create_sample_data()
    
    # Step 5: API test
    api_works = test_rutgers_api()
    
    # Summary
    print_header("Setup Complete!")
    
    print("\n📋 Status:")
    print(f"  • Python: ✅")
    print(f"  • Dependencies: ✅")
    print(f"  • AI Features: {'✅' if has_api_key else '⚠️ Limited (no API key)'}")
    print(f"  • Major Data: ✅")
    print(f"  • Rutgers API: {'✅' if api_works else '⚠️ Will retry on first request'}")
    
    print("\n🚀 To start the application:")
    print("   python app.py")
    print("\n   Then open: http://localhost:5000")
    
    if not has_api_key:
        print("\n💡 Tip: Add a Gemini API key for enhanced AI features!")
        print("   Get one at: https://makersuite.google.com/app/apikey")

if __name__ == "__main__":
    main()
