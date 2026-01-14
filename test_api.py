#!/usr/bin/env python3
"""
Gemini API Test Script for Scarlet Scheduler v1.3.0

This script tests your Gemini API configuration and helps diagnose issues.
Run this BEFORE running the main app to verify your setup.

Usage:
    python test_api.py
"""

import os
import sys
import time
import json
import requests
from typing import Optional, List, Tuple

# Try to load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Note: python-dotenv not installed, using environment variables directly")

# ANSI colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}{Colors.RESET}")

def print_success(text: str):
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")

def print_error(text: str):
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.RESET}")


def get_api_keys() -> List[str]:
    """Get API keys from environment."""
    keys = []
    seen = set()
    
    # Check for single key
    key = os.environ.get("GEMINI_API_KEY")
    if key and key not in seen:
        keys.append(key)
        seen.add(key)
    
    # Check for numbered keys
    for i in range(1, 10):
        key = os.environ.get(f"GEMINI_API_KEY_{i}")
        if key and key not in seen:
            keys.append(key)
            seen.add(key)
    
    return keys


def test_model_availability(api_key: str) -> Tuple[bool, List[str]]:
    """Test if we can list models and which ones are available."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = [
                m['name'].replace('models/', '') 
                for m in data.get('models', []) 
                if 'generateContent' in m.get('supportedGenerationMethods', [])
            ]
            return True, models
        elif response.status_code == 403:
            return False, ["403 Forbidden - API not enabled"]
        elif response.status_code == 401:
            return False, ["401 Unauthorized - Invalid API key"]
        else:
            return False, [f"{response.status_code}: {response.text[:100]}"]
            
    except Exception as e:
        return False, [str(e)]


def test_generation(api_key: str, model: str) -> Tuple[bool, str, float]:
    """Test text generation with a specific model."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{
                "text": "Say 'Hello Rutgers!' in exactly 3 words."
            }]
        }],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 50,
        }
    }
    
    headers = {'Content-Type': 'application/json'}
    
    start_time = time.time()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and data['candidates']:
                text = data['candidates'][0].get('content', {}).get('parts', [{}])[0].get('text', '')
                return True, text.strip(), elapsed
            return False, "No response generated", elapsed
        elif response.status_code == 429:
            return False, "Rate Limited (429)", elapsed
        elif response.status_code == 403:
            return False, "Forbidden (403) - API not enabled", elapsed
        elif response.status_code == 404:
            return False, f"Model not found (404)", elapsed
        else:
            error = response.json().get('error', {}).get('message', response.text[:100])
            return False, f"{response.status_code}: {error}", elapsed
            
    except requests.Timeout:
        return False, "Timeout", time.time() - start_time
    except Exception as e:
        return False, str(e), time.time() - start_time


