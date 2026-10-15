# -*- coding: utf-8 -*-
"""
bot.py - Nashmi Pro: answers questions about 12 Jordanian civil-status services, only from data/.

Pipeline for one message:
  1. load()      parse each data/*.txt into its 9 fields  -> pieces "service - field: text"
  2. route()     decide WHICH service(s) (document x situation) and WHICH field(s) the question is about
                 (rule-based, dialect-aware; uses the chat memory for follow-ups)
  3. decide      out of scope -> polite decline | unclear -> ask which one | else -> pick the pieces
  4. generate()  send only those pieces to the Ollama model with a strict "answer only from this" prompt
Only Python's standard library is used (Ollama is called over HTTP), so there is nothing to pip install.
"""
import glob, json, os, re, unicodedata, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "")          # empty = PREFERRED if installed, else the first chat model in Ollama
PREFERRED = "command-r7b-arabic"
NUM_CTX = int(os.getenv("NUM_CTX", "8192"))     # set explicitly: Ollama's default window silently cuts text
NUM_PREDICT = int(os.getenv("NUM_PREDICT", "500"))

# ------------------------------------------------------------------ 1. Arabic normalization
_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def norm(text):
    """Spelling-insensitive form used ONLY for matching (never shown to the user)."""
    t = unicodedata.normalize("NFKC", str(text))
    t = _DIAC.sub("", t)
    t = t.replace("ی", "ي").replace("ک", "ك").replace("ھ", "ه")
    t = re.sub("[إأآٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    return re.sub(r"\s+", " ", t.lower()).strip()


# ------------------------------------------------------------------ 2. Loading + cleaning the 12 files
FIELDS = [  # (key, label exactly as it starts a line in the files)
    ("beneficiary", "الفئة المستفيدة"),
    ("places", "أماكن تقديم الخدمة"),
    ("conditions", "شروط تقديم الخدمة"),
    ("documents", "الوثائق المطلوبة للحصول على الخدمة"),
    ("procedure", "إجراءات تقديم الخدمة"),
    ("time", "الزمن المستغرق لتقديم الخدمة"),
    ("partners", "شركاء الخدمة"),
    ("notes", "ملاحظات"),
    ("fees", "الرسوم"),
]
FIELD_LABEL = dict(FIELDS)
MENU = {"الرئيسية", "الخدمات", "دليل الخدمات", "شارك"}
# amounts written as words -> add the digit next to them (the fact is unchanged, the model reads it better)
WORD_AMOUNTS = [("دينارين", "دينارين (2 دينار)"), ("ثلاثة دنانير", "ثلاثة (3) دنانير"),
                ("عشرة دنانير", "عشرة (10) دنانير"), ("خمسة دنانير", "خمسة (5) دنانير")]

DOC_NAMES = {"passport": "جواز السفر", "family_book": "دفتر العائلة", "id_card": "البطاقة الذكية (الهوية)"}
SIT_NAMES = {"first_issue": "لأول مرة", "renewal": "تجديد", "lost": "بدل فاقد", "damaged": "بدل تالف"}


def clean_lines(text):
    lines = []
    for raw in text.replace("\r", "").split("\n"):
        l = re.sub(r"[ \t ]+", " ", raw).strip()
        l = l.replace("]", "").replace("‘", "")
        if l:
            lines.append(l)
    return lines


def parse_service(path):
    """One file -> {'key','doc','situation','title','fields':{field: text}}"""
    key = os.path.splitext(os.path.basename(path))[0]
    key = re.sub(r"^[0-9a-f]{8}-", "", key)  # tolerate upload prefixes like 'b4a629a2-passport_renewal'
    with open(path, encoding="utf-8-sig") as f:
        lines = clean_lines(f.read())
    # drop the website menu: everything up to and including 'شارك'; the next line is the real title
    if "شارك" in lines[:8]:
        i = lines.index("شارك")
        lines = lines[i + 1:]
    lines = [l for l in lines if l not in MENU]
    title = lines[0].strip("() ") if lines else key
    fields, cur = {}, None
    for l in lines[1:]:
        hit = next(((k, lab) for k, lab in FIELDS if l.startswith(lab)), None)
        if hit:
            cur = hit[0]
            rest = l[len(hit[1]):].strip(" :\t")
            fields.setdefault(cur, [])
            if rest:
                fields[cur].append(rest)
        elif cur:
            if not fields[cur] or fields[cur][-1] != l:  # drop exact repeated lines
                fields[cur].append(l)
    out = {}
    for k, v in fields.items():
        txt = "\n".join(v).strip()
        for a, b in WORD_AMOUNTS:
            txt = txt.replace(a, b)
        out[k] = txt or "لا يوجد"
    doc = next((d for d in DOC_NAMES if key.startswith(d)), "")
    sit = key[len(doc) + 1:] if doc else ""
    return {"key": key, "doc": doc, "situation": sit, "title": title, "fields": out}


def load(data_dir=DATA_DIR):
    services = {}
    for p in sorted(glob.glob(os.path.join(data_dir, "*.txt"))):
        s = parse_service(p)
        services[s["key"]] = s
    return services


def piece(service, field):
    """The context string: 'تجديد دفتر العائلة - الرسوم: ...' (same shape as the organisers' example)."""
    return f"{service['title']} - {FIELD_LABEL[field]}: {service['fields'].get(field, 'لا يوجد')}"


# ------------------------------------------------------------------ 3. Router vocabulary (normalized forms)
DOC_WORDS = {
    "passport": ["جواز", "جوازي", "جوازه", "جوازها", "جوازات السفر", "باسبور", "الباسبور", "باسبوري", "بسبور", "passport"],
    "family_book": ["دفتر", "دفتري", "الدفتر", "دفتر العايله", "دفتر عيله", "رب الاسره", "family book"],
    "id_card": ["هويه", "الهويه", "هويتي", "هويته", "هويتها", "بطاقه ذكيه", "البطاقه الذكيه", "البطاقه الشخصيه",
                "بطاقه شخصيه", "بطاقه احوال", "بطاقتي", "البطاقه", "بطاقه", "الذكيه", "id card", "smart id"],
}
SIT_WORDS = {  # order of checking = priority (lost/damaged beat renewal beat first issue)
    "lost": ["فاقد", "فقدان", "مفقود", "فقدت", "فقد", "ضاع", "ضايع", "ضايعه", "ضاعت", "ضيعت", "ضيعته", "ضيعتها",
             "انسرق", "انسرقت", "سرق", "سرقت", "انسرقلي", "lost", "stolen"],
    "damaged": ["تالف", "تلف", "تلفت", "تالفه", "خرب", "خربان", "خربت", "خربانه", "انكسر", "انكسرت", "مكسور", "مقطوع",
                "انقطع", "انقطعت", "تمزق", "ممزق", "اهترى", "اهتري", "اهترت", "مهتري", "مهتريه", "ما عاد تنقرا", "مش واضحه", "تبهدل", "مبلول", "انبل", "انغسل", "damaged"],
    "renewal": ["تجديد", "اجدد", "بجدد", "يجدد", "نجدد", "جدد", "جددت", "خلص", "خلصت", "منتهي", "منتهيه", "انتهى",
                "انتهت", "انتهاء", "صلاحيته", "باقي عليه", "بايق عليه", "ممتلي", "ممتلئ", "صالح", "ساري", "renew", "expired"],
    "first_issue": ["اول مره", "لاول مره", "لاول", "اول", "اصدار", "استخراج", "اطلع", "بطلع", "نطلع", "يطلع", "تطلع",
                    "اعمل", "جديد", "ما عندي", "طلعت", "ما طلعت", "استخرجت", "فتح", "فتحت", "افتح", "تزوجت", "اتزوجت", "first"],
}
FIELD_WORDS = {
    "fees": ["رسوم", "قديش", "كم بكلف", "بكلف", "بتكلف", "تكلفه", "كلفه", "سعر", "بدفع", "ادفع", "ندفع", "دفع", "مصاري",
             "فلوس", "دينار", "غرامه", "اغلى", "ارخص", "كفاله", "تعهد", "cost", "fee", "price"],
    "documents": ["اوراق", "الاوراق", "ورق", "وثائق", "الوثائق", "مستندات", "بلزم", "يلزم", "بلزمني", "المطلوب", "مطلوب",
                  "اجيب", "احضر", "صوره", "صور", "documents"],
    "conditions": ["شروط", "مين بقدر", "مين يحق", "يحق", "بقدر", "بيقدر", "موافقه", "حضور", "شخصيا", "الزوجه",
                   "زوجته", "مرتي", "ولي الامر", "القاصر", "قاصر", "ابني", "بنتي", "اولادي", "توكيل", "تفويض"],
    "time": ["يستغرق", "مده", "وقت", "بوخذ", "بياخد", "بتاخد", "بياخذ", "دقيقه", "ساعه", "متى بطلع", "قديش بطول", "بستلم", "استلم", "تستلم", "جاهز", "how long"],
    "places": ["وين", "اين", "مكان", "اماكن", "سفاره", "السفاره", "قنصليه", "القنصليه", "برا", "الخارج", "خارج", "مكتب", "where"],
    "procedure": ["اجراءات", "خطوات", "طريقه", "مراحل", "كيف", "procedure", "steps"],
    "notes": ["ملاحظات", "رب الاسره", "توفي", "وفاه", "اسبوعين", "خلال", "مهله"],
    "partners": ["شركاء", "جهات", "جهه"],
    "beneficiary": ["الفئه", "المستفيد", "مين المستفيد"],
}
GENERAL = ["شو بعمل", "شو اعمل", "شو لازم", "كيف بعمل", "شو الحل", "ساعدني", "شو بصير"]
# Services that sound related but are NOT in the data -> always decline
OUT_STRONG = ["دبلوماسي", "رخصه", "سواقه", "قياده", "فيزا", "تاشيره", "تذكره", "طيران", "عدم محكوميه", "شهاده ميلاد",
              "شهاده وفاه", "تصديق", "جامعيه", "اقامه عمل", "تصريح عمل", "جنسيه اردنيه لابناء"]

for _d in (DOC_WORDS, SIT_WORDS, FIELD_WORDS):
    for _k in _d:
        _d[_k] = list(dict.fromkeys(norm(w) for w in _d[_k]))
GENERAL[:] = [norm(w) for w in GENERAL]
OUT_STRONG[:] = [norm(w) for w in OUT_STRONG]

DECLINE = "عذراً، لا تتوفر لدي معلومات عن هذا الموضوع. أستطيع المساعدة فقط في خدمات جواز السفر ودفتر العائلة والبطاقة الذكية (لأول مرة، التجديد، بدل فاقد، بدل تالف)."


SUFFIX = r"(?:ه|ها|هم|ك|ي|نا|و|وا|ته|تها|له|لها|لي|ني)?"  # attached endings: اجدده، اطلعله، بلزمني


def _has(qn, words):
    """True if any word/phrase appears in the normalized question as a whole word (or word prefix for 1-letter clitics)."""
    for w in words:
        if re.search(r"(^|[\s،,؟?.!:\-و ب ل ف])" + re.escape(w) + SUFFIX + r"($|[\s،,؟?.!:])", " " + qn + " "):
            return True
    return False


def _find_docs(qn):
    found = [d for d, ws in DOC_WORDS.items() if _has(qn, ws)]
    # "البطاقة الشخصية" next to a passport/family book is usually a REQUIRED document, not the service asked about
    if "id_card" in found and len(found) > 1 and not _has(qn, ["هويه", "الهويه", "هويتي", "بطاقه ذكيه", "البطاقه الذكيه", "الذكيه"]):
        found.remove("id_card")
    return found


def _find_sits(qn):
    sits = [s for s, ws in SIT_WORDS.items() if _has(qn, ws)]
    # "وين بطلع جواز بدل فاقد": اطلع means 'get', the real situation is فاقد
    if "first_issue" in sits and len(sits) > 1:
        sits.remove("first_issue")
    return sits


def _find_fields(qn):
    f = [k for k, ws in FIELD_WORDS.items() if _has(qn, ws)]
    strong_fee = [w for w in FIELD_WORDS["fees"] if w not in (norm("قديش"),)]
    if "fees" in f and "documents" in f and not _has(qn, strong_fee):
        f.remove("fees")         # "قديش صورة بحتاج" asks how many photos, not the price
    weak_cond = [norm(w) for w in ("بقدر", "بيقدر")]
    strong_cond = [w for w in FIELD_WORDS["conditions"] if w not in weak_cond]
    if "conditions" in f and len(f) > 1 and not _has(qn, strong_cond):
        f.remove("conditions")   # "وين بقدر أطلع..." asks WHERE, not the conditions
    family_weak = [norm(w) for w in ("الزوجه", "زوجته", "مرتي", "ابني", "بنتي", "اولادي")]
    if "conditions" in f and len(f) > 1 and not _has(qn, [w for w in FIELD_WORDS["conditions"] if w not in family_weak + weak_cond]):
        f.remove("conditions")   # "ابني بدنا نطلعله جواز، كم؟" asks the fee; the child is only context
    if not f and _has(qn, [norm("كم"), norm("قديش")]):
        f = ["fees"]             # "...، كم؟" at the end = how much
    receive = [norm(w) for w in ("بستلم", "استلم", "تستلم", "جاهز", "جاهزه", "متى")]
    if any(x in f for x in ("fees", "conditions")) or ("time" in f and _has(qn, receive)):
        f.append("notes")  # extra charges, deadlines, waiting periods and exceptions hide in the notes
    return list(dict.fromkeys(f))


def _clauses(qn):
    parts = [p.strip() for p in re.split(r"[،,؟?.!\n؛;]| وكمان | و ", qn) if p.strip()]
    return parts or [qn]


GREET = [norm(w) for w in ("مرحبا", "مرحبتين", "هلا", "اهلا", "السلام عليكم", "صباح الخير", "مساء الخير", "hi", "hello")]
THANKS = [norm(w) for w in ("شكرا", "مشكور", "يعطيك العافيه", "تسلم", "يسلمو", "thanks")]


def route(question, memory):
    """Returns a dict: {'action': 'answer'|'clarify'|'decline', 'services': [...], 'fields': [...], 'message': str}"""
    qn = norm(question)
    if len(qn.split()) <= 4 and not _find_docs(qn) and not _find_sits(qn):
        if _has(qn, THANKS):
            return {"action": "clarify", "services": [], "fields": [], "message": "العفو! إذا عندك أي سؤال ثاني عن جواز السفر أو دفتر العائلة أو البطاقة الذكية أنا جاهز."}
        if _has(qn, GREET):
            return {"action": "clarify", "services": [], "fields": [], "message": "أهلاً وسهلاً! أنا مساعد دائرة الأحوال المدنية والجوازات. بقدر أساعدك بخدمات جواز السفر ودفتر العائلة والبطاقة الذكية: لأول مرة، التجديد، بدل فاقد، وبدل تالف. شو سؤالك؟"}
    if _has(qn, OUT_STRONG):
        return {"action": "decline", "services": [], "fields": [], "message": DECLINE}

    # pair every document with the situation written in the SAME clause ("للبطاقة لأول مرة، وقديش لتجديد الجواز")
    pairs = []
    clauses = _clauses(qn)
    for i, c in enumerate(clauses):
        docs, sits = _find_docs(c), _find_sits(c)
        if docs and not sits:  # situation may sit in the neighbouring clause
            for j in (i - 1, i + 1):
                if 0 <= j < len(clauses) and not _find_docs(clauses[j]):
                    sits = _find_sits(clauses[j])
                    if sits:
                        break
        for d in docs:
            pairs.append((d, sits))
    all_docs = _find_docs(qn)
    all_sits = _find_sits(qn)
    fields = _find_fields(qn)
    general = _has(qn, GENERAL)

    if not pairs:
        if memory.get("services"):  # follow-up: "وكم بتكلف؟" -> same service(s) as before
            services = memory["services"]
            docs_before = list(dict.fromkeys(next(d for d in DOC_NAMES if k.startswith(d)) for k in services))
            if all_sits and len(docs_before) == 1:  # "وإذا ضاع؟" -> same document, new situation
                services = [f"{docs_before[0]}_{s}" for s in all_sits]
            return {"action": "answer", "services": services, "fields": fields or memory.get("fields") or [], "general": general}
        if all_sits or fields:
            return {"action": "clarify", "services": [], "fields": fields,
                    "message": "ممكن توضح عن أي وثيقة بتسأل؟ جواز السفر، دفتر العائلة، أو البطاقة الذكية (الهوية)؟"}
        return {"action": "decline", "services": [], "fields": [], "message": DECLINE}

    services, unclear_docs = [], []
    for d, sits in pairs:
        sits = sits or (memory.get("sits", {}).get(d, []))
        if not sits:
            unclear_docs.append(d)
        for s in sits:
            k = f"{d}_{s}"
            if k not in services:
                services.append(k)
    return {"action": "answer", "services": services, "fields": fields, "general": general, "unclear_docs": unclear_docs}


# ------------------------------------------------------------------ 4. Choosing the pieces (contexts)
DEFAULT_FIELDS = ["conditions", "documents", "fees", "time", "places", "notes"]


def _tokens(t):
    stop = {"في", "من", "على", "علي", "الى", "عن", "ما", "هل", "شو", "كم", "قديش", "انا", "اذا", "او", "و", "لا", "مع",
            "بدي", "عشان", "اللي", "هو", "هي", "يا", "كيف", "وين", "متى"}
    out = set()
    for w in re.findall(r"\w+", norm(t)):
        if w in stop or len(w) < 2:
            continue
        w = re.sub(r"^(وال|بال|لل|ال|و|ب|ل|ف)(?=\w{3,})", "", w)
        out.add(w[:5])  # crude stem: first 5 letters
    return out


def best_fields(question, service, k=2):
    """No field keyword in the question: score the 9 fields of the service by word overlap."""
    q = _tokens(question)
    scored = []
    for f, txt in service["fields"].items():
        scored.append((len(q & _tokens(txt)), f))
    scored.sort(reverse=True)
    return [f for s, f in scored[:k] if s > 0]


STRICT_FIELDS = {"fees", "documents", "conditions", "procedure"}
URGENT = [norm(w) for w in ("مستعجل", "مستعجله", "المستعجله", "الخدمه المستعجله", "بسرعه", "عاجل")]


def _distinct(texts, sim=0.8):
    """How many really different texts (word-overlap similarity >= sim counts as the same)."""
    groups = []
    for t in texts:
        tt = _tokens(t)
        if not any(len(tt & g) / max(1, len(tt | g)) >= sim for g in groups):
            groups.append(tt)
    return len(groups)


def select(question, r, services_db):
    """Turn a route into the list of context pieces, or into a clarifying question."""
    keys = [k for k in r["services"] if k in services_db]
    unclear = r.get("unclear_docs", [])
    fields = r["fields"]

    # a document named without its situation ("كم رسوم الجواز؟", "مين بصير رب الأسرة؟")
    for d in unclear:
        cands = [k for k in services_db if k.startswith(d)]
        strict = [f for f in fields if f in STRICT_FIELDS]
        if strict:  # fees / documents / conditions / procedure differ per situation: only answer if truly identical
            texts = [" ".join(services_db[k]["fields"].get(f, "") for f in strict) for k in cands]
            keep = cands if _distinct(texts) == 1 else None
        else:       # time, place, a rule in the notes...: keep the situations whose text matches the question best
            q, scored = _tokens(question), []
            for k in cands:
                fs = fields or best_fields(question, services_db[k], 2)
                txt = " ".join(services_db[k]["fields"].get(f, "") for f in fs)
                scored.append((len(q & _tokens(txt)), k, txt))
            top = max(sc for sc, _, _ in scored)
            best = [(k, t) for sc, k, t in scored if sc == top and sc > 0]
            keep = [best[0][0]] if best and _distinct([t for _, t in best]) == 1 else None
        if keep:
            keys.append(keep[0])
        else:
            opts = "، ".join(f"{DOC_NAMES[d]} {SIT_NAMES[s]}" for s in SIT_NAMES)
            return None, f"حتى أعطيك الجواب الصحيح، عن أي خدمة بالضبط بتسأل؟ ({opts})"
    if not keys:
        return None, "ممكن توضح سؤالك أكثر؟ عن أي وثيقة وأي خدمة بتسأل؟"

    pieces = []
    for k in keys:
        s = services_db[k]
        if fields:
            want = fields
        elif r.get("general"):
            want = DEFAULT_FIELDS
        else:
            want = best_fields(question, s, 2)
            if want:
                want = want + (["notes"] if "notes" not in want else [])
            else:
                want = DEFAULT_FIELDS
        for f in want:
            if f in s["fields"]:
                if f == "notes" and norm(s["fields"][f]) in ("لا يوجد", ""):
                    continue
                p = piece(s, f)
                if f == "fees" and _has(norm(question), URGENT) and "مستعجل" in norm(s["fields"].get("notes", "")):
                    p = piece(s, "notes")  # "قديش بزيد المستعجل؟" -> the note "يضاف 25 دينار" is the answer
                if f == "fees" and r.get("profile") and not _has(norm(question), URGENT):
                    p = f"{s['title']} - {FIELD_LABEL['fees']}: {filter_fees(s['fields']['fees'], r['profile'])}"
                if p not in pieces:
                    pieces.append(p)
    return pieces, None


# ------------------------------------------------------------------ 5. Generation (Ollama over HTTP)
SYSTEM = """أنت مساعد رسمي لدائرة الأحوال المدنية والجوازات في الأردن.
تجيب عن أسئلة المواطنين عن خدمات جواز السفر ودفتر العائلة والبطاقة الذكية، اعتماداً فقط على "النصوص الرسمية" المرفقة.

قواعد صارمة:
1. استخدم فقط المعلومات الموجودة في النصوص الرسمية. لا تضف أي معلومة من معرفتك العامة، حتى لو كنت متأكداً منها.
2. انقل الأرقام والمبالغ والمدد والأعداد كما هي في النص تماماً.
3. إذا كانت الرسوم أو الشروط تختلف حسب حالة الشخص، فاستخدم "حقائق عن حالة السائل" المرفقة (إن وجدت) لاختيار الحالة التي تنطبق عليه وأعطه مبلغها. إذا لم تكفِ الحقائق، فاذكر الحالات المختلفة.
   انقل وصف كل حالة كما هو مكتوب في النص حرفياً. لا تفترض شيئاً عن السائل لم يذكره (مثلاً لا تفترض أنه عسكري). لا تجمع المبالغ.
4. إذا سأل عن قائمة (وثائق، شروط، إجراءات) فاذكرها كاملة بنقاط قصيرة.
5. انتبه للملاحظات: قد تحتوي على رسوم إضافية أو مهل أو استثناءات تخص السؤال.
6. إذا افترض السائل شيئاً يخالف النصوص، فصحّح له الافتراض بوضوح اعتماداً على النص.
7. إذا سأل عن أكثر من شيء، أجب عن كل جزء.
8. إذا لم تجد الجواب في النصوص، قل: "عذراً، لا تتوفر لدي هذه المعلومة في الوثائق الرسمية." ولا تخمّن.
9. لا تضف أي تفصيل غير مكتوب في النص (لا أماكن ولا شروط ولا أرقام إضافية).
10. ابدأ بجملة كاملة تذكر اسم الخدمة وتجيب مباشرة عن المطلوب فقط (لا تذكر المدة إلا إذا سُئلت عنها).
11. أجب بالعربية الواضحة، بإيجاز ومباشرة، دون مقدمات أو تحيات، ودون ذكر "النصوص" أو "المصدر"."""


_model_cache = {}


def model_name():
    if LLM_MODEL:
        return LLM_MODEL
    if "m" not in _model_cache:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
        chat = [n for n in names if not any(x in n.lower() for x in ("embed", "bge", "nomic", "minilm", "e5"))]
        if not chat:
            raise RuntimeError("no chat model found in Ollama - run: ollama pull <model>")
        _model_cache["m"] = next((n for n in chat if n.split(":")[0] == PREFERRED), chat[0])
    return _model_cache["m"]


def llm(messages):
    body = json.dumps({"model": model_name(), "messages": messages, "stream": False, "keep_alive": "60m",
                       "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT}}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["message"]["content"].strip()


AR_NUM = {"سنه": 1, "سنتين": 2, "شهر": 1, "شهرين": 2, "اسبوع": 1, "اسبوعين": 2, "يوم": 1, "يومين": 2}
WORD_NUM = {"واحد": 1, "ثلاث": 3, "تلات": 3, "اربع": 4, "خمس": 5, "ست": 6, "سبع": 7, "ثمان": 8, "تمن": 8, "تسع": 9, "عشر": 10}


def _num(tok):
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    for k, v in WORD_NUM.items():
        if tok.startswith(k):
            return v
    return None


def situation_facts(question, pieces_text=""):
    """Plain facts about the asker, computed in code because a 7B model compares numbers badly."""
    q = norm(question)
    facts = []
    # ages: "عمري 17", "عمره 12 سنه", "ابني عمره 5 سنين"
    for m in re.finditer(r"عمر\w*\s+(\d+|\w+)", q):
        a = _num(m.group(1))
        if a is None:
            continue
        rel16 = "أقل من 16 سنة" if a < 16 else ("16 سنة بالضبط" if a == 16 else "أكبر من 16 سنة")
        rel18 = "أقل من 18" if a < 18 else "18 أو أكثر"
        facts.append(f"عمر الشخص المذكور {a} سنة: أي {rel16}، و{rel18}.")
    # remaining validity: "باقي عليه 3 شهور", "صالح لسنه", "باقي 100 يوم"
    m = re.search(r"(?:باقي|بايق|متبقي|ضايل|صالح|ساري)\D{0,12}?(\d+|\w+)?\s*(سنه|سنتين|سنين|سنوات|شهرين|شهور|اشهر|شهر|اسابيع|اسبوعين|اسبوع|يومين|ايام|يوم)", q)
    if m:
        unit = m.group(2)
        n = _num(m.group(1) or "") if m.group(1) else None
        n = n if n is not None else AR_NUM.get(unit, 1)
        if unit in ("سنتين", "شهرين", "اسبوعين", "يومين"):
            n = 2
        days = n * (365 if unit.startswith("سن") else 30 if ("شه" in unit or unit == "اشهر") else 7 if "اسب" in unit else 1)
        facts.append(f"المتبقي على صلاحية الوثيقة حوالي {days} يوماً: أي {'أقل من 180 يوماً' if days < 180 else 'أكثر من 180 يوماً'}.")
    elif _has(q, [norm(w) for w in ("منتهي", "منتهيه", "خلص", "خلصت", "انتهى", "انتهت")]):
        facts.append("الوثيقة منتهية الصلاحية.")
    # time since marriage: "تزوجت قبل 4 شهور"
    m = re.search(r"(?:تزوج|اتجوز|تجوز)\w*\s+قبل\s+(\d+|\w+)?\s*(سنه|سنتين|شهرين|شهور|اشهر|شهر|اسابيع|ايام|يوم)", q)
    if m:
        unit = m.group(2); n = _num(m.group(1) or "") or (2 if unit in ("شهرين", "سنتين") else 1)
        days = n * (365 if unit.startswith("سن") else 30 if ("شه" in unit or unit == "اشهر") else 7 if "اسب" in unit else 1)
        facts.append(f"مضى على عقد الزواج حوالي {days} يوماً: أي {'أكثر من 90 يوماً' if days > 90 else 'أقل من 90 يوماً'}.")
    # abroad
    if _has(q, [norm(w) for w in ("برا", "بره", "بالخارج", "خارج الاردن", "خارج البلد", "مغترب", "عايش ب", "ساكن ب", "مقيم ب", "السفاره")]) or \
            re.search(r"(عايش|ساكن|مقيم)\s+ب\w+", q):
        facts.append("السائل خارج الأردن.")
    # military
    if _has(q, [norm(w) for w in ("عسكري", "القوات المسلحه", "الجيش", "جيش", "الامن العام", "الدفاع المدني", "الدرك", "حفظ السلام")]):
        facts.append("السائل من أفراد القوات المسلحة أو الأجهزة الأمنية.")
    # how many times lost (only when the document was lost: "لأول مرة" alone means first issue)
    for w, n in ([] if not _has(q, SIT_WORDS["lost"]) else (("الاولى", 1), ("اول مره", 1), ("الثانيه", 2), ("تاني مره", 2), ("ثاني مره", 2), ("التانيه", 2),
                 ("الثالثه", 3), ("التالته", 3), ("تالت مره", 3), ("ثالث مره", 3))):
        if norm(w) in q:
            facts.append(f"هذه المرة رقم {n} (المرة {'الأولى' if n == 1 else 'الثانية' if n == 2 else 'الثالثة'}).")
            break
    if _has(q, [norm(w) for w in ("مستعجل", "مستعجله", "المستعجله", "بسرعه")]):
        facts.append("السائل يريد الخدمة المستعجلة.")
    return facts


# Each fee line -> the condition it is about (patterns on the normalized line)
FEE_TAGS = {
    "military": [r"القوات المسلحه", r"العسكري", r"الاجهزه الامنيه"],
    "under16": [r"دون (سن )?(السادسه عشر|16)"],
    "over16": [r"فوق (سن )?(السادسه عشر|16)"],
    "full": [r"الممتلي"],
    "abroad": [r"خارج البلاد"],
    "inside": [r"داخل البلاد"],
    "lt180": [r"اقل من \(?180"],
    "gt180": [r"اكثر من \(?180"],
    "loss1": [r"للمره الاولي"],
    "lossN": [r"لاي مره تلي"],
    "fb_expired": [r"(?<!غير )منتهي المده"],
    "fb_valid": [r"غير منتهي المده"],
}
NOT_EXPIRED = [norm(w) for w in ("مش منتهي", "غير منتهي", "مو منتهي", "ما خلص", "ما انتهى", "لسا صالح", "لسا ساري", "ساري المفعول", "مش خالص")]


def person_profile(text):
    """True / False / None (unknown) for every fee condition, from what the user wrote."""
    q = norm(text)
    p = {}
    age = None
    for m in re.finditer(r"عمر\w*\s+(\d+|\w+)", q):
        age = _num(m.group(1)) if _num(m.group(1)) is not None else age
    p["under16"] = None if age is None else age < 16
    p["over16"] = None if age is None else age > 16
    p["military"] = _has(q, [norm(w) for w in ("عسكري", "القوات المسلحه", "الجيش", "جيش", "الامن العام", "الدفاع المدني", "الدرك", "حفظ السلام")])
    p["full"] = _has(q, [norm(w) for w in ("ممتلي", "ممتلئ", "امتلا", "مليان", "الصفحات", "صفحات")])
    p["abroad"] = bool(_has(q, [norm(w) for w in ("برا", "بره", "بالخارج", "خارج الاردن", "خارج البلد", "مغترب")]) or
                       re.search(r"(عايش|ساكن|مقيم)\s+ب\w+", q))
    # "inside" only counts when SAID; otherwise it is unknown (so it can't tie with a stated fact like the age)
    p["inside"] = False if p["abroad"] else (True if _has(q, [norm(w) for w in ("داخل الاردن", "داخل البلد", "بالاردن", "جوا البلد")]) else None)
    days, expired = None, None
    m = re.search(r"(?:باقي|بايق|متبقي|ضايل|صالح|ساري)\D{0,12}?(\d+|\w+)?\s*(سنه|سنتين|سنين|سنوات|شهرين|شهور|اشهر|شهر|اسابيع|اسبوعين|اسبوع|يومين|ايام|يوم)", q)
    if m:
        unit = m.group(2)
        n = (_num(m.group(1)) if m.group(1) else None) or (2 if unit in ("سنتين", "شهرين", "اسبوعين", "يومين") else 1)
        days = n * (365 if unit.startswith("سن") else 30 if ("شه" in unit or unit == "اشهر") else 7 if "اسب" in unit else 1)
    if _has(q, NOT_EXPIRED):
        expired = False
    elif _has(q, [norm(w) for w in ("منتهي", "منتهيه", "خلص", "خلصت", "انتهى", "انتهت", "خالص")]):
        expired = True
    p["lt180"] = True if expired else (None if days is None else days < 180)
    p["gt180"] = False if expired else (None if days is None else days >= 180)
    if expired is False and days is None:
        p["gt180"] = None  # "not expired" alone doesn't tell how long is left
    p["fb_expired"] = expired
    p["fb_valid"] = None if expired is None else not expired
    n = None
    if _has(q, SIT_WORDS["lost"]):
        for w, k in (("الاولى", 1), ("اول مره", 1), ("الثانيه", 2), ("تاني مره", 2), ("ثاني مره", 2), ("التانيه", 2),
                     ("الثالثه", 3), ("التالته", 3), ("تالت مره", 3), ("ثالث مره", 3)):
            if norm(w) in q:
                n = k
                break
    p["loss1"] = None if n is None else n == 1
    p["lossN"] = None if n is None else n >= 2
    return p


def chat_profile(question, earlier_questions):
    """The current message decides; earlier messages of the same chat fill what it doesn't say."""
    cur = person_profile(question)
    if earlier_questions:
        old = person_profile(" ".join(earlier_questions))
        for k, v in cur.items():
            if v is None or (v is False and k in ("military", "full", "abroad") and old.get(k)):
                cur[k] = old[k] if old.get(k) is not None else v
        if cur["abroad"]:
            cur["inside"] = False
    return cur


def filter_fees(fee_text, profile):
    """Keep only the fee line(s) matching the person's situation. Lines without a condition (bonds, fines) are kept.
    If nothing about the person is known, every line is kept so the answer lists the cases."""
    lines = [l for l in fee_text.split("\n") if l.strip()]
    tagged, plain = [], []
    for l in lines:
        ln = norm(l)
        tags = [t for t, pats in FEE_TAGS.items() if any(re.search(p, ln) for p in pats)]
        (tagged if tags else plain).append((l, tags))
    if len(tagged) < 2:
        return fee_text
    scored = []
    for l, tags in tagged:
        vals = [profile.get(t) for t in tags]
        if any(v is False for v in vals):
            continue
        scored.append((sum(1 for v in vals if v), l))
    best = max((sc for sc, _ in scored), default=0)
    if best == 0:
        return fee_text
    keep = [l for sc, l in scored if sc == best]
    return "\n".join(keep + [l for l, _ in plain])


def generate(question, pieces, history):
    ctx = "\n\n".join(f"[{i+1}] {p}" for i, p in enumerate(pieces))
    msgs = [{"role": "system", "content": SYSTEM}]
    for h in history[-2:]:  # last exchange(s) of THIS chat only, so follow-ups read naturally
        msgs += [{"role": "user", "content": h["q"]}, {"role": "assistant", "content": h["a"]}]
    facts = situation_facts(question, "\n".join(pieces)) if any(("الرسوم" in p or "شروط" in p) for p in pieces) else []
    ftxt = ("\n\nحقائق عن حالة السائل (محسوبة من سؤاله):\n- " + "\n- ".join(facts)) if facts else ""
    msgs.append({"role": "user", "content": f"النصوص الرسمية:\n{ctx}{ftxt}\n\nسؤال المواطن: {question}"})
    return strip_totals(llm(msgs))


def strip_totals(text):
    """The documents never give totals and a 7B model adds badly: drop any line that sums amounts."""
    bad = [norm(w) for w in ("اجمالي", "الاجمالي", "المجموع", "مجموع", "المبلغ الكلي", "بالمجمل", "في المجموع")]
    keep = [l for l in text.split("\n") if not any(b in norm(l) for b in bad)]
    return "\n".join(keep).strip() or text


def fee_list_answer(question, r, pieces, db):
    """Only fees were asked, for one service whose fee has several cases, and the person gave no detail that
    picks one: answer with the fee lines copied exactly (a 7B model invents conditions when it summarises them)."""
    keys = [k for k in r.get("services", []) if k in db]
    if len(keys) != 1 or set(r.get("fields") or []) - {"fees", "notes"} or "fees" not in (r.get("fields") or []):
        return None
    s = db[keys[0]]
    fee_piece = next((p for p in pieces if p.startswith(s["title"] + " - " + FIELD_LABEL["fees"])), None)
    if not fee_piece:
        return None
    lines = [l.strip() for l in fee_piece.split(": ", 1)[1].split("\n") if l.strip()]
    if len(lines) < 3:
        return None  # one clear amount: let the model write a normal sentence
    cases = sum(1 for l in lines if any(re.search(p, norm(l)) for pats in FEE_TAGS.values() for p in pats))
    head = f"تختلف رسوم {s['title']} حسب الحالة:" if cases >= 2 else f"رسوم {s['title']}:"
    out = head + "\n" + "\n".join(f"- {l}" for l in lines)
    extra = [l.strip("- ").strip() for l in s["fields"].get("notes", "").split("\n") if "دينار" in l or "دنانير" in l]
    if extra:
        out += "\n\nملاحظة:\n" + "\n".join(f"- {l}" for l in extra)
    return out


# ------------------------------------------------------------------ 6. One chat = one memory
class Chat:
    def __init__(self, services_db):
        self.db = services_db
        self.memory = {"services": [], "fields": [], "sits": {}}
        self.history = []

    def ask(self, question):
        """Returns (answer, contexts, debug_route)."""
        r = route(question, self.memory)
        if r["action"] in ("decline", "clarify"):
            ans, ctx = r["message"], []
        else:
            r["profile"] = chat_profile(question, [h["q"] for h in self.history])
            pieces, clar = select(question, r, self.db)
            if clar:
                ans, ctx = clar, []
            else:
                listed = fee_list_answer(question, r, pieces, self.db)
                try:
                    ans = listed or generate(question, pieces, self.history)
                except Exception as e:  # Ollama down / timeout: fall back to the exact text (still grounded)
                    print(f"   !! model error: {e} -> extractive answer")
                    ans = "\n".join(p.split(": ", 1)[-1] for p in pieces)
                ctx = pieces
                self.memory["services"] = [k for k in r["services"] if k in self.db] or self.memory["services"]
                self.memory["fields"] = r["fields"] or self.memory["fields"]
                for k in self.memory["services"]:
                    d = next(x for x in DOC_NAMES if k.startswith(x))
                    self.memory["sits"][d] = [k[len(d) + 1:]]
        self.history.append({"q": question, "a": ans})
        return ans, ctx, r
