import subprocess, os

os.chdir("D:/Citrinitas")

# 查所有 v0.5 相关的 tag
result = subprocess.run(["git", "tag", "-l", "v0.5*"], capture_output=True, text=True)
print("=== git tags v0.5* ===")
print(result.stdout or "(none)")
print(result.stderr or "")

# 查所有 tag
result2 = subprocess.run(["git", "tag", "-l"], capture_output=True, text=True)
print("=== all tags ===")
print(result2.stdout or "(none)")

# 查最近10个提交，看有没有提到版本号
result3 = subprocess.run(["git", "log", "--oneline", "-20"], capture_output=True, text=True)
print("=== recent 20 commits ===")
print(result3.stdout or "")

# 查 PROJECT_PLAN.md 里「守望文件夹」出现在哪里
try:
    with open("PROJECT_PLAN.md", "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if "守望" in line or "watch" in line.lower() or "folder" in line.lower():
            print(f"PROJECT_PLAN.md:{i+1}: {line.strip()}")
except Exception as e:
    print(f"Error reading PROJECT_PLAN: {e}")
