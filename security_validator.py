# security_validator.py
"""Security validation for LUCID backend"""
import os
import requests
import re

def get_config():
    return {
        'input_enabled': os.getenv('LUCID_SECURITY_INPUT', 'true').lower() == 'true',
        'output_enabled': os.getenv('LUCID_SECURITY_OUTPUT', 'true').lower() == 'true',
        'max_length': int(os.getenv('LUCID_MAX_MESSAGE_LENGTH', '2000')),
        'use_moderation': os.getenv('LUCID_USE_MODERATION', 'true').lower() == 'true',
        'key': os.getenv('OPENAI_API_KEY') or os.getenv('openai_api_key')
    }

def validate_input(message, messages_history=None):
    cfg = get_config()
    if not cfg['input_enabled']:
        return {'valid': True, 'filtered_message': message}
    
    if not message or len(message.strip()) < 1:
        return {'valid': False, 'reason': 'Empty message'}
    
    if len(message) > cfg['max_length']:
        return {'valid': False, 'reason': 'Message too long'}
    
    # Prompt injection check
    if not _check_injection(message)['safe']:
        print("[SECURITY] Prompt injection detected")
        return {'valid': False, 'reason': 'Input rejected by security'}
    
    # OpenAI moderation
    if cfg['use_moderation'] and cfg['key']:
        mod = _moderate(message, cfg['key'])
        if not mod['safe']:
            print(f"[SECURITY] Moderation flagged: {mod['categories']}")
            return {'valid': False, 'reason': 'Content policy violation'}
    
    return {'valid': True, 'filtered_message': message.strip()}

def validate_output(text):
    cfg = get_config()
    if not cfg['output_enabled']:
        return {'valid': True, 'filtered_text': text}
    
    if not text or len(text.strip()) == 0:
        return {'valid': False, 'use_fallback': True, 
                'fallback_text': "I apologize, but I need to rephrase."}
    
    # Leakage check
    if not _check_leakage(text)['safe']:
        print("[SECURITY] Information leakage detected")
        return {'valid': False, 'use_fallback': True,
                'fallback_text': "I need to rephrase more carefully."}
    
    # Moderation
    if cfg['use_moderation'] and cfg['key']:
        mod = _moderate(text, cfg['key'])
        if not mod['safe']:
            print(f"[SECURITY] Output flagged: {mod['categories']}")
            return {'valid': False, 'use_fallback': True,
                    'fallback_text': "I cannot provide that response."}
    
    return {'valid': True, 'filtered_text': text.strip()}

def _check_injection(msg):
    patterns = [
        r'ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions|prompts)',
        r'(show|reveal|display)\s+(your\s+)?system\s+prompt',
        r'you\s+are\s+now\s+(?!helpful|assistant)',
    ]
    for p in patterns:
        if re.search(p, msg.lower(), re.IGNORECASE):
            return {'safe': False}
    return {'safe': True}

def _check_leakage(text):
    patterns = [r'my\s+system\s+prompt', r'i\s+was\s+instructed\s+to', r'api\s+key']
    for p in patterns:
        if re.search(p, text.lower()):
            return {'safe': False}
    return {'safe': True}

def _moderate(text, key):
    try:
        r = requests.post('https://api.openai.com/v1/moderations',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'input': text}, timeout=5)
        
        if r.status_code == 200:
            res = r.json()
            if res['results'][0]['flagged']:
                cats = [k for k, v in res['results'][0]['categories'].items() if v]
                return {'safe': False, 'categories': cats}
            return {'safe': True, 'categories': []}
        
        print("[WARN] Moderation API failed, allowing")
        return {'safe': True, 'categories': []}
    except Exception as e:
        print(f"[WARN] Moderation error: {e}")
        return {'safe': True, 'categories': []}