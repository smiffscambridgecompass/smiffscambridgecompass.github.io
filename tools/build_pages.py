#!/usr/bin/env python3
"""Build Google-friendly static pages for Smiff's Cambridge Compass from venues.json.

Writes, next to index.html:
  pubs/index.html              every place, A to Z
  pubs/<id>/index.html         one page per place
  <guide>/index.html           topic guides (pub quizzes, beer gardens, live music...)
  sitemap.xml, robots.txt

Run from the repository root:  python3 tools/build_pages.py
Uses only the Python standard library. Safe to run again: it rewrites what it made
and removes pages for places that are no longer in venues.json.
"""
import datetime as dt
import html
import json
import math
import os
import re
import shutil
import sys
from zoneinfo import ZoneInfo

SITE = "https://smiffs.uk"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMAIL = "smiffscompass@gmail.com"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYLONG = dict(zip(DAYS, ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]))
CATNAME = {"pub": "Pub", "music": "Live music", "food": "Food", "late": "Late night", "classical": "Classical music"}
KINDNAME = {"music": "Live music", "classical": "Classical", "club": "Club night", "quiz": "Quiz", "offer": "Deal",
            "comedy": "Comedy", "sport": "Sport", "event": ""}

GIVING = re.compile(r"streetsmart|homeless|charit|fundrais|donat|good cause", re.I)
TODAY = dt.datetime.now(ZoneInfo("Europe/London")).date()
if len(sys.argv) > 1:  # optional fixed date for testing: build_pages.py 2026-11-06
    TODAY = dt.date.fromisoformat(sys.argv[1])
T0 = TODAY.isoformat()

e = lambda s: html.escape(str(s), quote=True)


def fmt_date(d, long=False):
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime(("%A " if long else "%a ") + str(d.day) + (" %B" if long else " %b"))


def when_label(d):
    if d == T0:
        return "Today"
    if d == (TODAY + dt.timedelta(1)).isoformat():
        return "Tomorrow"
    return fmt_date(d)


# ---------- data ----------
DATA = json.load(open(os.path.join(ROOT, "venues.json"), encoding="utf-8"))
V = sorted(DATA["venues"], key=lambda v: re.sub(r"^the ", "", v["name"].lower()))
BYID = {v["id"]: v for v in V}
CHECKED = DATA.get("meta", {}).get("checkedLabel", "")


def closed(v):
    return bool(v.get("closedUntil") and T0 < v["closedUntil"])


def dated(v, days=None):
    lim = (TODAY + dt.timedelta(days)).isoformat() if days else "9999"
    out = [x for x in v.get("events", []) if x.get("date", "") >= T0 and x["date"] < lim]
    for m in v.get("manual") or []:
        if m.get("type") == "gig" and m.get("date", "") >= T0 and m["date"] < lim:
            out.append({"date": m["date"], "title": m["text"], "kind": "music"})
    if v.get("closedUntil"):
        out = [x for x in out if x["date"] >= v["closedUntil"]]
    return sorted(out, key=lambda x: x["date"])


def weekly(v):
    out = list(v.get("weekly", []))
    for m in v.get("manual") or []:
        if m.get("type") == "weekly" and m.get("day") in DAYS:
            out.append({"day": m["day"], "title": m["text"], "kind": "music"})
    return sorted(out, key=lambda w: DAYS.index(w["day"]) if w.get("day") in DAYS else 9)


def offers(v):
    out = list(v.get("offers", []))
    out += [m["text"] for m in v.get("manual") or [] if m.get("type") == "offer"]
    return out


def amen(v, k):
    return bool((v.get("amen") or {}).get(k))


def is_kind(x, kinds):
    k = x.get("kind") or "event"
    return k in kinds or (k == "comedy" and "event" in kinds)


def on_day(v, d):
    """Everything at v on date d (an ISO string): dated items plus weekly ones."""
    if v.get("closedUntil") and d < v["closedUntil"]:
        return []
    dn = DAYS[dt.date.fromisoformat(d).weekday()]
    return [x for x in dated(v) if x["date"] == d] + [dict(w, weekly=True) for w in weekly(v) if w.get("day") == dn]


def dist_m(a, b):
    R = 6371000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lng"] - a["lng"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def walk(m):
    mins = max(1, round(m * 1.25 / 80))  # 1.25 for street detours, 80 m a minute
    return f"{mins} min walk"


def kind_of_place(v):
    c = v.get("cats", [])
    if "pub" in c:
        return "pub"
    if "classical" in c:
        return "concert venue"
    if "music" in c:
        return "music venue"
    if "late" in c:
        return "late-night bar"
    return "bar and restaurant"


def schema_type(v):
    c = v.get("cats", [])
    if "pub" in c:
        return "BarOrPub"
    if "music" in c:
        return "MusicVenue"
    if "late" in c:
        return "NightClub"
    if "food" in c:
        return "FoodEstablishment"
    return "Place"


def page_url(path):
    return SITE + path


def vlink(v, text=None):
    return f'<a href="/pubs/{e(v["id"])}/">{e(text or v["name"])}</a>'


def https(u):
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) else ""


# ---------- page shell ----------
CSS = """
:root{--bg:#FFF6E3;--panel:#FFFDF8;--ink:#161616;--muted:#55524B;--line:#DDD5C4;--soft:#F5EFE2;--pop:#FFD23F;--on-pop:#161616;--edge:#161616;--hard:#161616;
--display:"Gluten","Arial Rounded MT Bold",system-ui,sans-serif;--body:"Fredoka",system-ui,-apple-system,"Segoe UI",sans-serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111111;--panel:#1A1A1A;--ink:#F6F1E6;--muted:#B9B2A5;--line:#34312C;--soft:#242220;--edge:#6E6960;--hard:#000;color-scheme:dark}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--panel);color:var(--ink);font:17px/1.5 var(--body)}
a{color:inherit;text-decoration-thickness:2px;text-underline-offset:3px}
a:hover{text-decoration-color:var(--pop)}
:focus-visible{outline:3px solid var(--pop);outline-offset:2px}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header.top{border-bottom:2px solid var(--edge);background:var(--panel)}
header.top .wrap{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:12px;padding-bottom:12px}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;font:800 1.15rem/1.1 var(--display)}
.brand img{width:36px;height:36px;display:block}
.cta{display:inline-block;background:var(--pop);color:var(--on-pop);border:2px solid var(--edge);border-radius:999px;box-shadow:3px 3px 0 var(--hard);padding:8px 16px;font-weight:700;text-decoration:none;white-space:nowrap}
.cta:hover{transform:translate(1px,1px);box-shadow:2px 2px 0 var(--hard)}
main{padding:20px 0 40px}
.crumbs{font-size:.86rem;color:var(--muted);margin:0 0 12px}
.crumbs a{color:var(--muted)}
h1{font:800 clamp(1.8rem,6vw,2.6rem)/1.1 var(--display);margin:0 0 8px;text-wrap:balance}
h2{font:800 1.45rem/1.2 var(--display);margin:30px 0 8px;text-wrap:balance}
h3{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:18px 0 6px}
.lede{font-size:1.08rem;margin:0 0 14px}
.meta{color:var(--muted);margin:0 0 6px}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 14px;padding:0;list-style:none}
.tags li{border:2px solid var(--edge);border-radius:999px;padding:2px 11px;font-size:.84rem;font-weight:600}
.tags li.hi{background:var(--pop);color:var(--on-pop)}
.box{border:2px solid var(--edge);border-radius:16px;box-shadow:4px 4px 0 var(--hard);background:var(--panel);padding:14px 16px;margin:18px 0}
.box.pop{background:var(--pop);color:var(--on-pop)}
.box.pop a{color:var(--on-pop)}
.box p{margin:4px 0}
.links{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.links a{border:2px solid var(--edge);border-radius:10px;padding:6px 12px;font-weight:600;text-decoration:none;font-size:.92rem}
ul.list{list-style:none;margin:0;padding:0;border-top:2px solid var(--edge)}
ul.list>li{padding:10px 2px;border-bottom:1.5px dashed var(--line)}
ul.list .w{display:inline-block;min-width:6.2em;font-weight:700;font-variant-numeric:tabular-nums}
ul.list .k{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;font-weight:700;color:var(--muted);margin-left:6px;white-space:nowrap}
ul.list .sub{display:block;color:var(--muted);font-size:.92rem}
ul.list .n{font-weight:700}
dl.facts{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;margin:0}
dl.facts dt{font-weight:700}
dl.facts dd{margin:0}
.guides{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:8px 0}
.guides a{display:inline-block;border:2px solid var(--edge);border-radius:999px;padding:4px 12px;font-weight:600;text-decoration:none;font-size:.9rem;background:var(--panel)}
.daybar{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding:10px 16px;margin:6px -16px 4px;background:var(--panel);border-bottom:2px solid var(--edge)}
.daybar::-webkit-scrollbar{display:none}
.dchip{flex:none;font:inherit;font-size:.92rem;font-weight:700;color:var(--ink);background:var(--panel);border:2px solid var(--edge);border-radius:999px;padding:6px 14px;min-height:40px;cursor:pointer}
.dchip.today{border-style:dashed}
.dchip[aria-pressed="true"]{background:var(--pop);color:var(--on-pop);border-style:solid;box-shadow:2px 2px 0 var(--hard)}
section.grp[hidden],li[hidden]{display:none}
.hd-r{display:flex;align-items:center;gap:10px}
.az{columns:2 220px;column-gap:24px}
.az li{break-inside:avoid}
footer.foot{border-top:2px solid var(--edge);padding:18px 0 40px;color:var(--muted);font-size:.86rem}
footer.foot h2{font-size:1.1rem;color:var(--ink);margin:0 0 6px}
@media (max-width:520px){header.top .cta{padding:7px 12px;font-size:.9rem}.brand span{display:none}dl.facts{grid-template-columns:1fr}dl.facts dt{margin-top:6px}}
"""

