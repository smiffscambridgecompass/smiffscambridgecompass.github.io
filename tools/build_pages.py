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
<header class="top"><div class="wrap"><a class="brand" href="/"><img src="/favicon.svg" alt="" width="36" height="36"><span>Smiff&rsquo;s Cambridge Compass</span></a><a class="cta" href="{e(map_link)}">Open the map</a></div></header>
<main class="wrap">
{crumb_html}
{body}
</main>
<footer class="foot"><div class="wrap">
<h2>Guides to Cambridge pubs</h2>
<ul class="guides">{guides}<li><a href="/pubs/">Every place A to Z</a></li></ul>
<p>Smiff&rsquo;s Cambridge Compass is a free map of what&rsquo;s on in Cambridge pubs, made by a local pub-goer. Listings come from venue websites, CAMRA and event listings, and are checked twice a week (last checked {e(CHECKED)}). Times and deals can change, so check with the pub before a big night out.</p>
<p>Run a pub or venue? Send your events to <a href="mailto:{EMAIL}">{EMAIL}</a> and they&rsquo;ll go on the map for free.</p>
</div></footer>
</body>
</html>
"""


def write(path, content):
    fp = os.path.join(ROOT, path.strip("/"), "index.html") if path.endswith("/") else os.path.join(ROOT, path.strip("/"))
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(content)


def row(v, detail="", when="", kind=""):
    w = f'<span class="w">{e(when)}</span> ' if when else ""
    k = f'<span class="k">{e(kind)}</span>' if kind else ""
    return f'<li>{w}<span class="n">{vlink(v)}</span>{k}<span class="sub">{detail}</span></li>'


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
            out += f"<h2>{e(fmt_date(d, True))}</h2><ul class=\"list\">" + "".join(
                row(v, e(x["title"]) + (" <em>(every week)</em>" if x.get("weekly") else ""), "", KINDNAME.get(x.get("kind"), "")) for *_, v, x in rows[:40]) + "</ul>"
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
                out += f"<h2>{DAYLONG[dn]} quiz nights</h2><ul class=\"list\">" + "".join(row(v, e(w["title"]) + f' · {addr(v)}') for v, w in rows) + "</ul>"
        once = sorted([(x["date"], v, x) for v in V for x in dated(v, 60) if is_kind(x, ("quiz",))], key=lambda r: (r[0], r[1]["name"]))
        if once:
            out += "<h2>Monthly and one-off quizzes</h2><ul class=\"list\">" + "".join(row(v, e(x["title"]), when_label(d)) for d, v, x in once) + "</ul>"
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
                out += f"<h2>{e(when_label(d) if i < 2 else fmt_date(d, True))}</h2><ul class=\"list\">" + "".join(
                    row(v, e(x["title"]), "", "Classical" if x.get("kind") == "classical" else "") for v, x in rows) + "</ul>"
        reg = [(v, w) for v in V if not closed(v) for w in weekly(v) if is_kind(w, ("music",))]
        if reg:
            out += "<h2>Regular live music nights</h2><ul class=\"list\">" + "".join(
                row(v, e(w["title"]), "Every " + DAYLONG.get(w["day"], w["day"])) for v, w in reg) + "</ul>"
        return out

    add("/live-music/", "Live music", "Live music in Cambridge pubs and venues: gigs for the next two weeks",
        "Gigs and live music in Cambridge pubs, bars and venues for the next two weeks, plus the pubs with a regular music night.",
        "Every gig we know about in Cambridge pubs and venues for the next two weeks, then the pubs with a regular live music night.", b_music)

    # sunday roasts
    roast = re.compile(r"roast|carvery|sunday lunch", re.I)

    def b_roast(ld):
        rows = [(v, w) for v in V if not closed(v) for w in weekly(v) if w.get("day") == "Sun" and roast.search(w["title"])]
        rows += [(v, {"title": o}) for v in V if not closed(v) for o in offers(v) if roast.search(o) and not any(r[0] is v for r in rows)]
        return '<ul class="list">' + "".join(row(v, e(w["title"]) + f" · {addr(v)}") for v, w in rows) + "</ul>"

    add("/sunday-roasts/", "Sunday roasts", "Sunday roasts in Cambridge pubs",
        "Where to get a Sunday roast in a Cambridge pub, with prices and serving times where the pub lists them.",
        "Cambridge pubs serving a Sunday roast, with prices and kitchen times where the pub lists them. Booking is a good idea at the popular ones.", b_roast)

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
                out += f"<h2>{DAYLONG[dn]}</h2><ul class=\"list\">" + "".join(row(v, e(w["title"])) for v, w in rows) + "</ul>"
        rest = [(v, o) for v in V if not closed(v) for o in offers(v) if not re.search(r"christmas|festive|new year", o, re.I)]
        if rest:
            out += "<h2>Other deals</h2><ul class=\"list\">" + "".join(row(v, e(o)) for v, o in rest) + "</ul>"
        return out

    add("/pub-deals/", "Pub deals", "Food and drink deals in Cambridge pubs, day by day",
        "Pizza nights, 2-for-1s, happy hours, pie and pint deals and more in Cambridge pubs, sorted by day of the week.",
        "Food and drink deals in Cambridge pubs, sorted by the day they run. Deals change often, so check with the pub before you go.", b_deals)

    xmas = re.compile(r"christmas|festive|carol|mince pie|new year|nye|\bmulled", re.I)

    def b_xmas(ld):
        ev = sorted([(x["date"], v, x) for v in V for x in dated(v) if xmas.search(x["title"])], key=lambda r: (r[0], r[1]["name"]))
        out = ""
        if ev:
            out += "<h2>Christmas and New Year events</h2><ul class=\"list\">" + "".join(row(v, e(x["title"]), fmt_date(d)) for d, v, x in ev) + "</ul>"
        info = [(v, t) for v in V for t in dict.fromkeys(offers(v) + v.get("notes", [])) if xmas.search(t)]
        if info:
            out += "<h2>Festive menus and Christmas opening</h2><ul class=\"list\">" + "".join(row(v, e(t)) for v, t in info) + "</ul>"
        return out or "<p>Nothing festive listed yet. Check back soon.</p>"

    add("/christmas/", "Christmas", f"Christmas in Cambridge pubs {TODAY.year}: events, festive menus and opening times",
        "Christmas and New Year's Eve events, festive menus and Christmas opening times in Cambridge pubs, checked twice a week.",
        "Christmas parties, carols, festive menus, New Year's Eve and Christmas opening times in Cambridge pubs, as the pubs announce them.", b_xmas)
    return specs


# ---------- venue page ----------
def venue_page(v):
    path = f"/pubs/{v['id']}/"
    kp = kind_of_place(v)
    name = v["name"]
    wk, dd, of = weekly(v), dated(v), offers(v)
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
    if facts:
        body += "<h2>Good to know</h2><dl class=\"facts\">" + "".join(f"<dt>{k}</dt><dd>{x}</dd>" for k, x in facts) + "</dl>"
    notes = [n for n in v.get("notes", []) if n not in of]
    if notes:
        body += "<h3>Notes</h3><ul class=\"list\">" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>"
    near = sorted((dist_m(v, o), o) for o in V if o is not v and not closed(o))[:6]
    body += f"<h2>Near {e(name)}</h2><ul class=\"list\">" + "".join(
        row(o, e(walk(d)) + (f" · {e(nx['title'])} ({e(when_label(nx['date']))})" if (nx := (dated(o, 7) or [None])[0]) else "")) for d, o in near) + "</ul>"
    src = https(v.get("src"))
    body += f'<p class="meta" style="margin-top:22px">Details from {"<a href=%s rel=\"noopener nofollow\">%s</a>" % (e(src), e(re.sub(r"^https?://(www\\.)?", "", src).split("/")[0])) if src else "the venue"}; last checked {e(CHECKED)}. Run {e(name)}? <a href="mailto:{EMAIL}?subject={e("Listing for " + name)}">Send your events</a>.</p>'

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
        f.write(CSS.strip() + "\n")
    for path, label, title, desc, intro, build in specs:
        ld = []
        body = f"<h1>{e(title)}</h1><p class=\"lede\">{e(intro)}</p>" + build(ld)
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
    for v in V:
        path, doc = venue_page(v)
        write(path, doc)
        pages.append(path)
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
