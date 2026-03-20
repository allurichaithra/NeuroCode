"""
╔══════════════════════════════════════════════════════════════════╗
║  AI CODING MENTOR — 5-AGENT PIPELINE  v3.0                     ║
║  Agents: Analyzer · Memory · Fixer · Mentor · Roadmap          ║
║  Stack : Groq (llama-3.3-70b) + Hindsight (vector memory)      ║
╚══════════════════════════════════════════════════════════════════╝
"""
import os, re, json
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, send_from_directory
from groq import Groq

# ── ENV LOADER ────────────────────────────────────────────────────
def _load_env(path=".env"):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] in ('"', "'") and val[-1] == val[0]:
                val = val[1:-1]
            if val:
                os.environ[key] = val

_load_env()

# ── CONFIG ────────────────────────────────────────────────────────
app            = Flask(__name__, static_folder=".")
GROQ_MODEL     = "llama-3.3-70b-versatile"
HINDSIGHT_BASE = "https://api.hindsight.vectorize.io/v1"

# ── GROQ HELPER ───────────────────────────────────────────────────
def _chat(system, user, max_tokens=1600, temp=0.55):
    client = Groq(api_key=os.environ.get("GROQ_API_KEY", "").strip())
    r = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=max_tokens,
        temperature=temp,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return r.choices[0].message.content, r.usage.total_tokens

# ══════════════════════════════════════════════════════════════════
# HINDSIGHT MEMORY
# ══════════════════════════════════════════════════════════════════
def _hs_key():
    return os.environ.get("HINDSIGHT_API_KEY", "").strip()

def _hs_ready():
    k = _hs_key()
    return bool(k and k not in ("", "paste_your_hindsight_api_key_here"))

def _hs_org():
    parts = _hs_key().split("_")
    return parts[1] if len(parts) >= 3 and parts[0] == "hsk" else "default"

def _hs_hdr():
    return {"Authorization": f"Bearer {_hs_key()}", "Content-Type": "application/json"}

def hindsight_retain(bank_id, content):
    if not _hs_ready():
        _fb_retain(bank_id, content)
        return False
    import requests as http
    try:
        url = f"{HINDSIGHT_BASE}/default/banks/{bank_id}/memories"
        r = http.post(url, headers=_hs_hdr(), json={"items": [{"content": content}]}, timeout=15)
        if r.status_code in (200, 201):
            print(f"  [HS] retained '{content[:55]}'")
            return True
        print(f"  [HS] retain failed {r.status_code}: {r.text[:100]}")
        _fb_retain(bank_id, content)
        return False
    except Exception as e:
        print(f"  [HS] retain error: {e}")
        _fb_retain(bank_id, content)
        return False