GUIDES = []  # (path, short label) filled as guides are defined


def shell(path, title, desc, body, crumbs=None, ld=None, map_link="/"):
    url = page_url(path)
    crumb_html = ""
    lds = list(ld or [])
    if crumbs:
        items = [("Home", "/")] + crumbs
        crumb_html = '<nav class="crumbs" aria-label="Breadcrumb">' + " › ".join(
            (f'<a href="{e(p)}">{e(n)}</a>' if p else e(n)) for n, p in items) + "</nav>"
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": page_url(p or path)} for i, (n, p) in enumerate(items)]})
    guides = "".join(f'<li><a href="{p}">{e(l)}</a></li>' for p, l in GUIDES)
    NAV = nav_html()
    ldtags = "".join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace("</", "<\\/") + "</script>" for x in lds)
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(url)}">
<meta property="og:site_name" content="Smiff's Cambridge Compass">
<meta property="og:image" content="{SITE}/preview.png?v=6">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon-32.png" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png?v=6">
<meta name="theme-color" content="#FFFDF8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gluten:wght@800&family=Fredoka:wght@400;600;700&display=swap">
<link rel="stylesheet" href="/pages.css?v={TODAY.strftime('%Y%m%d')}">
<script data-goatcounter="https://smiffscambridgecompass.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
{ldtags}
</head>
<body>
<header class="top"><div class="wrap"><a class="brand" href="/"><img src="/favicon.svg" alt="" width="36" height="36"><span>Smiff&rsquo;s Cambridge Compass</span></a><div class="hd-r"><a class="cta" href="{e(map_link)}">Open the map</a>{NAV}</div></div></header>
<main class="wrap">
{crumb_html}
{body}
</main>
<footer class="foot"><div class="wrap">
<h2>Guides to Cambridge pubs</h2>
<ul class="guides">{guides}<li><a href="/areas/">Pubs by area</a></li><li><a href="/pubs/">Every place A to Z</a></li></ul>
<p>Smiff&rsquo;s Cambridge Compass is a free map of what&rsquo;s on in Cambridge pubs, made by a local pub-goer. Listings come from venue websites, CAMRA and event listings, and are checked twice a week (last checked {e(CHECKED)}). Times and deals can change, so check with the pub before a big night out.</p>
<p>Run a pub or venue? Send your events to <a href="mailto:{EMAIL}">{EMAIL}</a> and they&rsquo;ll go on the map for free, and <a href="/for-pubs/">get a free badge for your website</a>.</p>
</div></footer>
<script>{NAV_JS}</script>
</body>
</html>
"""


def write(path, content):
    fp = os.path.join(ROOT, path.strip("/"), "index.html") if path.endswith("/") else os.path.join(ROOT, path.strip("/"))
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(content)


def row(v, detail="", when="", kind="", day=None):
    w = f'<span class="w">{e(when)}</span> ' if when else ""
    k = f'<span class="k">{e(kind)}</span>' if kind else ""
    dd = f' data-day="{e(day)}"' if day else ""
    return f'<li{dd}>{w}<span class="n">{vlink(v)}</span>{k}<span class="sub">{detail}</span></li>'


def dn_of(d):
    return DAYS[dt.date.fromisoformat(d).weekday()]


def grp(title, items):
    return f'<section class="grp"><h2>{title}</h2><ul class="list">' + "".join(items) + "</ul></section>"


def daybar(body):
    """Day chips for a guide whose list items carry data-day. Works without JS as plain text links to nothing harmful."""
    have = set(re.findall(r'data-day="(\w{3})"', body))
    days = [d for d in DAYS if d in have]
    if len(days) < 2:
        return ""
    today = DAYS[TODAY.weekday()]
    chips = '<button type="button" class="dchip" data-f="" aria-pressed="true">All days</button>' + "".join(
        f'<button type="button" class="dchip{" today" if d == today else ""}" data-f="{d}" aria-pressed="false">{"Today" if d == today else d}</button>' for d in days)
    return (f'<div class="daybar" role="group" aria-label="Show one day">{chips}</div><p class="dnone meta" hidden>Nothing on that day yet.</p>'
            '<script>(function(){var bar=document.currentScript.previousElementSibling.previousElementSibling,none=bar.nextElementSibling;'
            'function apply(f){bar.querySelectorAll(".dchip").forEach(function(b){b.setAttribute("aria-pressed",b.dataset.f===f?"true":"false");if(b.dataset.f===f&&b.scrollIntoView)try{bar.scrollTo({left:b.offsetLeft-bar.clientWidth/2+b.offsetWidth/2,behavior:"smooth"})}catch(e){}});'
            'var any=false;document.querySelectorAll("section.grp").forEach(function(sec){var vis=0;sec.querySelectorAll("li[data-day]").forEach(function(li){var on=!f||li.dataset.day===f||li.dataset.day==="all";li.hidden=!on;if(on)vis++});sec.hidden=!vis;if(vis)any=true});'
            'none.hidden=any;try{history.replaceState(null,"",f?"#"+f.toLowerCase():location.pathname)}catch(e){}}'
            'bar.addEventListener("click",function(e){var b=e.target.closest(".dchip");if(b)apply(b.dataset.f)});'
            'var h=(location.hash||"").slice(1);h=h.charAt(0).toUpperCase()+h.slice(1,3);if(/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)$/.test(h)&&bar.querySelector(\'[data-f="\'+h+\'"]\'))document.addEventListener("DOMContentLoaded",function(){apply(h)});'
            'window.addEventListener("hashchange",function(){var h=(location.hash||"").slice(1);h=h.charAt(0).toUpperCase()+h.slice(1,3);if(bar.querySelector(\'[data-f="\'+h+\'"]\')){apply(h);bar.scrollIntoView({block:"start"})}})})()</script>')


def addr(v):
    return e(f'{v["address"]}, {v.get("postcode", "")}'.strip(", "))


# ---------- guides ----------
def guide_spec():
    """Each guide: path, short label, title, description, intro, builder(ld) -> html."""
    specs = []

    def add(path, label, title, desc, intro, build):
        specs.append((path, label, title, desc, intro, build))
        GUIDES.append((path, label))

    # this weekend
    def weekend_days():
        wd = TODAY.weekday()  # Mon=0
        start = TODAY if wd >= 4 else TODAY + dt.timedelta(4 - wd)
        return [(start + dt.timedelta(i)).isoformat() for i in range(7 - start.weekday())]

    def b_weekend(ld):
        out = ""
        for d in weekend_days():
            rows = []
            for v in V:
                for x in on_day(v, d):
                    if x.get("kind") in ("sport", "offer"):
                        continue
                    rows.append((0 if x.get("kind") in ("music", "classical") else 1 if x.get("kind") in ("comedy", "club") else 2,
                                 1 if x.get("weekly") else 0, v["name"], v, x))
            rows.sort(key=lambda r: r[:3])
            if not rows:
                continue
            out += grp(e(fmt_date(d, True)), [
                row(v, e(x["title"]) + (" <em>(every week)</em>" if x.get("weekly") else ""), "", KINDNAME.get(x.get("kind"), ""), dn_of(d)) for *_, v, x in rows[:40]])
        return out or "<p>Nothing listed yet for this weekend. Listings are checked every Monday and Thursday.</p>"

    wk = weekend_days()
    add("/this-weekend/", "This weekend", f"What's on in Cambridge pubs this weekend ({fmt_date(wk[0])} to {fmt_date(wk[-1])})",
        "Gigs, quiz nights, club nights, comedy and events in Cambridge pubs and venues this weekend, checked twice a week.",
        "Gigs, quizzes, club nights and one-off events in Cambridge pubs and venues this weekend, with live music first.", b_weekend)

    # pub quizzes
    def b_quiz(ld):
        out = ""
        for dn in DAYS:
            rows = [(v, w) for v in V if not closed(v) for w in weekly(v) if w.get("day") == dn and is_kind(w, ("quiz",))]
            if rows:
                out += grp(f"{DAYLONG[dn]} quiz nights", [row(v, e(w["title"]) + f' · {addr(v)}', day=dn) for v, w in rows])
        once = sorted([(x["date"], v, x) for v in V for x in dated(v, 60) if is_kind(x, ("quiz",))], key=lambda r: (r[0], r[1]["name"]))
        if once:
            out += grp("Monthly and one-off quizzes", [row(v, e(x["title"]), when_label(d), day=dn_of(d)) for d, v, x in once])
        return out

    nq = len({v["id"] for v in V for w in weekly(v) if is_kind(w, ("quiz",))})
    add("/pub-quizzes/", "Pub quizzes", "Pub quizzes in Cambridge: every quiz night, day by day",
        f"Find a pub quiz in Cambridge any night of the week: {nq} pubs with a regular quiz night, with times and entry fees where the pub lists them.",
        f"{nq} Cambridge pubs run a regular quiz night. Here they are by day, with the time and entry fee where the pub says.", b_quiz)

    # live music
    def b_music(ld):
        out = ""
        for i in range(14):
            d = (TODAY + dt.timedelta(i)).isoformat()
            rows = sorted([(v, x) for v in V for x in dated(v) if x["date"] == d and is_kind(x, ("music", "classical"))], key=lambda r: r[0]["name"])
            if rows:
                out += grp(e(when_label(d) if i < 2 else fmt_date(d, True)), [
                    row(v, e(x["title"]), "", "Classical" if x.get("kind") == "classical" else "", dn_of(d)) for v, x in rows])
        reg = [(v, w) for v in V if not closed(v) for w in weekly(v) if is_kind(w, ("music",))]
        if reg:
            out += grp("Regular live music nights", [
                row(v, e(w["title"]), "Every " + DAYLONG.get(w["day"], w["day"]), day=w.get("day")) for v, w in reg])
        return out

    add("/live-music/", "Live music", "Live music in Cambridge pubs and venues: gigs for the next two weeks",
        "Gigs and live music in Cambridge pubs, bars and venues for the next two weeks, plus the pubs with a regular music night.",
        "Every gig we know about in Cambridge pubs and venues for the next two weeks, then the pubs with a regular live music night.", b_music)

    # sunday roasts
    roast = re.compile(r"roast|carvery|sunday lunch", re.I)

    def b_roast(ld):
        out = ""
        seen = set()
        for dn in ["Sun", "Sat", "Mon", "Tue", "Wed", "Thu", "Fri"]:
            rows = [(v, w) for v in V if not closed(v) for w in weekly(v) if w.get("day") == dn and roast.search(w["title"])]
            seen |= {v["id"] for v, _ in rows}
            if rows:
                out += grp(f"{DAYLONG[dn]} roasts", [row(v, e(w["title"]) + f" · {addr(v)}", day=dn) for v, w in rows])
        more = [(v, o) for v in V if not closed(v) and v["id"] not in seen for o in offers(v) if roast.search(o)]
        if more:
            out += grp("More roasts (check which days)", [row(v, e(o) + f" · {addr(v)}", day="all") for v, o in more])
        return out

    add("/sunday-roasts/", "Sunday roasts", "Sunday roasts in Cambridge pubs",
        "Where to get a Sunday roast in a Cambridge pub, with prices and serving times where the pub lists them.",
        "Cambridge pubs serving a roast, by day, with prices and kitchen times where the pub lists them. Booking is a good idea at the popular ones.", b_roast)

    def amen_page(path, label, title, desc, intro, test, extra=lambda v: ""):
        def b(ld):
            vs = [v for v in V if not closed(v) and test(v)]
            return f'<p class="meta">{len(vs)} places</p><ul class="list">' + "".join(row(v, addr(v) + extra(v)) for v in vs) + "</ul>"
        add(path, label, title, desc, intro, b)

    def nxt(v):
        d = dated(v, 21)
        return f" · Next: {e(d[0]['title'])} ({e(when_label(d[0]['date']))})" if d else ""

    ng = sum(1 for v in V if amen(v, "garden"))
    amen_page("/beer-gardens/", "Beer gardens", "Beer gardens in Cambridge: pubs with a garden",
              f"{ng} Cambridge pubs with a beer garden or outdoor seating, on one list with addresses and what's on.",
              "Cambridge pubs with a beer garden or outdoor seating, from riverside spots to small back yards.", lambda v: amen(v, "garden"), nxt)
    amen_page("/real-fires/", "Pubs with a real fire", "Cosy Cambridge pubs with a real fire",
              "Cambridge pubs with a real fire for winter: an open fire or a log burner, with addresses and what's on.",
              "Cambridge pubs with a real fire or log burner, for the cold months.", lambda v: amen(v, "fire"), nxt)
    amen_page("/dog-friendly-pubs/", "Dog-friendly pubs", "Dog-friendly pubs in Cambridge",
              "Cambridge pubs that welcome dogs, with addresses and what's on.",
              "Cambridge pubs that say dogs are welcome. Some only allow dogs in the bar, not the dining area, so check if you're eating.", lambda v: amen(v, "dogs"), nxt)

    def b_sport(ld):
        vs = [v for v in V if not closed(v) and (amen(v, "sport") or any(is_kind(x, ("sport",)) for x in dated(v) + weekly(v)))]
        out = '<ul class="list">'
        for v in vs:
            fx = [x for x in dated(v, 14) if is_kind(x, ("sport",))]
            det = addr(v) + ("".join(f'<br><strong>{e(when_label(x["date"]))}:</strong> {e(x["title"])}' for x in fx[:4]) if fx else "")
            out += row(v, det)
        return out + "</ul>"

    add("/live-sport/", "Pubs showing sport", "Pubs showing live sport in Cambridge",
        "Cambridge pubs that show football, rugby and other live sport on TV, with listed fixtures for the next two weeks.",
        "Cambridge pubs that show live sport on TV. Where a pub lists its fixtures, the next few are shown; for the rest, ring ahead to check the game is on.", b_sport)

    def b_guin(ld):
        vs = [v for v in V if v.get("guinness")]
        vs.sort(key=lambda v: (not v["guinness"].get("harp"), v["name"]))
        return '<ul class="list">' + "".join(row(v, e(v["guinness"].get("note", "")) + f" · {addr(v)}") for v in vs) + "</ul>"

    add("/guinness/", "Where to get Guinness", "Where to get a good pint of Guinness in Cambridge",
        "Cambridge pubs confirmed to pour Guinness, including the ones in Guinness's own guide to the best pints.",
        "Cambridge pubs where we've seen Guinness confirmed on the pub's website, menu or in Guinness's own guide. Plenty of other pubs pour it too.", b_guin)

    amen_page("/independent-pubs/", "Independent pubs", "Independent pubs in Cambridge",
              "Cambridge pubs that aren't owned by a pub company or brewery chain, based on the freehold owner listed by CAMRA.",
              "Pubs that aren't owned by a pub company or brewery chain, based on the freehold owner CAMRA lists.", lambda v: v.get("indie") is True, nxt)

    def b_deals(ld):
        out = ""
        for dn in DAYS:
            rows = [(v, w) for v in V if not closed(v) for w in weekly(v) if w.get("day") == dn and is_kind(w, ("offer",))]
            if rows:
                out += grp(DAYLONG[dn], [row(v, e(w["title"]), day=dn) for v, w in rows])
        rest = [(v, o) for v in V if not closed(v) for o in offers(v) if not re.search(r"christmas|festive|new year", o, re.I)]
        if rest:
            out += grp("Deals on any day", [row(v, e(o), day="all") for v, o in rest])
        return out

    add("/pub-deals/", "Pub deals", "Food and drink deals in Cambridge pubs, day by day",
        "Pizza nights, 2-for-1s, happy hours, pie and pint deals and more in Cambridge pubs, sorted by day of the week.",
        "Food and drink deals in Cambridge pubs, sorted by the day they run. Deals change often, so check with the pub before you go.", b_deals)

    xmas = re.compile(r"christmas|festive|carol|mince pie|xmas|advent|christingle|\bmulled", re.I)
    nye = re.compile(r"new year|\bnye\b|hogmanay", re.I)
    party = re.compile(r"function room|private hire|private tasting|party booking|parties|christmas party|private room", re.I)
    yr = TODAY.year if TODAY.month >= 6 else TODAY.year - 1

    def b_xmas(ld):
        ev = sorted([(x["date"], v, x) for v in V for x in dated(v) if xmas.search(x["title"]) and not nye.search(x["title"])],
                    key=lambda r: (r[0], r[1]["name"]))
        carols = [(d, v, x) for d, v, x in ev if re.search(r"carol|concert|choir|evensong|advent|christingle|music for", x["title"], re.I) or "classical" in v["cats"]]
        days = sorted([(x["date"], v, x) for v in V for x in dated(v) if x["date"][5:] in ("12-24", "12-25", "12-26")], key=lambda r: (r[0], r[1]["name"]))
        carols = [r for r in carols if r[0][5:] not in ("12-24", "12-25", "12-26")]
        other = [r for r in ev if r not in carols and r[0][5:] not in ("12-24", "12-25", "12-26")]
        out = ""
        if other:
            out += grp("Christmas parties, quizzes and events", [row(v, e(x["title"]), fmt_date(d)) for d, v, x in other])
        if carols:
            out += grp("Carols and Christmas concerts", [row(v, e(x["title"]), fmt_date(d)) for d, v, x in carols])
        give = [(v, t) for v in V for t in dict.fromkeys(offers(v) + v.get("notes", [])) if GIVING.search(t)]
        if give:
            out += grp("Giving back this Christmas", [row(v, e(t)) for v, t in give])
        info = [(v, t) for v in V for t in dict.fromkeys(offers(v) + v.get("notes", [])) if xmas.search(t) and not GIVING.search(t)]
        if info:
            out += grp("Festive menus and Christmas bookings", [row(v, e(t)) for v, t in info])
        if days:
            out += grp("Christmas Eve, Christmas Day and Boxing Day", [row(v, e(x["title"]), fmt_date(d)) for d, v, x in days])
        out += f'<p class="meta">More pubs announce their Christmas plans every week, and this page is updated as they do. Also see <a href="/new-years-eve/">New Year&rsquo;s Eve</a> and <a href="/christmas-party-venues/">Christmas party venues</a>.</p>'
        return out or "<p>Nothing festive listed yet. Check back soon.</p>"

    add("/christmas/", "Christmas", f"Christmas in Cambridge pubs {yr}: events, carols, festive menus and opening",
        "Christmas parties, carols, festive menus, Christmas Day lunches and Boxing Day events in Cambridge pubs, updated as pubs announce them.",
        "Christmas parties and quizzes, carols, festive menus and what's on over Christmas in Cambridge pubs and venues, as they're announced.", b_xmas)

    def b_nye(ld):
        ev = sorted([(x["date"], v, x) for v in V for x in dated(v) if nye.search(x["title"]) or x["date"][5:] == "12-31"], key=lambda r: r[1]["name"])
        out = ""
        if ev:
            out += grp(f"New Year&rsquo;s Eve parties", [row(v, e(x["title"]), fmt_date(d)) for d, v, x in ev])
        nyd = sorted([(x["date"], v, x) for v in V for x in dated(v) if x["date"][5:] == "01-01"], key=lambda r: r[1]["name"])
        if nyd:
            out += grp("New Year&rsquo;s Day", [row(v, e(x["title"]), fmt_date(d)) for d, v, x in nyd])
        info = [(v, t) for v in V for t in dict.fromkeys(offers(v) + v.get("notes", [])) if nye.search(t)]
        if info:
            out += grp("New Year menus and bookings", [row(v, e(t)) for v, t in info])
        out += '<p class="meta">More New Year&rsquo;s Eve nights get announced through December, and this page is updated as they are. Tickets for the popular ones go early.</p>'
        return out

    add("/new-years-eve/", "New Year's Eve", f"New Year's Eve in Cambridge {yr}: pub parties, gigs and club nights",
        f"Where to go for New Year's Eve {yr} in Cambridge: pub parties, live bands, DJs and club nights, with times and ticket prices.",
        f"Pub parties, live bands and club nights for New Year's Eve {yr} in Cambridge, with times and prices where the venue lists them.", b_nye)

    def b_party(ld):
        fr = [v for v in V if not closed(v) and any(party.search(t) for t in v.get("features", []) + offers(v) + v.get("notes", []))]
        menus = [v for v in V if not closed(v) and v not in fr and any(xmas.search(t) and re.search(r"book|menu|party", t, re.I) for t in offers(v) + v.get("notes", []))]
        out = ""
        if fr:
            out += grp("Pubs with a function room or party bookings", [
                row(v, addr(v) + "".join(f"<br>{e(t)}" for t in dict.fromkeys(offers(v) + v.get("notes", [])) if xmas.search(t) or party.search(t))) for v in fr])
        if menus:
            out += grp("Pubs taking Christmas bookings", [
                row(v, addr(v) + "".join(f"<br>{e(t)}" for t in dict.fromkeys(offers(v) + v.get("notes", [])) if xmas.search(t))) for v in menus])
        return out

    add("/christmas-party-venues/", "Christmas party venues", f"Christmas party venues in Cambridge pubs {yr}",
        "Cambridge pubs with function rooms, party bookings and Christmas menus, for work Christmas parties and big groups.",
        "Cambridge pubs with a function room or party bookings, then the pubs taking Christmas bookings for tables. Ring early: December weekends go first.", b_party)

    riverside = ["anchor", "mill", "granta", "millworks", "old-spring", "fort-st-george", "boathouse", "tivoli", "waterman",
                 "red-lion-grantchester", "green-man-grantchester", "rupert-brooke", "blue-ball", "plough-fen-ditton"]
    amen_page("/riverside-pubs/", "Riverside pubs", "Riverside pubs in Cambridge: pubs by the Cam",
              "Cambridge pubs on or near the River Cam, from the Mill and the Anchor by the punts to Chesterton and Grantchester.",
              "Pubs on or near the River Cam, from the punting stations in town to Chesterton and out to Grantchester.", lambda v: v["id"] in riverside, nxt)
    return specs


# ---------- venue page ----------
def venue_page(v):
    path = f"/pubs/{v['id']}/"
    kp = kind_of_place(v)
    name = v["name"]
    wk, dd, of = weekly(v), dated(v), offers(v)
    give = [n for n in dict.fromkeys(v.get("notes", []) + of) if GIVING.search(n)]
    quiz = [w for w in wk if is_kind(w, ("quiz",))]
    feats = []
    if amen(v, "garden"):
        feats.append("beer garden")
    if amen(v, "fire"):
        feats.append("real fire")
    if amen(v, "sport"):
        feats.append("live sport on TV")
    if amen(v, "dogs"):
        feats.append("dog friendly")
    bits = []
    if quiz:
        bits.append("quiz night on " + " and ".join(DAYLONG[w["day"]] + "s" for w in quiz[:2]))
    if dd:
        bits.append(f"{len(dd)} upcoming event{'s' if len(dd) != 1 else ''}")
    bits += feats[:3]
    summary = (", ".join(bits) + ".") if bits else ""
    title = f"{name}, Cambridge: what's on, opening hours and food"
    desc = f"{name} is a {kp} at {v['address']}, Cambridge {v.get('postcode', '')}. " + (summary[:1].upper() + summary[1:] + " " if summary else "") + "Opening hours, food and events, checked twice a week."
    tags = [f'<li class="hi">{e(CATNAME.get(c, c))}</li>' for c in v.get("cats", [])]
    tags += [f"<li>{e(f[:1].upper() + f[1:])}</li>" for f in feats]
    if v.get("indie") is True:
        tags.append("<li>Independent</li>")
    elif v.get("group"):
        tags.append(f"<li>{e(v['group'])}</li>")
    if v.get("guinness"):
        tags.append("<li>Guinness</li>")
    body = f'<h1>{e(name)}</h1><p class="meta">{e(kp[:1].upper() + kp[1:])} · {addr(v)}</p><ul class="tags">{"".join(tags)}</ul>'
    if closed(v):
        body += f'<div class="box pop"><p><strong>Closed until {e(fmt_date(v["closedUntil"], True))}.</strong></p></div>'
    today = on_day(v, T0)
    if today and not closed(v):
        body += '<div class="box pop"><h3 style="margin-top:0;color:inherit">On today</h3>' + "".join(f"<p>{e(x['title'])}</p>" for x in today[:4]) + "</div>"
    maps = f"https://www.google.com/maps/dir/?api=1&destination={v['lat']},{v['lng']}"
    links = [f'<a href="{e(maps)}" rel="noopener">Directions</a>']
    if https(v.get("website")):
        links.append(f'<a href="{e(v["website"])}" rel="noopener nofollow">Website</a>')
    links.append(f'<a href="/?p={e(v["id"])}">See it on the map</a>')
    body += '<div class="links">' + "".join(links) + "</div>"
    if dd:
        body += f"<h2>What's on at {e(name)}</h2><ul class=\"list\">" + "".join(
            f'<li><span class="w">{e(when_label(x["date"]))}</span> {e(x["title"])}<span class="k">{e(KINDNAME.get(x.get("kind"), ""))}</span></li>' for x in dd[:30]) + "</ul>"
    if wk:
        body += "<h2>Every week</h2><ul class=\"list\">" + "".join(
            f'<li><span class="w">{e(DAYLONG.get(w["day"], w["day"]))}</span> {e(w["title"])}<span class="k">{e(KINDNAME.get(w.get("kind"), ""))}</span></li>' for w in wk) + "</ul>"
    if of:
        body += "<h2>Deals</h2><ul class=\"list\">" + "".join(f"<li>{e(o)}</li>" for o in of) + "</ul>"
    facts = []
    if v.get("hours"):
        facts.append(("Opening hours", e(v["hours"])))
    if v.get("food"):
        facts.append(("Food", e(v["food"])))
    if v.get("features"):
        facts.append(("Features", e(", ".join(v["features"]))))
    acc = v.get("access") or {}
    if acc.get("step") == "yes" or acc.get("note"):
        facts.append(("Access", e(("Step-free entrance. " if acc.get("step") == "yes" else "") + ("Accessible toilet. " if acc.get("wc") else "") + (acc.get("note") or "")).strip()))
    if v.get("guinness"):
        facts.append(("Guinness", e(v["guinness"].get("note", "Pours Guinness"))))
    if give:
        body = body.replace('<div class="links">', '<div class="box"><h3 style="margin-top:0">&#10084;&#65039; Giving back</h3>' + "".join(f"<p>{e(n)}</p>" for n in give) + '</div><div class="links">', 1)
    if facts:
        body += "<h2>Good to know</h2><dl class=\"facts\">" + "".join(f"<dt>{k}</dt><dd>{x}</dd>" for k, x in facts) + "</dl>"
    notes = [n for n in v.get("notes", []) if n not in of and n not in give]
    if notes:
        body += "<h3>Notes</h3><ul class=\"list\">" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>"
    near = sorted((dist_m(v, o), o) for o in V if o is not v and not closed(o))[:6]
    body += f"<h2>Near {e(name)}</h2><ul class=\"list\">" + "".join(
        row(o, e(walk(d)) + (f" · {e(nx['title'])} ({e(when_label(nx['date']))})" if (nx := (dated(o, 7) or [None])[0]) else "")) for d, o in near) + "</ul>"
    src = https(v.get("src"))
    body += f'<p class="meta" style="margin-top:22px">Details from {"<a href=%s rel=\"noopener nofollow\">%s</a>" % (e(src), e(re.sub(r"^https?://(www\\.)?", "", src).split("/")[0])) if src else "the venue"}; last checked {e(CHECKED)}. Run {e(name)}? <a href="mailto:{EMAIL}?subject={e("Listing for " + name)}">Send your events</a> or <a href="/for-pubs/#{e(v["id"])}">get a badge for your website</a>.</p>'

    place = {"@context": "https://schema.org", "@type": schema_type(v), "name": name, "url": page_url(path),
             "address": {"@type": "PostalAddress", "streetAddress": v["address"], "addressLocality": "Cambridge",
                         "postalCode": v.get("postcode", ""), "addressCountry": "GB"},
             "geo": {"@type": "GeoCoordinates", "latitude": v["lat"], "longitude": v["lng"]}}
    if https(v.get("website")):
        place["sameAs"] = v["website"]
    ld = [place]
    for x in dd[:15]:
        ld.append({"@context": "https://schema.org", "@type": "Event", "name": x["title"], "startDate": x["date"],
                   "eventStatus": "https://schema.org/EventScheduled", "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                   "location": {"@type": "Place", "name": name, "address": place["address"]}, "url": page_url(path)})
    return path, shell(path, title, desc, body, crumbs=[("Pubs and venues", "/pubs/"), (name, None)], ld=ld, map_link=f"/?p={v['id']}")


# ---------- areas ----------
STATION = {"lat": 52.1946, "lng": 0.1376}
AREAS = [
    ("city-centre", "City centre", "Pubs in Cambridge city centre",
     "Pubs and bars in the middle of Cambridge, around the market, King's Parade, Bene't Street, Bridge Street and St Andrew's Street.",
     ["chop-house", "cwm-kings-parade", "ivy", "mitre", "baron-of-beef", "bridge-street-wine-bar", "kiki", "cambridge-tap", "regal", "castle-bar",
      "revolution", "bar-oh", "vinyl", "town-gown", "mash", "pint-shop", "brewboard", "corn-exchange", "eagle", "smokeworks", "bath-house",
      "orator", "maypole", "hidden-rooms", "byrons-bear", "mill", "anchor", "north-star"]),
    ("mill-road", "Mill Road", "Mill Road pubs: Mill Road and Petersfield",
     "Pubs on and around Mill Road, from the Six Bells and the Kingston Arms to the Cambridge Blue and the Royal Standard.",
     ["white-swan", "devonshire-arms", "salisbury-arms", "live-let-live", "six-bells", "cambridge-blue", "hot-numbers", "alexandra-arms",
      "kingston-arms", "calverleys", "geldart", "petersfield", "dobblers", "earl-beaconsfield", "empress", "royal-standard", "brook", "blue-moon"]),
    ("king-street", "King Street and the Kite", "King Street pubs and the Kite",
     "King Street's run of pubs plus the back streets of the Kite, including the Free Press and the Elm Tree.",
     ["free-press", "tram-depot", "cricketers", "elm-tree", "st-radegund", "king-street-cellar", "brew-house", "champion", "king-street-run",
      "darrys", "handsome-prince"]),
    ("newmarket-road", "Newmarket Road", "Newmarket Road pubs",
     "Pubs along Newmarket Road from the Burleigh Arms out to the Wrestlers, plus the Riverside.",
     ["burleigh-arms", "bird-or-worm", "engineers-house", "wrestlers", "seven-stars", "corner-house", "navadhanya"]),
    ("chesterton", "Chesterton and the river", "Chesterton pubs: Chesterton Road, the river and Chesterton village",
     "Pubs along Chesterton Road and by the river at Midsummer Common, out to the old village pubs in Chesterton.",
     ["thirsty", "fort-st-george", "midsummer-house", "old-spring", "haymakers", "green-dragon", "stem-glory", "boathouse", "waterman",
      "tivoli", "portland-arms"]),
    ("castle-hill", "Castle Hill and Histon Road", "Castle Hill pubs: Castle Street, Magdalene Street and Histon Road",
     "Pubs up Castle Hill and Magdalene Street and on towards Histon Road and Victoria Road.",
     ["pickerel", "architect", "castle-inn", "sir-isaac-newton", "kettles-yard", "carpenters-arms", "grapes"]),
    ("regent-street", "Regent Street and Hills Road", "Regent Street and Hills Road pubs",
     "Pubs and bars along Regent Street and Hills Road, plus the Panton Arms and the Alma in the streets between.",
     ["grain-hop", "parkers-tavern", "prince-regent", "novi", "old-bicycle-shop", "the-lab", "panton-arms", "alma", "emperor", "earl-of-derby"]),
    ("newnham", "Newnham", "Newnham pubs", "Pubs in Newnham and along Barton Road, a short walk over the river from the centre.",
     ["granta", "millworks", "red-bull"]),
    ("grantchester", "Grantchester", "Grantchester pubs",
     "Grantchester's four pubs, a walk across the meadows or a punt up the river from Cambridge.",
     ["red-lion-grantchester", "green-man-grantchester", "rupert-brooke", "blue-ball"]),
    ("trumpington", "Trumpington", "Trumpington pubs", "Pubs in Trumpington village on the south side of Cambridge.",
     ["green-man-trumpington", "hudsons", "lord-byron"]),
    ("cherry-hinton", "Cherry Hinton and the south-east", "Cherry Hinton pubs and the south-east of Cambridge",
     "Pubs in Cherry Hinton and along Cherry Hinton Road, plus Queen Edith's and Perne Road.",
     ["robin-hood", "red-lion-cherry-hinton", "rock", "cwm-cherry-hinton-road", "queen-edith", "dumpling-tree", "junction"]),
    ("fen-ditton", "Fen Ditton", "Fen Ditton pubs", "The three pubs in Fen Ditton, just across the river from Cambridge.",
     ["kings-head-fen-ditton", "ancient-shepherds", "plough-fen-ditton"]),
    ("north-cambridge", "North Cambridge", "North Cambridge pubs: Arbury, Kings Hedges and Milton Road",
     "Pubs in the north of the city, around Arbury, Kings Hedges and Milton Road.",
     ["golden-hind", "hickorys", "carlton-arms", "ship"]),
    ("eddington", "Eddington", "Eddington bars and venues", "Bars and venues in Eddington, the new neighbourhood in north-west Cambridge.",
     ["storeys-field", "starman", "douce"]),
]


def area_body(vs, near_station=False):
    vs = [v for v in vs if not closed(v)]
    items = []
    for v in vs:
        bits = []
        if near_station:
            bits.append(walk(dist_m(STATION, v)) + " from the station")
        bits.append(f'{v["address"]}, {v.get("postcode", "")}'.strip(", "))
        q = [w for w in weekly(v) if is_kind(w, ("quiz",))]
        if q:
            bits.append("Quiz " + " and ".join(DAYLONG[w["day"]] + "s" for w in q[:2]))
        am = [k for k, lab in (("garden", "beer garden"), ("fire", "real fire"), ("sport", "sport on TV"), ("dogs", "dogs welcome")) if amen(v, k)]
        if am:
            bits.append(", ".join(lab for k, lab in (("garden", "beer garden"), ("fire", "real fire"), ("sport", "sport on TV"), ("dogs", "dogs welcome")) if k in am))
        items.append(row(v, e(" · ".join(bits))))
    out = f'<p class="meta">{len(vs)} places</p><section class="grp0"><ul class="list">' + "".join(items) + "</ul></section>"
    week = ""
    for i in range(7):
        d = (TODAY + dt.timedelta(i)).isoformat()
        rows = [(v, x) for v in vs for x in on_day(v, d) if x.get("kind") not in ("sport",)]
        rows.sort(key=lambda r: (0 if r[1].get("kind") in ("music", "classical") else 1 if r[1].get("kind") in ("quiz", "comedy", "club") else 2, r[0]["name"]))
        if rows:
            week += grp(e(when_label(d) if i < 2 else fmt_date(d, True)), [row(v, e(x["title"]), "", KINDNAME.get(x.get("kind"), ""), dn_of(d)) for v, x in rows])
    if week:
        out += "<h2>On this week</h2>" + daybar(week) + week
    return out


def build_areas(pages):
    cards = []
    for slug, label, title, intro, ids in AREAS:
        vs = [BYID[i] for i in ids if i in BYID]
        if not vs:
            continue
        path = f"/areas/{slug}/"
        others = " · ".join(f'<a href="/areas/{s}/">{e(l)}</a>' for s, l, *_ in AREAS if s != slug)
        body = f"<h1>{e(title)}</h1><p class=\"lede\">{e(intro)}</p>" + area_body(vs) + f'<h2>Other areas</h2><p>{others} · <a href="/areas/near-the-station/">Near the station</a></p>'
        desc = f"{len(vs)} pubs and bars in {label}, Cambridge, with quiz nights, beer gardens and what's on this week, checked twice a week."
        write(path, shell(path, f"{title} | Smiff's Cambridge Compass", desc, body, crumbs=[("Areas", "/areas/"), (label, None)]))
        pages.append(path)
        cards.append((path, label, len(vs)))
    near = sorted((v for v in V if not closed(v) and dist_m(STATION, v) <= 1100 and "classical" not in v["cats"][:1]), key=lambda v: dist_m(STATION, v))
    path = "/areas/near-the-station/"
    body = ("<h1>Pubs near Cambridge station</h1><p class=\"lede\">Pubs and bars within about a 15-minute walk of Cambridge railway station, nearest first, "
            "for a pint before your train or the first stop on a night out.</p>" + area_body(near, near_station=True))
    write(path, shell(path, "Pubs near Cambridge station | Smiff's Cambridge Compass",
                      f"{len(near)} pubs within a 15-minute walk of Cambridge railway station, nearest first, with walking times and what's on.",
                      body, crumbs=[("Areas", "/areas/"), ("Near the station", None)]))
    pages.append(path)
    cards.insert(1, (path, "Near the station", len(near)))
    lis = "".join(f'<li><span class="n"><a href="{p}">{e(l)}</a></span><span class="sub">{n} places</span></li>' for p, l, n in cards)
    body = "<h1>Cambridge pubs by area</h1><p class=\"lede\">Find a pub near you, or plan a night out in one part of town.</p>" + f'<ul class="list">{lis}</ul>'
    write("/areas/", shell("/areas/", "Cambridge pubs by area | Smiff's Cambridge Compass",
                           "Cambridge pubs by area: the city centre, Mill Road, King Street, Chesterton, Grantchester, near the station and more.",
                           body, crumbs=[("Areas", None)]))
    pages.append("/areas/")


# ---------- for pubs: badge ----------
def build_for_pubs(pages):
    path = "/for-pubs/"
    opts = "".join(f'<option value="{e(v["id"])}">{e(v["name"])}</option>' for v in V)
    body = f"""<h1>Put Smiff&rsquo;s Compass on your website</h1>
