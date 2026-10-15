# -*- coding: utf-8 -*-
"""Routing test without a model: shows which service/fields each question goes to.
   python test_route.py            (each line = one chat; ' || ' separates follow-up messages)"""
import bot

CHATS = """كم يستغرق تجديد دفتر العائلة؟
وين بقدر أطلع جواز سفر بدل فاقد؟
شو الأوراق المطلوبة لتجديد دفتر العائلة؟ || وبقدر أقدّم الطلب من السفارة إذا كنت برا البلد؟
قديش صورة شخصية بحتاج للبطاقة الذكية لأول مرة، وقديش لتجديد جواز السفر؟
كم سعر تذكرة الطيران من عمان إلى دبي؟
كم يستغرق إصدار دفتر العائلة؟
عمري 17 وجوازي بايق عليه 3 شهور، كم رسوم التجديد؟
شو المطلوب لتجديد دفتر العائلة؟
إذا توفي الأب والأم، مين بصير رب الأسرة؟
أيهما أغلى: جواز بدل تالف ولا بدل فاقد؟
الباسبور خلص، شو بعمل؟
كم رسوم تجديد الهوية؟ || وكم بتكلف إذا ضاعت؟
الزوجة لازم تجيب موافقة جوزها عشان تطلع جواز، صح؟
بدي أجدد، شو المطلوب؟
كم رسوم تصديق الشهادة الجامعية؟
كم رسوم الجواز؟
هويتي اهترت وما عاد تنقرأ، قديش بدفع؟
ضاعت هويتي للمرة الثالثة، شو بصير؟
أنا مسافر برا الأردن وبدي أجدد جوازي، قديش الرسوم؟
ابني عمره 10 سنين بدي أطلعله جواز أول مرة، قديش؟
بعد ما أبلغ عن فقدان الهوية متى بستلمها؟
تزوجت قبل 4 شهور وما فتحت دفتر عائلة، في غرامة؟
كم رسوم جواز السفر الدبلوماسي؟
مرحبا
دفتر العيلة انبل بالمي، شو الأوراق؟""".strip().splitlines()

db = bot.load()
for line in CHATS:
    chat = bot.Chat(db)
    for q in line.split(" || "):
        r = bot.route(q, chat.memory)
        if r["action"] != "answer":
            print(f"\nQ: {q}\n   -> {r['action'].upper()}: {r['message'][:90]}")
            chat.history.append({"q": q, "a": r["message"]})
            continue
        pieces, clar = bot.select(q, r, db)
        if clar:
            print(f"\nQ: {q}\n   -> CLARIFY: {clar[:90]}")
            continue
        print(f"\nQ: {q}\n   -> services={r['services']} fields={r['fields']}")
        for p in pieces:
            print("      ·", p[:110].replace("\n", " / "))
        # update memory the same way Chat.ask does
        chat.memory["services"] = [k for k in r["services"] if k in db] or chat.memory["services"]
        chat.memory["fields"] = r["fields"] or chat.memory["fields"]
