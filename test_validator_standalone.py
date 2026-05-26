#!/usr/bin/env python3
"""
Standalone test for the validator using the actual production class with a mocked frappe
"""
import json
import os
import sys

# Mock frappe to avoid import errors and database dependency
class MockFrappeDb:
    @staticmethod
    def exists(doctype, filters):
        # Mock port codes to exist
        if doctype == "SPS-Port":
            # XZiii is blocked, other ports exist
            name = filters.get("name")
            return name != "XZiii"
        return True

class MockFrappe:
    db = MockFrappeDb()
    
    @staticmethod
    def log_error(message, title="", reference=""):
        print(f"[LOG ERROR] {title}: {message}")
    
    @staticmethod
    def whitelist():
        def decorator(func):
            return func
        return decorator
    
    @staticmethod
    def _(text):
        return text

sys.modules['frappe'] = MockFrappe()

# Add parent path to import port_msg_validator_hub
sys.path.insert(0, '/home/frappe/fbench/apps/port_msg_validator_hub')

# Import the actual validator class from the app
from port_msg_validator_hub.msg_validator import UniversalMessageValidator

if __name__ == '__main__':
    msg3501_path = '/home/frappe/fbench/apps/port_msg_validator_hub/port_msg_validator_hub/sample_msg3501.xml'
    msg2701_path = '/home/frappe/fbench/apps/port_msg_validator_hub/port_msg_validator_hub/sample_msg2701.xml'
    
    # Test MSG3501 (Expect Valid)
    with open(msg3501_path, 'r', encoding='utf-8') as f:
        msg3501 = f.read()
    
    print("=" * 80)
    print("TESTING MSG3501 MESSAGE WITH PRODUCTION VALIDATOR")
    print("=" * 80)
    
    validator = UniversalMessageValidator()
    result = validator.validate_message(msg3501)
    
    print(f"\nMessage Type Detected: {validator.detected_message_type}")
    print(f"Schema Format: {validator.schema_format}")
    print(f"\nValidation Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result['valid']:
        print("\n✓ MSG3501 VALIDATION PASSED!")
    else:
        print("\n✗ MSG3501 VALIDATION FAILED!")
        print(f"Errors: {result['error_count']}")
        sys.exit(1)
        
    # Test MSG2701 (Expect Invalid - sample contains invalid Goods_Status '01')
    with open(msg2701_path, 'r', encoding='utf-8') as f:
        msg2701 = f.read()
        
    print("\n" + "=" * 80)
    print("TESTING MSG2701 MESSAGE WITH PRODUCTION VALIDATOR (EXPECTED FAILURE)")
    print("=" * 80)
    
    validator2 = UniversalMessageValidator()
    result2 = validator2.validate_message(msg2701)
    
    print(f"\nMessage Type Detected: {validator2.detected_message_type}")
    print(f"Schema Format: {validator2.schema_format}")
    print(f"\nValidation Result:")
    print(json.dumps(result2, indent=2, ensure_ascii=False))
    
    # We expect this to fail due to Goods_Status ('01' is not one of ['05', '06'])
    expected_error = "is not one of ['05', '06']"
    has_expected_error = False
    
    if result2['errors'] and result2['errors'].get('invalid_values'):
        for err in result2['errors']['invalid_values']:
            if expected_error in err:
                has_expected_error = True
                break
                
    if not result2['valid'] and has_expected_error:
        print("\n✓ MSG2701 VALIDATION FAILED AS EXPECTED (Successfully caught invalid Goods_Status '01')!")
    else:
        print("\n✗ MSG2701 VALIDATION BEHAVIOR UNEXPECTED!")
        if result2['valid']:
            print("Error: Message was marked as valid but should have failed validation.")
        else:
            print(f"Error: Validation failed but didn't contain the expected error. Errors: {result2['errors']}")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("🎉 ALL STANDALONE TESTS PASSED SUCCESSFULLY! PRODUCTION LOGIC IS FULLY FUNCTIONAL!")
    print("=" * 80)
    sys.exit(0)