def hindsight_recall(bank_id, query, top_k=6):
    if not _hs_ready():
        return _fb_recall(bank_id)
    import requests as http
    try:
        url = f"{HINDSIGHT_BASE}/default/banks/{bank_id}/memories/recall"
        r = http.post(url, headers=_hs_hdr(), json={"query": query}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            items = data.get("results", data.get("memories", []))
            out = [
                (i.get("text") or i.get("content") or "").strip()[:300]
                for i in items
                if (i.get("text") or i.get("content") or "").strip()
            ]
            print(f"  [HS] recalled {len(out)} from '{bank_id}'")
            return out[:top_k]
        if r.status_code == 404:
            print(f"  [HS] bank '{bank_id}' not found — first session")
            return []
        print(f"  [HS] recall failed {r.status_code}")
        return _fb_recall(bank_id)
    except Exception as e:
        print(f"  [HS] recall error: {e}")
        return _fb_recall(bank_id)

def hindsight_delete(bank_id):
    if not _hs_ready():
        return False
    import requests as http
    try:
        url = f"{HINDSIGHT_BASE}/default/banks/{bank_id}/memories"
        r = http.delete(url, headers=_hs_hdr(), timeout=15)
        if r.status_code == 200:
            print(f"  [HS] cleared memories for '{bank_id}'")
            return True
        print(f"  [HS] clear failed {r.status_code}")
        return False
    except Exception as e:
        print(f"  [HS] clear error: {e}")
        return False

# ══════════════════════════════════════════════════════════════════
# FALLBACK DISK MEMORY
# ══════════════════════════════════════════════════════════════════
_FB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fallback_memory.json")

def _fb_load():
    if os.path.exists(_FB_PATH):
        try:
            with open(_FB_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _fb_save(d):
    try:
        with open(_FB_PATH, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

_fb = _fb_load()

def _fb_retain(bid, m):
    _fb.setdefault(bid, [])
    if m not in _fb[bid]:
        _fb[bid].append(m)
        _fb_save(_fb)
        print(f"  [FB] stored '{m[:55]}'")

def _fb_recall(bid):
    mems = _fb.get(bid, [])
    print(f"  [FB] recalled {len(mems)} from '{bid}'")
    return mems

# ══════════════════════════════════════════════════════════════════
# STUDENT PROFILE STORE (disk JSON)
# ══════════════════════════════════════════════════════════════════
_PROFILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json")

def _profiles_load():
    if os.path.exists(_PROFILES_PATH):
        try:
            with open(_PROFILES_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _profiles_save(d):
    try:
        with open(_PROFILES_PATH, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass

_profiles = _profiles_load()

# ── XP / Level system ────────────────────────────────────────────
LEVELS = [
    (0,    "🌱", "Seedling"),
    (100,  "🐛", "Debugger"),
    (300,  "⚙️",  "Builder"),
    (600,  "🔥", "Hacker"),
    (1000, "💡", "Engineer"),
    (1800, "🚀", "Architect"),
    (3000, "🧠", "Wizard"),
]

BADGES = {
    "first_blood":   ("🩸", "First Blood",   "Submitted your first code"),
    "streak_3":      ("🔥", "On Fire",       "3-day coding streak"),
    "streak_7":      ("⚡", "Week Warrior",  "7-day coding streak"),
    "no_repeats_5":  ("🎯", "Clean Coder",   "5 sessions with no repeated mistakes"),
    "10_sessions":   ("💎", "Dedicated",     "Completed 10 sessions"),
    "polyglot":      ("🌍", "Polyglot",      "Used 3+ different languages"),
    "fast_learner":  ("📈", "Fast Learner",  "Zero critical issues in a session"),
    "bug_slayer":    ("🐛", "Bug Slayer",    "Fixed 20+ total issues"),
}

def _level_info(xp):
    level_idx = 0
    for i, (threshold, _, _) in enumerate(LEVELS):
        if xp >= threshold:
            level_idx = i
    icon, name = LEVELS[level_idx][1], LEVELS[level_idx][2]
    next_threshold = LEVELS[level_idx + 1][0] if level_idx + 1 < len(LEVELS) else None
    prev_threshold = LEVELS[level_idx][0]
    if next_threshold:
        span = next_threshold - prev_threshold
        progress = min(100, int(((xp - prev_threshold) / span) * 100))
        xp_to_next = next_threshold - xp
    else:
        progress, xp_to_next = 100, 0
    return {
        "level_icon": icon,
        "level_name": name,
        "level_idx":  level_idx,
        "progress_pct": progress,
        "xp_to_next": xp_to_next,
    }

def _compute_xp(issue_count, repeat_count, is_first):
    base = 20
    bonus = max(0, 10 - issue_count)          # reward fewer bugs
    repeat_penalty = repeat_count * 3
    first_bonus = 10 if is_first else 0
    return max(5, base + bonus - repeat_penalty + first_bonus)

def _get_profile(uid):
    return _profiles.get(uid, {
        "user_id": uid,
        "username": uid,
        "xp": 0,
        "streak_days": 0,
        "last_date": None,
        "total_submissions": 0,
        "total_issues_fixed": 0,
        "badges": [],
        "history": [],
        "langs_used": [],
    })

def _update_profile(uid, username, lang, score, issue_count, repeat_count, mistakes):
    p = _get_profile(uid)
    p["user_id"]  = uid
    p["username"] = username or p.get("username", uid)

    # Streak
    today_str = date.today().isoformat()
    last      = p.get("last_date")
    if last == today_str:
        pass  # same day, no change
    elif last == (date.today() - timedelta(days=1)).isoformat():
        p["streak_days"] = p.get("streak_days", 0) + 1
    else:
        p["streak_days"] = 1
    p["last_date"] = today_str

    # XP
    is_first = p.get("total_submissions", 0) == 0
    xp_earned = _compute_xp(issue_count, repeat_count, is_first)
    old_level  = _level_info(p.get("xp", 0))["level_idx"]
    p["xp"]    = p.get("xp", 0) + xp_earned
    new_level  = _level_info(p["xp"])["level_idx"]
    leveled_up = new_level > old_level

    p["total_submissions"]  = p.get("total_submissions", 0) + 1
    p["total_issues_fixed"] = p.get("total_issues_fixed", 0) + issue_count

    # Language tracking
    langs = p.get("langs_used", [])
    if lang not in langs:
        langs.append(lang)
    p["langs_used"] = langs

    # History entry
    entry = {
        "date":     today_str,
        "lang":     lang,
        "score":    score,
        "mistakes": len(mistakes),
        "issues":   issue_count,
    }
    history = p.get("history", [])
    history.append(entry)
    p["history"] = history[-20:]  # keep last 20

    # Badges
    existing_badges = set(p.get("badges", []))
    earned = []
    if p["total_submissions"] == 1:
        earned.append("first_blood")
    if p["streak_days"] >= 7:
        earned.append("streak_7")
    elif p["streak_days"] >= 3:
        earned.append("streak_3")
    if len(langs) >= 3:
        earned.append("polyglot")
    if p["total_submissions"] >= 10:
        earned.append("10_sessions")
    if issue_count == 0:
        earned.append("fast_learner")
    if p["total_issues_fixed"] >= 20:
        earned.append("bug_slayer")
    for b in earned:
        if b not in existing_badges:
            existing_badges.add(b)
    # No-repeat streak
    recent = p["history"][-5:] if len(p["history"]) >= 5 else []
    if len(recent) >= 5 and all(h.get("mistakes", 1) == 0 for h in recent):
        existing_badges.add("no_repeats_5")

    p["badges"] = list(existing_badges)

    _profiles[uid] = p
    _profiles_save(_profiles)

    return {
        "xp_earned":         xp_earned,
        "total_xp":          p["xp"],
        "streak_days":       p["streak_days"],
        "total_submissions": p["total_submissions"],
        "badges":            [f"{BADGES[b][0]} {BADGES[b][1]}" for b in p["badges"] if b in BADGES],
        "history":           p["history"],
        "level_info":        _level_info(p["xp"]),
        "leveled_up":        leveled_up,
    }

# ══════════════════════════════════════════════════════════════════
# XML HELPERS
# ══════════════════════════════════════════════════════════════════
def _tag(text, tag):
    m = re.search(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""

def _tags(text, tag):
    return [m.strip() for m in re.findall(rf"<{tag}>([\s\S]*?)</{tag}>", text, re.IGNORECASE) if m.strip()]

def _safe_int(s, default=0):
    try:
        return int(re.sub(r"[^\d-]", "", str(s)) or default)
    except Exception:
        return default

# ══════════════════════════════════════════════════════════════════
# AGENT 1 — CODE ANALYZER
# ══════════════════════════════════════════════════════════════════
def agent_analyzer(problem, code, lang):
    print("  [1/5] Analyzer running...")
    sys = (
        "You are a ruthlessly precise code analysis engine. "
        "Find EVERY defect: syntax errors, logic bugs, off-by-one, null refs, "
        "bad naming, inefficiencies, security smells. Never skip issues. "
        "Be terse and exact — no padding."
    )
    usr = f"""Language: {lang}
Problem: {problem}
Code:
```
{code}
```
Respond ONLY in this XML (no extra text):
<analysis>
  <summary>One sentence: what does this code attempt and is the approach sound?</summary>
  <score>Integer 0-100 representing overall code quality</score>
  <topics>comma-separated list of CS topics this code touches e.g. arrays,loops,recursion</topics>
  <issues>
    <issue severity="critical|warning|suggestion">
      <line>line number or "general"</line>
      <type>SyntaxError|LogicError|OffByOne|NullRef|BadPractice|Performance|Security|Style</type>
      <description>Precise one-sentence description</description>
      <fix>How to fix it in plain English</fix>
    </issue>
  </issues>
  <positives>
    <positive>Something genuinely correct (max 3)</positive>
  </positives>
</analysis>"""
    text, tokens = _chat(sys, usr, max_tokens=1400)
    issues = []
    for m in re.finditer(r"<issue severity=['\"](\w+)['\"]>([\s\S]*?)</issue>", text, re.IGNORECASE):
        sev, body = m.group(1), m.group(2)
        issues.append({
            "severity":    sev,
            "line":        _tag(body, "line") or "general",
            "type":        _tag(body, "type") or "Issue",
            "description": _tag(body, "description"),
            "fix":         _tag(body, "fix"),
        })
    score_raw = _tag(text, "score")
    score     = max(0, min(100, _safe_int(score_raw, 50)))
    topics_raw = _tag(text, "topics")
    topics = [t.strip() for t in topics_raw.split(",") if t.strip()] if topics_raw else []
    return {
        "summary":   _tag(text, "summary"),
        "score":     score,
        "topics":    topics,
        "issues":    issues,
        "positives": _tags(text, "positive"),
        "tokens":    tokens,
    }

# ══════════════════════════════════════════════════════════════════
# AGENT 2 — MEMORY AGENT (Hindsight recall + pattern detection)
# ══════════════════════════════════════════════════════════════════
def agent_memory(bank_id, problem, code, current_issues):
    print("  [2/5] Memory Agent (Hindsight recall)...")
    query = f"coding mistakes related to: {problem}. Code snippet: {code[:300]}"
    past  = hindsight_recall(bank_id, query)

    if not past or not current_issues:
        return {"past_memories": past, "repeats": [], "patterns": "", "tokens": 0}

    sys = (
        "You are a pattern-recognition memory agent. "
        "Given past mistakes and current issues, find exact repeating patterns. "
        "Be strict — only flag genuine repeats, not superficial similarities."
    )
    past_str = "\n".join(f"  {i+1}. {m}" for i, m in enumerate(past))
    curr_str = "\n".join(f"  - [{x['type']}] {x['description']}" for x in current_issues)
    usr = f"""PAST MISTAKES (from memory):
{past_str}

CURRENT ISSUES (this session):
{curr_str}

Respond ONLY in this XML:
<memory_analysis>
  <repeats>
    <repeat>
      <past_mistake>Quote the past mistake recurring</past_mistake>
      <current_issue>Quote the matching current issue</current_issue>
      <pattern>One sentence on the repeating pattern</pattern>
    </repeat>
  </repeats>
  <overall_pattern>One sentence on student's overall weakness, or 'No clear pattern yet.'</overall_pattern>
</memory_analysis>"""
    text, tokens = _chat(sys, usr, max_tokens=700, temp=0.3)
    repeats = []
    for m in re.finditer(r"<repeat>([\s\S]*?)</repeat>", text, re.IGNORECASE):
        b = m.group(1)
        repeats.append({
            "past":    _tag(b, "past_mistake"),
            "current": _tag(b, "current_issue"),
            "pattern": _tag(b, "pattern"),
        })
    return {
        "past_memories": past,
        "repeats":       repeats,
        "patterns":      _tag(text, "overall_pattern"),
        "tokens":        tokens,
    }

# ══════════════════════════════════════════════════════════════════
# AGENT 3 — CODE FIXER
# ══════════════════════════════════════════════════════════════════
def agent_fix(problem, code, lang, issues):
    print("  [3/5] Code Fixer running...")
    issue_sum = "\n".join(
        f"  - [{x['type']}] Line {x['line']}: {x['description']} → {x['fix']}"
        for x in issues
    ) or "  No critical issues — refine for best practices."

    sys = (
        "You are an expert code fixer and teacher. "
        "Write the corrected, clean version. "
        "Add a brief comment on EVERY changed line explaining WHY. "
        "Mistakes must be short labels (under 10 words each) for memory storage."
    )
    usr = f"""Language: {lang}
Problem: {problem}
Original code:
```{lang}
{code}
```
Issues to fix:
{issue_sum}

Respond ONLY in this XML:
<fix>
  <explanation>2-3 sentences summarising what you changed and why</explanation>
  <code>
```{lang}
[complete fixed code with inline comments on changed lines]
```
  </code>
  <mistakes>
    <mistake>Short label: e.g. OffByOne: range(len+1) instead of range(len)</mistake>
    <mistake>LogicError: forgot to handle empty list</mistake>
  </mistakes>
</fix>"""
    text, tokens = _chat(sys, usr, max_tokens=1600, temp=0.4)
    code_block = _tag(text, "code")
    code_clean = re.sub(r"^```[\w]*\n?", "", code_block).rstrip("`").strip()
    mistakes   = _tags(text, "mistake")
    return {
        "explanation": _tag(text, "explanation"),
        "fixed_code":  code_clean,
        "mistakes":    mistakes,
        "tokens":      tokens,
    }

# ══════════════════════════════════════════════════════════════════
# AGENT 4 — MENTOR / MOTIVATOR
# ══════════════════════════════════════════════════════════════════
def agent_mentor(username, problem, issues, repeats, overall_pattern, level_name, is_first):
    print("  [4/5] Mentor Agent running...")
    repeat_str  = "\n".join(f"  - {r['pattern']}" for r in repeats) or "  None"
    issue_types = list({i["type"] for i in issues})

    sys = (
        "You are a warm, direct coding mentor — like a senior dev who genuinely cares. "
        "Be personal, specific, honest. No generic fluff. "
        "If there are repeat mistakes, call them out clearly but kindly."
    )
    usr = f"""Student: {username or 'Student'}
Level: {level_name}  |  First session: {is_first}
Issue types found: {', '.join(issue_types) or 'None'}
Repeating patterns:
{repeat_str}
Overall weakness: {overall_pattern or 'Not enough data yet'}

Respond ONLY in this XML:
<mentor>
  <greeting>Personal one-liner addressing {username or 'the student'} by name, mentioning their level</greeting>
  <strengths>1-2 sentences on what they are doing well (be specific)</strengths>
  <focus>The single most important thing to fix this week</focus>
  <repeat_callout>If repeats exist: call them out firmly but kindly starting with "REPEAT MISTAKE —". If none: "No repeat patterns yet — great consistency!"</repeat_callout>
  <encouragement>One punchy genuine motivational line</encouragement>
  <next_challenge>One specific coding challenge targeting their weak spot</next_challenge>
</mentor>"""
    text, tokens = _chat(sys, usr, max_tokens=700, temp=0.75)
    return {
        "greeting":       _tag(text, "greeting"),
        "strengths":      _tag(text, "strengths"),
        "focus":          _tag(text, "focus"),
        "repeat_callout": _tag(text, "repeat_callout"),
        "encouragement":  _tag(text, "encouragement"),
        "next_challenge": _tag(text, "next_challenge"),
        "tokens":         tokens,
    }

# ══════════════════════════════════════════════════════════════════
# AGENT 5 — ROADMAP BUILDER
# ══════════════════════════════════════════════════════════════════
def agent_roadmap(username, lang, issues, past_mems, level_name):
    print("  [5/5] Roadmap Agent running...")
    weaknesses = list({i["type"] for i in issues}) + [m[:60] for m in past_mems[:3]]
    sys = (
        "You are a curriculum designer for self-taught programmers. "
        "Create a tight 7-day plan. Each day: one specific actionable task. No vague advice."
    )
    usr = f"""Student: {username or 'Student'}
Language: {lang}  |  Level: {level_name}
Weaknesses: {', '.join(weaknesses) or 'General fundamentals'}

Respond ONLY in this XML:
<roadmap>
  <goal>One sentence: what will the student achieve in 7 days?</goal>
  <days>
    <day number="1"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="2"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="3"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="4"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="5"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="6"><task>Specific task</task><resource>One free resource URL or name</resource></day>
    <day number="7"><task>Mini-project combining everything</task><resource>Build something real</resource></day>
  </days>
</roadmap>"""
    text, tokens = _chat(sys, usr, max_tokens=900, temp=0.6)
    days = []
    for m in re.finditer(r'<day number=["\'](\d+)["\']>([\s\S]*?)</day>', text, re.IGNORECASE):
        b = m.group(2)
        days.append({
            "day":      int(m.group(1)),
            "task":     _tag(b, "task"),
            "resource": _tag(b, "resource"),
        })
    return {"goal": _tag(text, "goal"), "days": days, "tokens": tokens}

# ══════════════════════════════════════════════════════════════════
# RESPONSE FORMATTER — builds the Markdown string for the frontend
# ══════════════════════════════════════════════════════════════════
def _build_markdown(a1, a2, a3, a4, a5, username):
    lines = []

    # Mentor greeting
    if a4.get("greeting"):
        lines.append(f"## 🧠 {a4['greeting']}")

    # Repeat callout (prominent)
    rc = a4.get("repeat_callout", "")
    if rc and "REPEAT MISTAKE" in rc:
        lines.append(f"\n{rc}\n")

    # Code summary
    lines.append(f"## 🔍 Code Analysis")
    if a1.get("summary"):
        lines.append(a1["summary"])

    # Issues
    critical = [i for i in a1["issues"] if i["severity"] == "critical"]
    warnings = [i for i in a1["issues"] if i["severity"] == "warning"]
    suggestions = [i for i in a1["issues"] if i["severity"] == "suggestion"]

    if critical:
        lines.append(f"\n## 🐛 Critical Issues ({len(critical)})")
        for i in critical:
            lines.append(f"- **Line {i['line']} [{i['type']}]:** {i['description']}")
            lines.append(f"  - Fix: {i['fix']}")

    if warnings:
        lines.append(f"\n## ⚠️ Warnings ({len(warnings)})")
        for i in warnings:
            lines.append(f"- **Line {i['line']} [{i['type']}]:** {i['description']}")
            lines.append(f"  - Fix: {i['fix']}")

    if suggestions:
        lines.append(f"\n## 💡 Suggestions ({len(suggestions)})")
        for i in suggestions:
            lines.append(f"- **[{i['type']}]:** {i['description']}")

    # Positives
    if a1.get("positives"):
        lines.append(f"\n## ✅ What You Did Well")
        for p in a1["positives"]:
            lines.append(f"- {p}")

    # Memory insights
    if a2.get("repeats"):
        lines.append(f"\n## 🧠 Memory Insights")
        for r in a2["repeats"]:
            lines.append(f"- **Pattern:** {r['pattern']}")
        if a2.get("patterns") and a2["patterns"] != "No clear pattern yet.":
            lines.append(f"\n**Overall weakness:** {a2['patterns']}")

    # Fixed code
    if a3.get("fixed_code"):
        lines.append(f"\n## 🔧 Fixed Code")
        if a3.get("explanation"):
            lines.append(a3["explanation"])
        lines.append(f"```\n{a3['fixed_code']}\n```")

    # Mentor advice
    if a4.get("focus"):
        lines.append(f"\n## 🎯 Focus This Week")
        lines.append(a4["focus"])

    if a4.get("encouragement"):
        lines.append(f"\n_{a4['encouragement']}_")

    if a4.get("next_challenge"):
        lines.append(f"\n## 🎯 Next Challenge")
        lines.append(a4["next_challenge"])

    # Roadmap
    if a5.get("goal") and a5.get("days"):
        lines.append(f"\n## 📈 7-Day Learning Roadmap")
        lines.append(f"**Goal:** {a5['goal']}\n")
        for d in a5["days"]:
            lines.append(f"- **Day {d['day']}:** {d['task']}  _(Resource: {d['resource']})_")

    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════
# ORCHESTRATOR — runs all 5 agents in sequence
# ══════════════════════════════════════════════════════════════════
def run_pipeline(user_id, username, email, problem, code, lang):
    print(f"\n{'═'*58}")
    print(f"  PIPELINE  user={user_id!r}  lang={lang}")
    print(f"{'═'*58}")

    bank_id = f"student-{user_id}"

    # ── Agent 1: Analyze ──────────────────────────────────────────
    a1 = agent_analyzer(problem, code, lang)

    # ── Agent 2: Memory recall + pattern detection ────────────────
    a2 = agent_memory(bank_id, problem, code, a1["issues"])

    # ── Agent 3: Fix code + extract structured mistakes ───────────
    a3 = agent_fix(problem, code, lang, a1["issues"])

    # ── Agent 4: Mentor message ───────────────────────────────────
    profile_pre = _get_profile(user_id)
    level_info  = _level_info(profile_pre.get("xp", 0))
    a4 = agent_mentor(
        username, problem, a1["issues"],
        a2["repeats"], a2["patterns"],
        level_info["level_name"],
        profile_pre.get("total_submissions", 0) == 0,
    )

    # ── Agent 5: Roadmap ──────────────────────────────────────────
    a5 = agent_roadmap(username, lang, a1["issues"], a2["past_memories"], level_info["level_name"])

    # ── Retain new mistakes into Hindsight ────────────────────────
    retained = 0
    new_mistakes_retained = []
    for mistake in a3["mistakes"]:
        content = (
            f"Student mistake: {mistake}. "
            f"Problem: {problem}. "
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d')}."
        )
        if hindsight_retain(bank_id, content):
            retained += 1
        else:
            _fb_retain(bank_id, mistake)
        new_mistakes_retained.append(mistake)

    # ── Update student profile (XP, streak, badges) ───────────────
    profile_update = _update_profile(
        user_id, username, lang,
        a1["score"], len(a1["issues"]), len(a2["repeats"]),
        a3["mistakes"],
    )

    # ── Build final markdown response ─────────────────────────────
    response_md = _build_markdown(a1, a2, a3, a4, a5, username)

    total_tokens = sum(x["tokens"] for x in [a1, a2, a3, a4, a5])
    print(f"  DONE — {total_tokens} tokens | {retained}/{len(a3['mistakes'])} retained to Hindsight")

    return {
        # Identity
        "user_id":    user_id,
        "username":   username or user_id,
        "bank_id":    bank_id,
        "lang":       lang,

        # Agent outputs (structured)
        "analyzer":   a1,
        "memory":     a2,
        "fix":        a3,
        "mentor":     a4,
        "roadmap":    a5,

        # Flat fields the frontend reads directly
        "response":          response_md,
        "score":             a1["score"],
        "topics":            a1["topics"],
        "issue_count":       len(a1["issues"]),
        "repeat_count":      len(a2["repeats"]),
        "past_count":        len(a2["past_memories"]),
        "past_mistakes":     a2["past_memories"],
        "past_mistakes_count": len(a2["past_memories"]),
        "new_mistakes_found": new_mistakes_retained,
        "is_first_run":      profile_update["total_submissions"] == 1,

        # Gamification
        "xp_earned":         profile_update["xp_earned"],
        "total_xp":          profile_update["total_xp"],
        "streak_days":       profile_update["streak_days"],
        "total_submissions": profile_update["total_submissions"],
        "badges":            profile_update["badges"],
        "history":           profile_update["history"],
        "level_icon":        profile_update["level_info"]["level_icon"],
        "level_name":        profile_update["level_info"]["level_name"],
        "level_progress_pct": profile_update["level_info"]["progress_pct"],
        "xp_to_next":        profile_update["level_info"]["xp_to_next"],
        "leveled_up":        profile_update["leveled_up"],

        # Meta
        "retained":         retained,
        "total_tokens":     total_tokens,
        "tokens_used":      total_tokens,
        "hindsight_active": _hs_ready(),
        "hindsight_org_id": _hs_org() if _hs_ready() else None,
        "session":          profile_update["total_submissions"],
    }

# ══════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    b        = request.get_json(force=True, silent=True) or {}
    uid      = str(b.get("user_id", "")).strip()
    username = str(b.get("username", "")).strip()
    email    = str(b.get("email", "")).strip()
    problem  = str(b.get("problem", "")).strip()
    code     = str(b.get("code", "")).strip()
    lang     = str(b.get("lang", "python")).strip() or "python"

    if not uid:     return jsonify({"error": "user_id required"}), 400
    if not problem: return jsonify({"error": "problem required"}), 400
    if not code:    return jsonify({"error": "code required"}), 400

    gk = os.environ.get("GROQ_API_KEY", "").strip()
    if not gk or gk == "gsk_paste_your_groq_key_here":
        return jsonify({"error": "GROQ_API_KEY not set in .env"}), 500

    try:
        return jsonify(run_pipeline(uid, username, email, problem, code, lang))
    except Exception as exc:
        msg = str(exc)
        print(f"  [ERROR] {msg}")
        if "401" in msg or "authentication" in msg.lower():
            return jsonify({"error": "Invalid Groq API key — check .env"}), 500
        if "429" in msg or "rate_limit" in msg.lower():
            return jsonify({"error": "Rate limited — wait a moment and retry"}), 429
        return jsonify({"error": f"Pipeline error: {msg}"}), 500

@app.route("/health")
def health():
    gk = os.environ.get("GROQ_API_KEY", "").strip()
    hk = _hs_key()
    total_students = len([k for k in _profiles.keys()])
    return jsonify({
        "status":          "ok",
        "groq_model":      GROQ_MODEL,
        "groq_ready":      bool(gk) and gk != "gsk_paste_your_groq_key_here",
        "groq_preview":    (gk[:14] + "...") if gk else "NOT SET",
        "hindsight_active": _hs_ready(),
        "hindsight_ready": _hs_ready(),
        "hindsight_org_id": _hs_org() if _hs_ready() else None,
        "hindsight_preview": (hk[:14] + "...") if _hs_ready() else "NOT SET",
        "memory_mode":     "Hindsight Cloud (vector)" if _hs_ready() else "Fallback (disk JSON)",
        "total_students":  total_students,
        "fallback_banks":  [k for k in _fb if not k.endswith(("-codes", "-sessions"))],
    })

@app.route("/memory/<uid>")
def view_memory(uid):
    bank = f"student-{uid}"
    return jsonify({
        "bank_id":   bank,
        "hindsight": _hs_ready(),
        "fallback":  _fb.get(bank, []),
        "sessions":  _fb.get(f"{bank}-sessions", 0),
    })

@app.route("/memory/<uid>", methods=["DELETE"])
def clear_memory(uid):
    bank = f"student-{uid}"
    hindsight_delete(bank)
    for k in [bank, f"{bank}-codes", f"{bank}-sessions"]:
        _fb.pop(k, None)
    _fb_save(_fb)
    return jsonify({"ok": True, "cleared": bank})

# ── Fallback memory routes (called by frontend) ───────────────────
@app.route("/memory/fallback")
def memory_fallback_all():
    """Return the entire fallback memory store — used by frontend memory panel."""
    return jsonify(_fb)

@app.route("/memory/fallback/<uid>", methods=["DELETE"])
def memory_fallback_clear(uid):
    """Clear fallback memory for a specific user."""
    bank = f"student-{uid}"
    hindsight_delete(bank)
    for k in [bank, f"{bank}-codes", f"{bank}-sessions"]:
        _fb.pop(k, None)
    _fb_save(_fb)
    return jsonify({"ok": True, "cleared": bank})

# ── Profile routes ────────────────────────────────────────────────
@app.route("/profile/<uid>")
def get_profile(uid):
    p = _get_profile(uid)
    return jsonify({
        **p,
        "level_info": _level_info(p.get("xp", 0)),
    })

# ── Leaderboard ───────────────────────────────────────────────────
@app.route("/leaderboard")
def leaderboard():
    rows = []
    for uid, p in _profiles.items():
        xp   = p.get("xp", 0)
        li   = _level_info(xp)
        rows.append({
            "user_id":     uid,
            "username":    p.get("username", uid),
            "xp":          xp,
            "streak":      p.get("streak_days", 0),
            "submissions": p.get("total_submissions", 0),
            "level":       li["level_name"],
            "level_icon":  li["level_icon"],
        })
    rows.sort(key=lambda r: r["xp"], reverse=True)
    return jsonify(rows[:20])

# ── ENTRY POINT ───────────────────────────────────────────────────
if __name__ == "__main__":
    gk = os.environ.get("GROQ_API_KEY", "").strip()
    print()
    print("═" * 60)
    print("  AI CODING MENTOR  —  5-AGENT PIPELINE  v3.0")
    print("  Groq + Hindsight Vector Memory")
    print("═" * 60)
    print(f"  Model     : {GROQ_MODEL}")
    print(f"  Groq      : {'✅  ' + gk[:14] + '...' if gk and gk != 'gsk_paste_your_groq_key_here' else '❌  NOT SET — add to .env'}")
    print(f"  Hindsight : {'✅  ' + _hs_key()[:14] + '...' if _hs_ready() else '⚠   NOT SET — using disk fallback'}")
    print(f"  Agents    : Analyzer · Memory · Fixer · Mentor · Roadmap")
    print(f"  URL       : http://localhost:5001")
    print("═" * 60)
    print()
    app.run(debug=True, port=5001)
