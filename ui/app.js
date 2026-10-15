/* Nashmi UI: plain JavaScript port of the design, talking to server.py (/api/chat). Works fully offline. */
(function () {
  "use strict";

  // ------------------------------------------------------------------ content
  var ICONS = {
    passport: '<rect x="5" y="3.5" width="14" height="17" rx="2"/><circle cx="12" cy="10" r="3"/><path d="M9 10h6M12 7v6M8.5 16.5h7"/>',
    book: '<path d="M5 4.5h10a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3v-12Z"/><path d="M8 4.5v15M11 9h4M11 13h4"/>',
    card: '<rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="8.5" cy="11" r="2.2"/><path d="M13 10h5M13 14h4M6 16h5"/>',
    shield: '<path d="M12 3 5 6v5c0 4.4 2.8 8.4 7 10 4.2-1.6 7-5.6 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/>',
    shieldPlain: '<path d="M12 3 5 6v5c0 4.4 2.8 8.4 7 10 4.2-1.6 7-5.6 7-10V6l-7-3Z"/>',
    chat: '<path d="M20 11.5a7.5 7.5 0 0 1-8 7.5 8.8 8.8 0 0 1-3.5-.7L4 20l1.5-4A7.2 7.2 0 0 1 4 11.5 7.5 7.5 0 0 1 12 4a7.5 7.5 0 0 1 8 7.5Z"/>',
    lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.3 2.3 0 1 1 3.1 2.2c-.7.3-.9.8-.9 1.5"/><circle cx="12" cy="16.6" r=".8" fill="currentColor"/>',
    arrow: '<path d="m14 6-6 6 6 6"/>',
    send: '<path d="m5 12 14-7-4 14-3.2-5.8L5 12Z"/><path d="m11.8 13.2 3.3-3.3"/>',
    doc: '<path d="M7 3h8l3 3v15H7V3Z"/><path d="M10 11h5M10 15h5M14 3v4h4"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
  };
  function icon(name, size) {
    size = size || 20;
    return '<svg aria-hidden="true" fill="none" height="' + size + '" width="' + size + '" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" viewBox="0 0 24 24">' + ICONS[name] + "</svg>";
  }

  var SERVICES = [
    { title: "جواز السفر", description: "إصدار، تجديد، بدل فاقد أو تالف", example: "عمري 17 وجوازي بايق عليه 3 شهور، كم رسوم التجديد؟", tone: "green", icon: "passport" },
    { title: "دفتر العائلة", description: "إصدار، تجديد، بدل فاقد أو تالف", example: "شو الأوراق المطلوبة لتجديد دفتر العائلة؟", tone: "red", icon: "book" },
    { title: "البطاقة الذكية", description: "إصدار، تجديد، بدل فاقد أو تالف", example: "ضاعت هويتي، قديش الرسوم؟", tone: "black", icon: "card" },
  ];
  var TRUST = [
    { title: "إجابة موثّقة", description: "كل معلومة من نص رسمي تقدر تشوفه", icon: "shield" },
    { title: "يفهم لهجتك", description: "اسأل بالفصحى أو باللهجة الأردنية", icon: "chat" },
    { title: "خصوصية أولًا", description: "يعمل على جهازك بدون إنترنت", icon: "lock" },
  ];
  var WELCOME = "أهلًا بك. اسألني عن جواز السفر أو دفتر العائلة أو البطاقة الذكية، وسأجيبك من الوثائق الرسمية فقط.";
  var FOLLOW = { fees: "وكم الرسوم؟", documents: "شو الأوراق المطلوبة؟", places: "وين بقدر أقدّم؟", time: "كم بتاخد المعاملة؟", conditions: "شو الشروط؟" };

  // ------------------------------------------------------------------ state
  function newConv() {
    var id = "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    return { id: id, title: "محادثة جديدة", messages: [{ role: "assistant", text: WELCOME }] };
  }
  var state = { convs: [newConv()], activeId: null, typing: false, sidebar: false, help: false, draft: "", status: "loading" };
  state.activeId = state.convs[0].id;
  function active() {
    for (var i = 0; i < state.convs.length; i++) if (state.convs[i].id === state.activeId) return state.convs[i];
    return state.convs[0];
  }

  // ------------------------------------------------------------------ helpers
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function cleanAnswer(t) { return String(t || "").replace(/\*\*(.+?)\*\*/g, "$1"); }

  // ------------------------------------------------------------------ render
  function renderMessage(m, i, conv) {
    if (m.role === "user") {
      return '<div class="message-row user-row"><div class="message user-message"><p>' + esc(m.text) + "</p></div></div>";
    }
    var h = '<div class="message-row"><img src="nashami.jpeg" alt="" class="message-avatar"/><div class="message assistant-message">';
    h += '<p class="' + (m.error ? "error-text" : "") + '">' + esc(cleanAnswer(m.text)) + "</p>";
    if (m.source) {
      h += '<span class="source-label">' + icon("doc", 14) + esc(m.source) + "</span>";
    }
    if (m.contexts && m.contexts.length) {
      h += '<details class="rag-box"><summary>النصوص الرسمية اللي اعتمد عليها الجواب (' + m.contexts.length + ")</summary>";
      if (m.route) h += '<div class="rag-route">' + esc(m.route) + "</div>";
      m.contexts.forEach(function (c) {
        var k = c.indexOf(": ");
        h += '<div class="rag-piece">' + (k > 0 ? "<b>" + esc(c.slice(0, k)) + "</b>: " + esc(c.slice(k + 2)) : esc(c)) + "</div>";
      });
      h += "</details>";
    }
    var isLast = i === conv.messages.length - 1;
    if (m.suggestions && m.suggestions.length && isLast) {
      h += '<div class="follow-ups">' + m.suggestions.map(function (s) {
        return '<button type="button" data-ask="' + esc(s) + '">' + esc(s) + "</button>";
      }).join("") + "</div>";
    }
    return h + "</div></div>";
  }

  function render() {
    var conv = active();
    var started = conv.messages.some(function (m) { return m.role === "user"; });
    var statusText = state.status === "ready" ? "جاهز · يعمل على جهازك من الوثائق الرسمية" :
      state.status === "loading" ? "عم يجهّز النموذج… أول مرة بتاخد دقيقة" : "النموذج مش شغّال · تأكد إن Ollama شغّال";
    var dotClass = state.status === "ready" ? "" : state.status === "loading" ? " is-loading" : " is-offline";

    var h = '<div class="app-shell" dir="rtl">';
    h += '<div aria-hidden="true" class="sidebar-backdrop' + (state.sidebar ? " is-visible" : "") + '" data-act="close-sidebar"></div>';
    h += '<aside class="sidebar' + (state.sidebar ? " is-open" : "") + '">';
    h += '<div class="brand"><div class="brand-mark"><img src="nashami.jpeg" alt=""/></div><div><h1>نشمي</h1><p>دليلك لمعاملات الأحوال المدنية والجوازات</p></div></div>';
    h += '<button class="new-chat" data-act="new">' + icon("plus", 19) + "<span>محادثة جديدة</span></button>";
    h += '<nav class="chat-history" aria-label="سجل المحادثات"><span class="section-label">المحادثات</span>';
    state.convs.forEach(function (c) {
      h += '<button class="history-item' + (c.id === state.activeId ? " active" : "") + '" data-conv="' + c.id + '">' + icon("chat", 18) + "<span>" + esc(c.title) + "</span></button>";
    });
    h += "</nav>";
    h += '<div class="scope-card">' + icon("shield", 18) + "<span><strong>مصادر رسمية فقط</strong><small>كل إجابة معها النص اللي اعتمدت عليه</small></span></div>";
    h += "</aside>";

    h += '<main class="main-content">';
    h += '<header class="topbar"><button aria-label="فتح القائمة" class="menu-button" data-act="open-sidebar">' + icon("menu", 22) + "</button>";
    h += '<div class="topbar-title"><span class="status-dot' + dotClass + '"></span><span>' + statusText + "</span></div>";
    h += '<button class="help-button" aria-label="المساعدة" data-act="help">' + icon("help", 20) + "</button></header>";

    h += '<section class="conversation" aria-live="polite" id="conversation">';
    if (!started) {
      h += '<div class="welcome"><div class="hero-row"><div class="hero-avatar"><div class="avatar-glow"></div><img src="nashami.jpeg" alt="نشمي، المساعد الذكي"/><span class="online-badge"></span></div>';
      h += '<div class="welcome-copy"><span class="eyebrow">دليل المواطن · الأحوال المدنية والجوازات</span><h2>أهلًا بك، أنا نشمي</h2>';
      h += "<p>اسألني عن رسوم معاملتك، الأوراق اللي لازم تجيبها، الشروط، وين تقدّم وقديش بتاخد. بجاوبك من ملفات الخدمات الرسمية فقط، وبسألك إذا احتجت توضيح.</p></div></div>";
      h += '<div class="trust-grid">' + TRUST.map(function (t) {
        return '<div class="trust-item"><span>' + icon(t.icon, 18) + "</span><div><strong>" + t.title + "</strong><small>" + t.description + "</small></div></div>";
      }).join("") + "</div>";
      h += '<div class="situation-list" aria-label="الحالات المدعومة"><span>إصدار لأول مرة</span><span>تجديد</span><span>بدل فاقد</span><span>بدل تالف</span></div>';
      h += '<div class="prompt-grid">' + SERVICES.map(function (s, i) {
        return '<button class="prompt-card ' + s.tone + '" data-example="' + i + '"><span class="prompt-icon">' + icon(s.icon) + "</span><span><strong>" + s.title + "</strong><small>" + s.description + '</small></span><span class="prompt-arrow">' + icon("arrow", 18) + "</span></button>";
      }).join("") + "</div></div>";
    } else {
      h += '<div class="messages">' + conv.messages.map(function (m, i) { return renderMessage(m, i, conv); }).join("");
      if (state.typing) {
        h += '<div class="message-row"><img src="nashami.jpeg" alt="" class="message-avatar"/><div class="typing" aria-label="نشمي يكتب"><span></span><span></span><span></span></div></div>';
      }
      h += '<div id="end"></div></div>';
    }
    h += "</section>";

    h += '<div class="composer-wrap"><form class="composer" id="composer"><input id="message-input" autocomplete="off" placeholder="مثال: الباسبور خلص، قديش التجديد؟" value="' + esc(state.draft) + '"/>';
    h += '<button aria-label="إرسال الرسالة" class="send-button" id="send" type="submit"' + (!state.draft.trim() || state.typing ? " disabled" : "") + ">" + icon("send", 21) + "</button></form>";
    h += '<p class="disclaimer">لا تشارك رقمك الوطني أو بياناتك الشخصية. نشمي بجاوب من وثائق الخدمات الرسمية فقط، وإذا ما لقي المعلومة بحكيلك.</p></div>';
    h += "</main>";

    if (state.help) {
      h += '<div class="modal-backdrop" role="presentation" data-act="close-help"><section aria-labelledby="help-title" aria-modal="true" class="help-modal" role="dialog">';
      h += '<button aria-label="إغلاق" class="modal-close" data-act="close-help">' + icon("close", 20) + "</button>";
      h += '<span class="modal-icon">' + icon("shieldPlain", 24) + '</span><h2 id="help-title">كيف تستخدم نشمي؟</h2>';
      h += "<p>اذكر الوثيقة والحالة، ثم اسأل عن الرسوم أو الشروط أو الأوراق أو مكان التقديم. إذا رسومك بتعتمد على عمرك أو صلاحية وثيقتك، احكيها بالسؤال. مثال: «عمري 17 وجوازي بايق عليه 3 شهور، كم رسوم التجديد؟»</p>";
      h += '<div class="help-scope"><strong>النطاق المتاح</strong><span>جواز السفر · دفتر العائلة · البطاقة الذكية</span></div></section></div>';
    }
    h += "</div>";

    var hadFocus = document.activeElement && document.activeElement.id === "message-input";
    document.getElementById("root").innerHTML = h;
    var input = document.getElementById("message-input");
    if (hadFocus || !state.typing) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
    var end = document.getElementById("end");
    if (end) end.scrollIntoView({ behavior: "smooth" });
  }

  // ------------------------------------------------------------------ chat
  function send(text) {
    var q = (text || "").trim();
    if (!q || state.typing) return;
    var conv = active();
    if (conv.title === "محادثة جديدة") conv.title = q.slice(0, 32);
    conv.messages.push({ role: "user", text: q });
    state.draft = "";
    state.typing = true;
    render();

    fetch("api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conv.id, message: q }),
    })
      .then(function (res) { return res.text(); })
      .then(function (body) {
        var reply = { role: "assistant", text: "" }, meta = null;
        body.split("\n").forEach(function (line) {
          if (!line.trim()) return;
          var evt; try { evt = JSON.parse(line); } catch (e) { return; }
          if (evt.type === "meta") meta = evt;
          else if (evt.type === "token") reply.text += evt.text;
          else if (evt.type === "error") { reply.text = evt.message; reply.error = true; }
        });
        if (meta) {
          var r = meta.route || {};
          reply.contexts = meta.contexts || [];
          reply.route = meta.route_label || "";
          if (reply.contexts.length) reply.source = meta.sources_short || "";
          if ((r.action === "clarify" && !r.greet) || r.clarified) {
            reply.suggestions = r.missing === "document" ? ["جواز السفر", "دفتر العائلة", "البطاقة الذكية"] : ["لأول مرة", "تجديد", "بدل فاقد", "بدل تالف"];
          } else if (r.action === "answer" && (r.services || []).length) {
            var asked = r.fields || [];
            reply.suggestions = Object.keys(FOLLOW).filter(function (f) { return asked.indexOf(f) < 0; }).slice(0, 3).map(function (f) { return FOLLOW[f]; });
          }
        }
        if (!reply.text) { reply.text = "ما وصل رد. جرّب كمان مرة."; reply.error = true; }
        conv.messages.push(reply);
      })
      .catch(function () {
        conv.messages.push({ role: "assistant", text: "مش قادر أوصل للخادم. تأكد إن python server.py شغّال.", error: true });
      })
      .then(function () { state.typing = false; render(); });
  }

  function pollStatus() {
    fetch("api/status").then(function (r) { return r.json(); }).then(function (s) {
      var before = state.status;
      state.status = s.model === "ready" ? "ready" : s.model === "loading" ? "loading" : "offline";
      if (before !== state.status && !state.typing) render();
      setTimeout(pollStatus, state.status === "ready" ? 30000 : 4000);
    }).catch(function () {
      state.status = "offline"; render(); setTimeout(pollStatus, 5000);
    });
  }

  // ------------------------------------------------------------------ events (delegated, so re-rendering is safe)
  document.addEventListener("click", function (e) {
    var t = e.target.closest("[data-act],[data-conv],[data-example],[data-ask]");
    if (!t) return;
    if (t.hasAttribute("data-ask")) return send(t.getAttribute("data-ask"));
    if (t.hasAttribute("data-example")) { state.draft = SERVICES[+t.getAttribute("data-example")].example; return render(); }
    if (t.hasAttribute("data-conv")) { if (!state.typing) { state.activeId = t.getAttribute("data-conv"); state.sidebar = false; render(); } return; }
    var act = t.getAttribute("data-act");
    if (act === "new" && !state.typing) { var c = newConv(); state.convs.unshift(c); state.activeId = c.id; state.sidebar = false; state.draft = ""; render(); }
    else if (act === "open-sidebar") { state.sidebar = true; render(); }
    else if (act === "close-sidebar") { state.sidebar = false; render(); }
    else if (act === "help") { state.help = true; render(); }
    else if (act === "close-help" && (e.target === t || t.classList.contains("modal-close"))) { state.help = false; render(); }
  });
  document.addEventListener("input", function (e) {
    if (e.target.id !== "message-input") return;
    state.draft = e.target.value;
    var b = document.getElementById("send");
    if (b) b.disabled = !state.draft.trim() || state.typing;
  });
  document.addEventListener("submit", function (e) {
    if (e.target.id !== "composer") return;
    e.preventDefault();
    send(state.draft);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && state.help) { state.help = false; render(); } });

  render();
  pollStatus();
})();
