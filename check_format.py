# -*- coding: utf-8 -*-
"""
check_format.py - checks answers.json against the brief's rules (the scoring is automatic, so the format must be exact).

    python check_format.py                          # questions.json vs answers.json in this folder
    python check_format.py tests/new/questions.json tests/new/answers.json
"""
import json, sys

q_path = sys.argv[1] if len(sys.argv) > 1 else "questions.json"
a_path = sys.argv[2] if len(sys.argv) > 2 else "answers.json"
problems = []
try:
    with open(a_path, encoding="utf-8") as f:   # must be valid JSON in UTF-8
        a = json.load(f)
except Exception as e:
    sys.exit(f"FAIL: {a_path} is not valid UTF-8 JSON: {e}")
with open(q_path, encoding="utf-8-sig") as f:
    q = json.load(f)

if [c.get("chat_id") for c in q["chats"]] != [c.get("chat_id") for c in a.get("chats", [])]:
    problems.append("chats missing, extra or reordered")
n = 0
for cq, ca in zip(q["chats"], a.get("chats", [])):
    mq, ma = cq.get("messages", []), ca.get("messages", [])
    if len(mq) != len(ma):
        problems.append(f"{cq['chat_id']}: {len(mq)} messages in questions, {len(ma)} in answers")
    for x, y in zip(mq, ma):
        n += 1
        mid = x.get("message_id")
        for k, v in x.items():                       # everything we received must be unchanged
            if y.get(k) != v:
                problems.append(f"{mid}: key '{k}' was changed")
        if not isinstance(y.get("answer"), str) or not y["answer"].strip():
            problems.append(f"{mid}: missing or empty 'answer'")
        if not isinstance(y.get("contexts"), list) or not all(isinstance(c, str) for c in y["contexts"]):
            problems.append(f"{mid}: 'contexts' must be a list of strings ([] if nothing found)")
        elif any(len(c) > 3000 for c in y["contexts"]):
            problems.append(f"{mid}: a context looks like a whole file (should be only the pieces used)")

if problems:
    print(f"FAIL: {len(problems)} problem(s)")
    for p in problems[:30]:
        print("  -", p)
    sys.exit(1)
print(f"OK: {n} messages in {len(q['chats'])} chats - structure, ids, order, answer and contexts all match the brief")
