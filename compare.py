# -*- coding: utf-8 -*-
"""
compare.py - print our answers next to the expected answers, message by message, in the terminal.

    python compare.py                                    # answers.json  vs answers_example.json
    python compare.py tests/new/answers.json tests/new/expected.json
    python compare.py tests/hard/answers.json            # just our answers + contexts

Terminals can't show Arabic right-to-left, so this writes compare_report.html (Arabic displays correctly)
and opens it in the browser. Add --text to print in the terminal instead.
"""
import html, json, os, sys, webbrowser

for s in (sys.stdout,):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TEXT = "--text" in sys.argv
args = [a for a in sys.argv[1:] if a != "--text"]
ours_path = args[0] if args else "answers.json"
exp_path = args[1] if len(args) > 1 else ("answers_example.json" if not args else None)

ours = json.load(open(ours_path, encoding="utf-8"))
expected = {}
if exp_path:
    e = json.load(open(exp_path, encoding="utf-8"))
    if isinstance(e, dict) and "chats" in e:          # answers_example.json format
        for c in e["chats"]:
            for m in c["messages"]:
                expected[m["message_id"]] = (m.get("answer", ""), m.get("contexts", []))
    else:                                             # tests/*/expected.json format: {message_id: expected answer}
        expected = {k: (v, None) for k, v in e.items()}

if not TEXT:
    rows = []
    n = 0
    for c in ours["chats"]:
        for m in c["messages"]:
            n += 1
            mid = m["message_id"]
            ctx = "".join(f"<li>{html.escape(x)}</li>" for x in m.get("contexts", [])) or "<li class=none>[] لا يوجد</li>"
            exp, exp_ctx = expected.get(mid, ("", None))
            ectx = "" if exp_ctx is None else ("".join(f"<li>{html.escape(x)}</li>" for x in exp_ctx) or "<li class=none>[]</li>")
            rows.append(f"""<tr><td class=id>{html.escape(mid)}</td><td class=q>{html.escape(m['question'])}</td>
<td><div class=ans>{html.escape(m.get('answer', '(missing!)'))}</div><ul class=ctx>{ctx}</ul></td>
<td><div class=exp>{html.escape(str(exp))}</div>{f'<ul class=ctx>{ectx}</ul>' if ectx else ''}</td>
<td class=ok><label><input type=checkbox> ✓</label></td></tr>""")
    page = f"""<!doctype html><html lang=ar dir=rtl><meta charset=utf-8><title>مقارنة الأجوبة</title>
<style>body{{font-family:"Segoe UI",Tahoma,Arial,sans-serif;margin:20px;background:#f6f7f6;color:#1c211e}}
h1{{font-size:20px}} .meta{{color:#555;margin-bottom:12px}} table{{border-collapse:collapse;width:100%;background:#fff}}
th{{background:#00592c;color:#fff;padding:8px;position:sticky;top:0}} td{{border-bottom:1px solid #ddd;padding:8px;vertical-align:top}}
tr:nth-child(even) td{{background:#fafbfa}} .id{{direction:ltr;color:#888;font-size:12px;white-space:nowrap}} .q{{font-weight:bold;width:22%}}
.ans{{white-space:pre-wrap;color:#0b5a32}} .exp{{white-space:pre-wrap;color:#7a1020}} .ctx{{margin:8px 0 0;padding-right:18px;font-size:12px;color:#555}}
.none{{color:#aaa}} .ok{{text-align:center;width:50px}}</style>
<h1>مقارنة الأجوبة</h1><div class=meta>{html.escape(ours_path)} مقابل {html.escape(exp_path or "—")} · {n} رسالة ·
تأكد: نفس الأرقام والوثائق والأماكن؟ والنصوص (contexts) من الخدمة الصحيحة؟</div>
<table><tr><th>#</th><th>السؤال</th><th>جوابنا + النصوص اللي استخدمها</th><th>الجواب المتوقع</th><th>صح؟</th></tr>{"".join(rows)}</table></html>"""
    out = os.path.abspath("compare_report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"report written: {out}  ({n} messages) - opening in the browser")
    webbrowser.open("file:///" + out.replace(os.sep, "/"))
    sys.exit(0)

line = "-" * 70
for c in ours["chats"]:
    for m in c["messages"]:
        mid = m["message_id"]
        print(line)
        print(f"[{mid}]  Q: {m['question']}")
        print(f"  OUR ANSWER : {m.get('answer', '(missing!)')}")
        if mid in expected:
            print(f"  EXPECTED   : {expected[mid][0]}")
        print(f"  OUR CONTEXTS ({len(m.get('contexts', []))}):")
        for x in m.get("contexts", []):
            print("     -", x.replace("\n", " / ")[:160])
        if mid in expected and expected[mid][1] is not None:
            print(f"  EXPECTED CONTEXTS ({len(expected[mid][1])}):")
            for x in expected[mid][1]:
                print("     -", x[:160])
print(line)
print("Check each one: same facts (numbers, documents, places)? contexts from the right service?")
