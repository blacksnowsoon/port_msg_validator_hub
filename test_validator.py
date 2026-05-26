#!/usr/bin/env python3
"""
Test the UniversalMessageValidator with real message samples
"""
import json
import sys
import os

# Add to path
sys.path.insert(0, '/home/frappe/fbench')
sys.path.insert(0, '/home/frappe/fbench/apps/port_msg_validator_hub')

def test_messages():
    """Test validator with real messages"""
    
    # Read the sample files
    msg2701_path = '/home/frappe/fbench/apps/port_msg_validator_hub/port_msg_validator_hub/sample_msg2701.xml'
    msg3501_path = '/home/frappe/fbench/apps/port_msg_validator_hub/port_msg_validator_hub/sample_msg3501.xml'
    
    with open(msg2701_path, 'r', encoding='utf-8') as f:
        msg2701 = f.read()
    
    with open(msg3501_path, 'r', encoding='utf-8') as f:
        msg3501 = f.read()
    
    # Import validator
    try:
        from port_msg_validator_hub.msg_validator import UniversalMessageValidator
    except ImportError:
        # Try without the module path
        import validate3501
        UniversalMessageValidator = validate3501.UniversalMessageValidator
    
    print("=" * 80)
    print("TESTING MSG2701 MESSAGE")
    print("=" * 80)
    
    validator2701 = UniversalMessageValidator()
    result2701 = validator2701.validate_message(msg2701)
    
    print(f"\nMessage Type Detected: {validator2701.detected_message_type}")
    print(f"Schema Format: {validator2701.schema_format}")
    print(f"\nValidation Result:")
    print(json.dumps(result2701, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 80)
    print("TESTING MSG3501 MESSAGE")
    print("=" * 80)
    
    validator3501 = UniversalMessageValidator()
    result3501 = validator3501.validate_message(msg3501)
    
    print(f"\nMessage Type Detected: {validator3501.detected_message_type}")
    print(f"Schema Format: {validator3501.schema_format}")
    print(f"\nValidation Result:")
    print(json.dumps(result3501, indent=2, ensure_ascii=False))
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"MSG2701: {'✓ VALID' if result2701['valid'] else '✗ INVALID'}")
    print(f"MSG3501: {'✓ VALID' if result3501['valid'] else '✗ INVALID'}")
    
    return result2701['valid'] and result3501['valid']

if __name__ == '__main__':
    try:
        success = test_messages()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Test failed with error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
