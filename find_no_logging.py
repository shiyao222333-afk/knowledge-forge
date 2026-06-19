#!/usr/bin/env python3
"""Find except blocks without logging in kb_query.py."""
import re

with open('D:/citrinitas/kb_query.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("=" * 60)
print("Finding except blocks without proper logging...")
print("=" * 60)

results = []
i = 0
while i < len(lines):
    line = lines[i]
    # Match: except Exception:  or  except Exception as e:
    m = re.match(r'^(\s*)except Exception(\s+as\s+\w+)?\s*:\s*$', line)
    if m:
        indent = len(m.group(1))
        # Collect the except block lines
        block_lines = [line.rstrip()]
        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            next_stripped = next_line.rstrip()
            # Empty line or comment or dedent → end of block
            if next_stripped == '' or next_stripped.startswith('#'):
                block_lines.append(next_stripped)
                j += 1
                continue
            # Check if this line is still part of the block (indented more than except line)
            next_indent = len(next_line) - len(next_line.lstrip())
            if next_indent > indent:
                block_lines.append(next_stripped)
                j += 1
            else:
                break
        block_text = '\n'.join(block_lines)
        # Check if block has logging (logger, print, warn, log)
        has_logging = re.search(r'\b(logger|logging|print|warn|log\.)\b', block_text, re.IGNORECASE)
        # Check if block just has 'pass'
        is_pass_only = re.search(r'^\s*pass\s*$', block_text, re.MULTILINE) and not has_logging
        if not has_logging or is_pass_only:
            results.append((i + 1, is_pass_only, block_text))
        i = j
    else:
        i += 1

print(f"\nFound {len(results)} except blocks without logging:\n")
for lineno, is_pass, block in results:
    tag = " [pass only]" if is_pass else " [no logging]"
    print(f"--- Line {lineno}{tag} ---")
    print(block)
    print()

print("=" * 60)
print(f"Total: {len(results)} locations need logging")
