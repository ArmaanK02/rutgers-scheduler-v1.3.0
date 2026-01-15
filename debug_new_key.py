"""
Debug Script for specific API Key
"""

import requests
import json
import time

# PASTE YOUR FRESH KEY HERE
TEST_KEY = "AIzaSyCdyXmDsYG4_2tTWlCFCCUJxFN1xuGV-04" 

def run_debug():
    print(f"\n🧪 Testing key: {TEST_KEY[:10]}...{TEST_KEY[-4:]}\n")
    
    # 1. Test Listing Models (Base Connectivity)
    print("--- Step 1: Listing Models ---")
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={TEST_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            models = [m['name'].split('/')[-1] for m in data.get('models', [])]
            print(f"✅ Success! Found {len(models)} models available to this key.")
            # print(f"Sample models: {models[:5]}")
        else:
            print(f"❌ List Models Failed: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ Exception: {e}")
        return

    # 2. Test Generation (Deep Inspection)
    print("\n--- Step 2: Testing Models & Quotas ---")
    
    # Expanded list of models to try
    models_to_test = [
        "gemini-1.5-flash",
        "gemini-1.5-flash-001",
        "gemini-1.5-flash-8b", # Often has different quota
        "gemini-2.0-flash-exp", # Experimental
        "gemini-pro",
        "gemini-1.0-pro"
    ]
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": "Hi"}]}]
    }
    
    success = False
    
    for model in models_to_test:
        print(f"\n👉 Testing: {model}")
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={TEST_KEY}"
        
        # FORCE DELAY to avoid speed-based 429s
        time.sleep(2)
        
        try:
            resp = requests.post(gen_url, headers=headers, json=payload, timeout=10)
            
            if resp.status_code == 200:
                print(f"   ✅ SUCCESS! This model works.")
                print(f"   Response: {resp.json()['candidates'][0]['content']['parts'][0]['text']}")
                success = True
                break # We found a working model!
                
            elif resp.status_code == 429:
                print("   ❌ 429 RATE LIMIT (Quota Exceeded)")
                try:
                    error_details = resp.json().get('error', {})
                    msg = error_details.get('message', '')
                    if "limit: 0" in msg:
                        print("      -> Limit is 0. This account/IP is blocked from this model.")
                    else:
                        print(f"      -> {msg[:100]}...")
                except:
                    pass
                    
            elif resp.status_code == 404:
                print("   ❌ 404 (Model not found)")
                
            else:
                print(f"   ❌ Error {resp.status_code}: {resp.text[:100]}")
                
        except Exception as e:
            print(f"   ❌ Exception: {e}")

    print("\n" + "="*40)
    if success:
        print("🎉 FOUND A WORKING CONFIGURATION!")
        print("   Update your code to use the working model above.")
    else:
        print("💥 ALL TESTS FAILED.")
        print("   It appears your IP Address might be temporarily blocked")
        print("   or the new account also requires a waiting period.")
    print("="*40 + "\n")

if __name__ == "__main__":
    if TEST_KEY == "PASTE_YOUR_NEW_KEY_HERE":
        print("❌ Please edit debug_new_key.py and paste your new key into TEST_KEY first.")
    else:
        run_debug()