<p class="lede">Every pub and venue on the map has its own page with your opening hours, quiz nights, deals and what&rsquo;s on. Link to it from your website, Linktree or Instagram bio and your customers can see everything in one place.</p>
<p><img src="/badge.png" alt="Find us on Smiff&rsquo;s Compass" width="275" height="72"></p>
<h2>1. Pick your pub</h2>
<p><label for="pub" class="meta">Your pub or venue</label><br><select id="pub" style="font:inherit;font-size:1rem;padding:10px 12px;border:2px solid var(--edge);border-radius:10px;background:var(--panel);color:var(--ink);max-width:100%"><option value="">Choose&hellip;</option>{opts}</select></p>
<div id="out" hidden>
<h2>2. Your page</h2>
<p><a id="link" href="/"></a></p>
<h2>3. Add the badge to your website</h2>
<p>Paste this where you want the badge, for example in your footer or on your &ldquo;What&rsquo;s on&rdquo; page:</p>
<textarea id="code" readonly rows="5" style="width:100%;font:14px/1.4 ui-monospace,monospace;padding:10px;border:2px solid var(--edge);border-radius:10px;background:var(--soft);color:var(--ink)"></textarea>
<p><button type="button" id="copy" class="cta" style="font:inherit;font-weight:700;cursor:pointer">Copy the code</button> <span id="done" class="meta" aria-live="polite"></span></p>
<h2>Linktree or Instagram</h2>
<p>Add your page link above as a link called &ldquo;What&rsquo;s on&rdquo;. If your link tool takes an image, <a href="/badge.png" download>download the badge</a>.</p>
</div>
<h2>Keep your listing up to date</h2>
<p>Send your gigs, quiz nights and deals to <a href="mailto:{EMAIL}">{EMAIL}</a> and they&rsquo;ll go on your page and the map for free.</p>
<script>(function(){{var s=document.getElementById("pub"),o=document.getElementById("out"),l=document.getElementById("link"),c=document.getElementById("code"),d=document.getElementById("done");
function upd(){{var id=s.value;o.hidden=!id;if(!id)return;var u="{SITE}/pubs/"+id+"/";l.href=u;l.textContent=u;
c.value='<a href="'+u+'"><img src="{SITE}/badge.png" alt="Find us on Smiff\\u2019s Compass" width="275" height="72"></a>';d.textContent="";try{{history.replaceState(null,"","#"+id)}}catch(e){{}}}}
s.addEventListener("change",upd);document.getElementById("copy").addEventListener("click",function(){{c.select();var ok=false;try{{navigator.clipboard.writeText(c.value);ok=true}}catch(e){{try{{ok=document.execCommand("copy")}}catch(e2){{}}}}d.textContent=ok?"Copied":"Select the code and copy it"}});
var h=location.hash.slice(1);if(h&&s.querySelector('option[value="'+h+'"]')){{s.value=h;upd()}}}})()</script>"""
    write(path, shell(path, "Find us on Smiff's Compass: a free badge for Cambridge pubs",
                      "A free badge and link for Cambridge pubs and venues to show their events, quiz nights and deals on Smiff's Compass.",
                      body, crumbs=[("For pubs", None)]))
    pages.append(path)


# ---------- site menu (used on every guide page and injected into the app's header) ----------
NAV_CSS = """
.sn-btn{display:inline-grid;place-items:center;width:44px;height:44px;flex:none;border:2px solid var(--edge,#161616);border-radius:12px;background:var(--panel,#FFFDF8);color:var(--ink,#161616);cursor:pointer;padding:0}
.sn-btn svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:2.4;stroke-linecap:round}
.sn-btn[aria-expanded="true"]{background:var(--pop,#FFD23F);color:#161616}
.sn-scrim{position:fixed;inset:0;z-index:2000;background:rgb(0 0 0/.35)}
.sn-panel{position:fixed;top:0;right:0;bottom:0;z-index:2001;width:min(360px,88vw);overflow:auto;overscroll-behavior:contain;background:var(--panel,#FFFDF8);color:var(--ink,#161616);border-left:2px solid var(--edge,#161616);padding:12px 12px calc(24px + env(safe-area-inset-bottom,0px));font-family:var(--body,system-ui);animation:sn-in .2s ease-out}
@keyframes sn-in{from{transform:translateX(24px);opacity:0}to{transform:none;opacity:1}}
@media (prefers-reduced-motion:reduce){.sn-panel{animation:none}}
.sn-head{display:flex;align-items:center;justify-content:space-between;padding:4px 4px 10px;border-bottom:2px solid var(--edge,#161616);margin-bottom:6px}
.sn-head b{font:800 1.3rem/1.1 var(--display,system-ui)}
.sn-x{all:unset;cursor:pointer;width:40px;height:40px;display:grid;place-items:center;border-radius:10px;font-size:1.6rem;line-height:1}
.sn-x:focus-visible,.sn-panel a:focus-visible,.sn-tg:focus-visible{outline:3px solid var(--pop,#FFD23F);outline-offset:1px}
.sn-panel ul{list-style:none;margin:0;padding:0}
.sn-panel li{border-bottom:1.5px dashed var(--line,#DDD5C4)}
.sn-panel li li{border:0}
.sn-r{display:flex;align-items:stretch;min-height:48px}
.sn-r>a,.sn-r>.sn-tg.full{flex:1;display:flex;align-items:center;padding:6px 8px;font-weight:700;font-size:1.02rem;color:inherit;text-decoration:none;text-align:left}
.sn-tg{all:unset;box-sizing:border-box;cursor:pointer;min-width:48px;display:grid;place-items:center}
.sn-tg svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round;transition:transform .18s}
.sn-tg[aria-expanded="true"] svg{transform:rotate(90deg)}
.sn-tg.full{justify-content:space-between;display:flex}
.sn-sub{padding:0 0 8px 14px}
.sn-sub a{display:flex;align-items:center;min-height:40px;padding:2px 8px;color:inherit;text-decoration:none;font-size:.96rem;border-radius:8px}
.sn-sub a:hover,.sn-r>a:hover{background:var(--soft,#F5EFE2)}
.sn-sub a .t{margin-left:8px;font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;background:var(--pop,#FFD23F);color:#161616;border-radius:999px;padding:1px 7px}
"""

NAV_JS = """(function(){var b=document.getElementById("sn-btn"),p=document.getElementById("sn-panel"),s=document.getElementById("sn-scrim");if(!b||!p)return;
function open(o){p.hidden=!o;s.hidden=!o;b.setAttribute("aria-expanded",o?"true":"false");document.documentElement.style.overflow=o?"hidden":"";if(o){var f=p.querySelector(".sn-x");f&&f.focus()}else b.focus()}
b.addEventListener("click",function(){open(p.hidden)});s.addEventListener("click",function(){open(false)});
p.addEventListener("click",function(e){var t=e.target.closest(".sn-tg");if(t){var u=document.getElementById(t.getAttribute("aria-controls"));var x=t.getAttribute("aria-expanded")!=="true";t.setAttribute("aria-expanded",x?"true":"false");u.hidden=!x;return}
if(e.target.closest(".sn-x")){open(false);return}if(e.target.closest("a"))open(false)});
document.addEventListener("keydown",function(e){if(e.key==="Escape"&&!p.hidden){e.stopPropagation();open(false)}},true)})();"""

ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7"/></svg>'
BURGER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>'


def nav_html():
    today = DAYS[TODAY.weekday()]

    def days(path, which=DAYS):
        return [(f"{path}#{d.lower()}", DAYLONG[d], d == today) for d in which]

    items = [
        ("This weekend", "/this-weekend/", None),
        ("Live music", "/live-music/", days("/live-music/")),
        ("Pub quizzes", "/pub-quizzes/", days("/pub-quizzes/")),
        ("Sunday roasts", "/sunday-roasts/", days("/sunday-roasts/", ["Sat", "Sun"])),
        ("Pub deals", "/pub-deals/", days("/pub-deals/")),
        ("Occasions", None, [("/christmas/", "Christmas", False), ("/christmas-party-venues/", "Christmas party venues", False),
                             ("/new-years-eve/", "New Year's Eve", False)]),
        ("Pubs with…", None, [("/beer-gardens/", "Beer gardens", False), ("/real-fires/", "Real fires", False),
                             ("/dog-friendly-pubs/", "Dog-friendly", False), ("/live-sport/", "Live sport", False),
                             ("/riverside-pubs/", "Riverside", False), ("/guinness/", "Guinness", False),
                             ("/independent-pubs/", "Independent pubs", False)]),
        ("Areas", "/areas/", [("/areas/near-the-station/", "Near the station", False)] +
         [(f"/areas/{s}/", l, False) for s, l, *_ in AREAS]),
        ("Every pub A to Z", "/pubs/", None),
        ("For pubs: get a badge", "/for-pubs/", None),
    ]
    lis = ""
    for i, (label, href, subs) in enumerate(items):
        sid = f"sn-s{i}"
        if subs:
            sub = "".join(f'<li><a href="{e(h)}">{e(l)}{"<span class=t>Today</span>" if t else ""}</a></li>' for h, l, t in subs)
            if href:
                r = f'<a href="{e(href)}">{e(label)}</a><button type="button" class="sn-tg" aria-expanded="false" aria-controls="{sid}" aria-label="Show {e(label.lower())} options">{ARROW}</button>'
            else:
                r = f'<button type="button" class="sn-tg full" aria-expanded="false" aria-controls="{sid}"><span>{e(label)}</span>{ARROW}</button>'
            lis += f'<li><div class="sn-r">{r}</div><ul class="sn-sub" id="{sid}" hidden>{sub}</ul></li>'
        else:
            lis += f'<li><div class="sn-r"><a href="{e(href)}">{e(label)}</a></div></li>'
    return (f'<button type="button" class="sn-btn" id="sn-btn" aria-expanded="false" aria-controls="sn-panel" aria-label="Menu">{BURGER}</button>'
            f'<div class="sn-scrim" id="sn-scrim" hidden></div>'
            f'<nav class="sn-panel" id="sn-panel" aria-label="Guides" hidden><div class="sn-head"><b>Explore</b><button type="button" class="sn-x" aria-label="Close menu">&times;</button></div>'
            f'<ul><li><div class="sn-r"><a href="/">The map</a></div></li>{lis}</ul></nav>')


def inject_app_nav():
    """Keep the menu in the app (index.html) in step with the guides, between marker comments."""
    fp = os.path.join(ROOT, "index.html")
    s = open(fp, encoding="utf-8").read()
    a, b = "<!--SITE-NAV-->", "<!--/SITE-NAV-->"
    if a not in s or b not in s:
        return
    block = a + f'<style>{NAV_CSS.strip()}</style>' + nav_html() + f"<script>{NAV_JS}</script>" + b
    s2 = s[:s.index(a)] + block + s[s.index(b) + len(b):]
    if s2 != s:
        open(fp, "w", encoding="utf-8").write(s2)


# ---------- build ----------
def main():
    specs = guide_spec()
    pages = []
    # clean old venue pages
    pub_dir = os.path.join(ROOT, "pubs")
    if os.path.isdir(pub_dir):
        keep = {v["id"] for v in V}
        for d in os.listdir(pub_dir):
            if os.path.isdir(os.path.join(pub_dir, d)) and d not in keep:
                shutil.rmtree(os.path.join(pub_dir, d))
    with open(os.path.join(ROOT, "pages.css"), "w", encoding="utf-8") as f:
        f.write(CSS.strip() + "\n" + NAV_CSS.strip() + "\n")
    for path, label, title, desc, intro, build in specs:
        ld = []
        main_html = build(ld)
        body = f"<h1>{e(title)}</h1><p class=\"lede\">{e(intro)}</p>" + daybar(main_html) + main_html
        body += f'<div class="box pop"><p><strong>See it all on the map:</strong> gigs, quizzes and deals for every Cambridge pub, with what&rsquo;s open now. <a href="/">Open Smiff&rsquo;s Compass</a></p></div>'
        write(path, shell(path, title, desc, body, crumbs=[(label, None)]))
        pages.append(path)
    # A to Z
    lis = "".join(f'<li>{vlink(v)} <span class="sub">{e(kind_of_place(v))} · {e(v["address"])}</span></li>' for v in V)
    body = (f"<h1>Every pub and venue on Smiff&rsquo;s Compass</h1><p class=\"lede\">All {len(V)} Cambridge pubs, bars and venues on the map, A to Z. Each page has opening hours, food, quiz nights and what&rsquo;s on.</p>"
            f'<ul class="list az">{lis}</ul>')
    write("/pubs/", shell("/pubs/", "Cambridge pubs and venues A to Z | Smiff's Cambridge Compass",
                          f"All {len(V)} Cambridge pubs, bars and venues on Smiff's Compass, with opening hours, quiz nights, food and what's on.",
                          body, crumbs=[("Pubs and venues", None)]))
    pages.append("/pubs/")
    build_areas(pages)
    build_for_pubs(pages)
    for v in V:
        path, doc = venue_page(v)
        write(path, doc)
        pages.append(path)
    inject_app_nav()
    urls = ["/"] + pages
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
        f"  <url><loc>{page_url(u)}</loc><lastmod>{T0}</lastmod></url>\n" for u in urls) + "</urlset>\n"
    with open(os.path.join(ROOT, "sitemap.xml"), "w") as f:
        f.write(sm)
    with open(os.path.join(ROOT, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n")
    print(f"Built {len(pages)} pages for {T0}")


if __name__ == "__main__":
    main()
