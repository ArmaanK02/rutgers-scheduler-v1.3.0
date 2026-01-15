"""
AI Model Diagnostic Tool
------------------------
This script tests your API key against all available Gemini models to find
a working configuration. It bypasses the main app logic to isolate API issues.
"""

import requests
import json
import os
import time

# --- CONFIGURATION ---
# Replace this with the key you want to test specifically
TEST_KEY = "AIzaSyBxHfhLl042m9jcG1wkblule0kUNDoLXuY"

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

def log(status, msg):
    icon = "✅" if status == "OK" else "❌" if status == "FAIL" else "⚠️"
    print(f"{icon} {msg}")

def test_key_validity():
    print("\n--- 1. Testing Key Validity & Listing Models ---")
    url = f"{BASE_URL}/models?key={TEST_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            log("OK", f"Key accepted. Found {len(models)} accessible models.")
            return [m['name'] for m in models if 'generateContent' in m.get('supportedGenerationMethods', [])]
        elif response.status_code == 403:
            log("FAIL", "403 Forbidden. API Service is likely DISABLED in Google Cloud Console.")
            print("   -> Go to console.cloud.google.com -> APIs -> Enable 'Generative Language API'")
        elif response.status_code == 400:
            log("FAIL", f"400 Bad Request. Key might be invalid format. Key: {TEST_KEY[:10]}...")
        else:
            log("FAIL", f"Error {response.status_code}: {response.text}")
    except Exception as e:
        log("FAIL", f"Connection error: {e}")
    return []

def test_generation(model_name):
    # Clean model name (remove 'models/' prefix if present for clean printing, but API usually needs it or handles it)
    # The list endpoint returns 'models/gemini-pro', generate endpoint expects 'models/gemini-pro' or just 'gemini-pro'
    # We will use the full name returned by the list endpoint.
    
    print(f"\n--- Testing Generation: {model_name} ---")
    url = f"{BASE_URL}/{model_name}:generateContent?key={TEST_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": "Reply with 'Working' only."}]}],
        "generationConfig": {"maxOutputTokens": 10}
    }
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            try:
                text = data['candidates'][0]['content']['parts'][0]['text']
                log("OK", f"Success! Output: {text.strip()}")
                return True
            except:
                log("WARN", f"200 OK but unexpected format: {data}")
                return True # Still counts as 'working' connectivity-wise
                
        elif response.status_code == 429:
            log("FAIL", "429 Rate Limit. (Quota Exceeded or Too Fast)")
        elif response.status_code == 404:
            log("FAIL", "404 Model Not Found (Check region availability)")
        elif response.status_code == 500:
            log("FAIL", "500 Server Error (Google side)")
        else:
            log("FAIL", f"Status {response.status_code}: {response.text[:100]}...")
            
    except Exception as e:
        log("FAIL", f"Exception: {e}")
    return False

def main():
    print(f"Diagnostic for API Key: {TEST_KEY[:8]}********")
    
    # 1. Get Models
    available_models = test_key_validity()
    
    if not available_models:
        print("\n❌ CRITICAL: Could not list models. Cannot proceed.")
        return

    # 2. Filter for Gemini models (ignore PaLM or others if present)
    gemini_models = [m for m in available_models if 'gemini' in m]
    
    print(f"\nFound {len(gemini_models)} Gemini models to test:")
    for m in gemini_models:
        print(f" - {m}")
        
    # 3. Test Each Model
    working_models = []
    for model in gemini_models:
        if test_generation(model):
            working_models.append(model)
        # Sleep slightly to avoid hitting rate limits between tests
        time.sleep(1) 

    # 4. Summary
    print("\n" + "="*40)
    print("DIAGNOSTIC SUMMARY")
    print("="*40)
    if working_models:
        print(f"✅ The following models are WORKING for this key:")
        for wm in working_models:
            print(f"   - {wm}")
        print("\nRECOMMENDATION: Update 'preferred_models' in app.py to use one of these.")
    else:
        print("❌ NO models generated content successfully.")
        print("   Check for 429 (Quota) or 403 (Billing/Region) errors above.")

if __name__ == "__main__":
    main()
