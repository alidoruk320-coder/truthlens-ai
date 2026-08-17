import re

# Read the files
with open('main.py', 'r') as f:
    main_content = f.read()

with open('image_fix.py', 'r') as f:
    fix_content = f.read()

# Extract just the function from fix file (skip the comment)
fix_lines = fix_content.split('\n')
start_idx = next(i for i, line in enumerate(fix_lines) if line.startswith('def analyze_image_ai_probability'))
new_func = '\n'.join(fix_lines[start_idx:])

# Find and replace the old function
pattern = r'def analyze_image_ai_probability\(image_url: str, source_url: str = ""\) -> dict:.*?(?=\ndef [a-zA-Z_]|\Z)'
updated = re.sub(pattern, new_func, main_content, flags=re.DOTALL)

if updated != main_content:
    with open('main.py', 'w') as f:
        f.write(updated)
    print("✓ Function replaced successfully")
    print(f"  Old size: {len(main_content)}, New size: {len(updated)}")
else:
    print("✗ No match found or replacement failed")
