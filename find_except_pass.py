#!/usr/bin/env python3
"""Find except:pass patterns in kb_query.py."""
import re

with open('D:/citrinitas/kb_query.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=" * 60)
print("Searching for bare except:pass patterns...")
print("=" * 60)

matches = []
for i, line in enumerate(lines):
    # Pattern 1: except:pass on same line
    if re.search(r'\bexcept\s*:\s*pass\s*$', line):
        matches.append((i+1, 'same_line', line.rstrip()))
    # Pattern 2: except Exception: followed by pass on next line
    elif re.search(r'^\s*except\s+Exception\s*:\s*$', line):
        if i+1 < len(lines) and re.search(r'^\s*pass\s*$', lines[i+1]):
            matches.append((i+1, 'two_lines', line.rstrip(), lines[i+1].rstrip()))

for m in matches:
    if m[1] == 'same_line':
        print(f"\nLine {m[0]}: {m[2]}")
    else:
        print(f"\nLine {m[0]}: {m[2]}")
        print(f"Line {m[0]+1}: {m[3]}")
    print("-" * 40)

print(f"\nTotal matches: {len(matches)}")
