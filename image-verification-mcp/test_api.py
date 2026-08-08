#!/usr/bin/env python3
"""Test the MCP server API via FluidMCP"""
import base64
import requests
import json

# Read test image
with open('/tmp/irctc_realistic.jpg', 'rb') as f:
    image_b64 = base64.b64encode(f.read()).decode('utf-8')

# Call the tool
payload = {
    "name": "verify_image_authenticity",
    "arguments": {
        "image_base64": image_b64,
        "document_type": "irctc"
    }
}

try:
    response = requests.post(
        'http://localhost:8090/image-verification/mcp/tools/call',
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    
    print("Status Code:", response.status_code)
    print("\nResponse:")
    result = response.json()
    print(json.dumps(result, indent=2))
    
    # Pretty print the verification result
    if 'content' in result and len(result['content']) > 0:
        verification = result['content'][0].get('text', '')
        if verification:
            print("\n" + "="*60)
            print("VERIFICATION RESULT:")
            print("="*60)
            try:
                parsed = json.loads(verification)
                print(f"Is Real Image: {parsed.get('is_real_image')}")
                print(f"Is AI Generated: {parsed.get('is_ai_generated')}")
                print(f"Is Tampered: {parsed.get('is_tampered')}")
                print(f"Confidence: {parsed.get('confidence')}")
                print(f"\nReasoning:")
                for reason in parsed.get('reasoning', []):
                    print(f"  • {reason}")
            except:
                print(verification)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