def run_diagnostics():
    """Run full API diagnostics."""
    print_header("Gemini API Diagnostic Test")
    
    # Step 1: Check for API keys
    print("\n📋 Step 1: Checking API Keys...")
    api_keys = get_api_keys()
    
    if not api_keys:
        print_error("No API keys found!")
        print_info("Set GEMINI_API_KEY in your .env file or environment")
        print_info("Get a free key at: https://makersuite.google.com/app/apikey")
        return False
    
    print_success(f"Found {len(api_keys)} API key(s)")
    
    # Step 2: Test each key
    working_keys = []
    all_models = set()
    
    for i, key in enumerate(api_keys):
        key_preview = f"{key[:10]}...{key[-4:]}"
        print(f"\n🔑 Step 2.{i+1}: Testing API Key #{i+1} ({key_preview})...")
        
        success, models = test_model_availability(key)
        
        if success:
            print_success(f"Key #{i+1} can list models ({len(models)} models available)")
            working_keys.append(key)
            all_models.update(models)
        else:
            print_error(f"Key #{i+1} failed: {models[0] if models else 'Unknown error'}")
            if "403" in str(models):
                print_info("Enable the API at: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
    
    if not working_keys:
        print_error("\nNo working API keys found!")
        return False
    
    # Step 3: Find best models
    print(f"\n🤖 Step 3: Identifying Available Models...")
    
    # Preferred models (fastest to slowest, free tier)
    preferred_models = [
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
    ]
    
    available_preferred = [m for m in preferred_models if m in all_models]
    
    print(f"   Total models available: {len(all_models)}")
    print(f"   Preferred models available: {len(available_preferred)}")
    
    if available_preferred:
        print_success(f"Best model for free tier: {available_preferred[0]}")
    else:
        # Look for any flash model
        flash_models = [m for m in all_models if 'flash' in m.lower()]
        if flash_models:
            print_warning(f"Using alternative model: {flash_models[0]}")
            available_preferred = flash_models[:3]
        else:
            print_error("No suitable models found!")
            return False
    
    # Step 4: Test actual generation
    print(f"\n⚡ Step 4: Testing Text Generation...")
    
    test_key = working_keys[0]
    successful_models = []
    
    for model in available_preferred[:3]:  # Test up to 3 models
        print(f"   Testing {model}...", end=" ", flush=True)
        success, result, elapsed = test_generation(test_key, model)
        
        if success:
            print(f"{Colors.GREEN}✓{Colors.RESET} ({elapsed:.2f}s)")
            successful_models.append((model, elapsed))
        else:
            print(f"{Colors.RED}✗{Colors.RESET} ({result})")
            if "429" in result:
                print_warning("   Rate limited - waiting 5 seconds...")
                time.sleep(5)
    
    if not successful_models:
        print_error("\nNo models passed generation test!")
        print("")
        print_header("🔧 HOW TO FIX: API Not Enabled (403 Error)")
        print("")
        print("   The 'Generative Language API' is NOT enabled in your Google Cloud project.")
        print("   Your API keys can list models but cannot generate content.")
        print("")
        print(f"   {Colors.YELLOW}OPTION 1 - Enable API (Recommended):{Colors.RESET}")
        print("   1. Go to: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
        print("   2. Select the project linked to your API key")
        print("   3. Click 'ENABLE'")
        print("   4. Wait 1-2 minutes for changes to propagate")
        print("   5. Run this test again")
        print("")
        print(f"   {Colors.YELLOW}OPTION 2 - Create New Key (Easiest):{Colors.RESET}")
        print("   1. Go to: https://aistudio.google.com/apikey")
        print("   2. Click 'Create API Key'")
        print("   3. Choose 'Create API key in new project' (this auto-enables the API!)")
        print("   4. Copy the new key to your .env file")
        print("   5. Run this test again")
        print("")
        return False
    
    # Summary
    print_header("Summary")
    
    print_success(f"Working API Keys: {len(working_keys)}")
    print_success(f"Working Models: {len(successful_models)}")
    
    best_model, best_time = min(successful_models, key=lambda x: x[1])
    print_success(f"Best Model: {best_model} ({best_time:.2f}s response time)")
    
    print(f"\n{Colors.GREEN}🎉 Your Gemini API is properly configured!{Colors.RESET}")
    print(f"\nRecommended configuration for your .env:")
    print(f"   GEMINI_API_KEY={working_keys[0][:20]}...")
    
    return True


def run_rate_limit_test():
    """Test rate limiting behavior."""
    print_header("Rate Limit Test")
    print_info("This test will make multiple rapid requests to understand rate limits")
    
    api_keys = get_api_keys()
    if not api_keys:
        print_error("No API keys found")
        return
    
    test_key = api_keys[0]
    
    # Find a working model
    success, models = test_model_availability(test_key)
    if not success:
        print_error("Could not list models")
        return
    
    test_model = None
    for m in ["gemini-2.0-flash-lite", "gemini-2.0-flash"]:
        if m in models:
            test_model = m
            break
    
    if not test_model:
        test_model = [m for m in models if 'flash' in m.lower()][0] if any('flash' in m.lower() for m in models) else models[0]
    
    print(f"Testing with model: {test_model}")
    print("Making 10 rapid requests...\n")
    
    results = {"success": 0, "rate_limited": 0, "errors": 0}
    
    for i in range(10):
        print(f"Request {i+1}/10: ", end="", flush=True)
        success, result, elapsed = test_generation(test_key, test_model)
        
        if success:
            print(f"{Colors.GREEN}✓{Colors.RESET} ({elapsed:.2f}s)")
            results["success"] += 1
        elif "429" in result or "Rate" in result:
            print(f"{Colors.YELLOW}Rate Limited{Colors.RESET}")
            results["rate_limited"] += 1
        else:
            print(f"{Colors.RED}Error: {result[:50]}{Colors.RESET}")
            results["errors"] += 1
        
        # Small delay between requests
        time.sleep(0.5)
    
    print(f"\nResults:")
    print(f"   Successful: {results['success']}")
    print(f"   Rate Limited: {results['rate_limited']}")
    print(f"   Errors: {results['errors']}")
    
    if results['rate_limited'] > 5:
        print_warning("High rate limiting detected - consider adding delays between requests")
    elif results['rate_limited'] > 0:
        print_info("Some rate limiting - the app handles this with exponential backoff")
    else:
        print_success("No rate limiting detected in this test")


if __name__ == "__main__":
    print(f"{Colors.BOLD}Scarlet Scheduler v1.3.0 - API Test Utility{Colors.RESET}")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--rate-test":
        run_rate_limit_test()
    else:
        success = run_diagnostics()
        
        if success:
            print(f"\n{Colors.BLUE}Optional: Run 'python test_api.py --rate-test' to test rate limits{Colors.RESET}")
        
        sys.exit(0 if success else 1)
