#!/usr/bin/env python3
"""Antiques enrichment from The Metropolitan Museum of Art Open Access.

The Met's Collection API is the primary source (all metadata CC0), so
unlike mirror harvests every field here is authoritative at origin:
culture, period/objectDate, medium, and measurements are taken
verbatim from the API response — no third-party rewriting to correct.

Mapping is strictly onto the antiques fixture's existing vocabulary:

  culture   only China / Japan / Korea (the corpus's cultural spheres)
  period    a dynasty/era member whose name appears in the objectDate
            or period field (Shang...Meiji)
  category  keyword classification of objectName/title/medium onto the
            AntiqueCategory members (Ceramics, Bronze, Jade,
            PaintingCalligraphy, Furniture, Lacquer, CloisonneEnamel,
            BuddhistSculpture, SnuffBottle, UkiyoEPrint)
  height /  cm measurements from the API's measurements array
  diameter

Objects that do not map cleanly onto that vocabulary are skipped —
accuracy over volume. Output is a generated CDDAL section between
markers for idempotent splicing into the antiques fixture.

Reads:    nothing on disk (queries the Met API)
Writes:   harvest/out/met_bulk.cddal
"""

import json
import re
import time
import urllib.request

BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OUT = "harvest/out/met_bulk.cddal"
BEGIN = "# ==== BEGIN MET MUSEUM BULK REGISTRY (generated - do not hand-edit) ===="
END = "# ==== END MET MUSEUM BULK REGISTRY ===="

CULTURES = {"China": "China", "Japan": "Japan", "Korea": "Korea"}
PERIODS = ["Shang", "Zhou", "Han", "Tang", "Song", "Yuan", "Ming", "Qing",
           "Goryeo", "Joseon", "Edo", "Meiji"]

CATEGORY_RULES = [
    ("SnuffBottle", r"snuff bottle"),
    ("UkiyoEPrint", r"ukiyo-?e|woodblock print|polychrome woodblock"),
    ("CloisonneEnamel", r"cloisonn[ée]"),
    ("BuddhistSculpture", r"buddha|bodhisattva|buddhist|guanyin|bodhisattva"),
    ("PaintingCalligraphy", r"screen|hanging scroll|handscroll|album leaf|"
                            r"ink and colou?r on|calligraph"),
    ("Jade", r"\bjade\b|nephrite"),
    ("Bronze", r"\bbronze\b"),
    ("Lacquer", r"lacquer"),
    ("Furniture", r"table\b|chair\b|cabinet\b|chest\b|stool\b|stand\b"),
    ("Ceramics", r"porcelain|stoneware|earthenware|celadon|ceramic|\bvase\b|\bjar\b|"
                 r"\bbowl\b|\bdish\b|\bcup\b|\bbottle\b|\bewer\b|\bplate\b|\bcenser\b|"
                 r"tile\b|\bfigurine\b"),
]


def get_json(url, attempts=3):
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "opencdd-harvest/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.load(r)
        except Exception as exc:
            if attempt == attempts - 1:
                print("  FAIL %s (%s)" % (url.rsplit("/", 1)[-1], exc), flush=True)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def classify(name, title, medium):
    hay = " ".join(filter(None, [name, title, medium])).lower()
    for cat, pat in CATEGORY_RULES:
        if re.search(pat, hay, re.I):
            return cat
    return None


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').strip()


def main():
    ids = []
    for q in ["ceramic", "bronze", "jade", "screen", "scroll", "buddha",
              "snuff bottle", "cloisonne", "lacquer", "furniture", "print",
              "vase", "jar", "sculpture", "temple", "tomb", "figurine",
              "mirror", "textile", "ding", "korean", "sword", "armor",
              "calligraphy", "incense", "archer's ring", "chicken cup"]:
        d = get_json(f"{SEARCH}?isHighlight=true&departmentId=6&q={urllib.parse.quote(q)}")
        if d and d.get("objectIDs"):
            ids += d["objectIDs"]
        time.sleep(0.5)
    ids = sorted(set(ids))
    print("candidate highlight objects:", len(ids), flush=True)

    objects = []
    seen_missing = 0
    for i, oid in enumerate(ids):
        o = get_json(f"{BASE}/objects/{oid}")
        if o is None:
            continue
        time.sleep(0.35)
        culture = None
        for key, val in CULTURES.items():
            c = (o.get("culture") or "")
            if c.startswith(key) or key in c:
                culture = val
                break
        if culture is None:
            continue
        date_text = " ".join(filter(None, [o.get("objectDate"), o.get("period")]))
        period = next((p for p in PERIODS if re.search(r"\b%s\b" % p, date_text)), None)
        name = (o.get("objectName") or "").strip()
        title = (o.get("title") or "").strip()
        medium = (o.get("medium") or "").strip()
        category = classify(name, title, medium)
        if category is None:
            continue
        height = diameter = None
        for m in o.get("measurements") or []:
            if m.get("unit") != "cm":
                continue
            t = (m.get("type") or "").lower()
            if t == "height" and height is None:
                height = m.get("value")
            if t == "diameter" and diameter is None:
                diameter = m.get("value")
        segs = []
        for seg in [name, medium, o.get("objectDate"),
                    "The Metropolitan Museum of Art, %s" % (o.get("accessionYear") or "")]:
            seg = (seg or "").strip()
            if seg and seg not in segs:
                segs.append(seg)
        definition = "; ".join(segs)
        objects.append({
            "id": oid,
            "title": title or name,
            "category": category,
            "culture": culture,
            "period": period,
            "medium": medium,
            "height": height,
            "diameter": diameter,
            "definition": definition[:240],
        })
        if (i + 1) % 40 == 0:
            print("scanned %d/%d, kept %d" % (i + 1, len(ids), len(objects)), flush=True)

    objects.sort(key=lambda o: o["id"])
    # identical titles collide in the symbol table — keep the first
    # object per title, log the skips
    seen_titles = set()
    deduped = []
    for o in objects:
        key = o["title"].strip().lower()
        if key in seen_titles:
            print("  skip duplicate title: %s (object %d)" % (o["title"], o["id"]))
            continue
        seen_titles.add(key)
        deduped.append(o)
    objects = deduped
    lines = [BEGIN, "#",
             "# Registered individuals - The Metropolitan Museum of Art, Open Access (CC0)",
             "#",
             "# Highlighted objects from the Asian Art department, retrieved %s." % __import__("datetime").date.today().isoformat(),
             "# Every field is taken verbatim from the Met Collection API (the",
             "# primary source): culture, period/objectDate, medium, and cm",
             "# measurements. Objects outside the corpus's cultural spheres or",
             "# vocabulary are excluded. Regenerate via `rake browser:harvest_met`.",
             "#",
             "# The Metropolitan Museum of Art: Open Access policy, CC0 1.0",
             "# (https://www.metmuseum.org/about-the-met/policies-and-documents/open-access).",
             "", ""]
    for i, o in enumerate(objects):
        ident = "Met%d" % o["id"]
        lines += [f"instance {ident} < MDC_C002 {{",
                  f"  code: ANI{13 + i:03d}",
                  f'  preferred_name.en: "{esc(o["title"][:100])}"',
                  f'  definition.en: "{esc(o["definition"])}"',
                  "  superclass: " + o["category"],
                  "  class_type: ITEM_CLASS",
                  f"  category: {o['category']}",
                  f"  culture: {o['culture']}"]
        if o["period"]:
            lines.append(f"  period: {o['period']}")
        if o["height"] is not None:
            lines.append(f"  height: {o['height']}")
        if o["diameter"] is not None:
            lines.append(f"  diameter: {o['diameter']}")
        lines += ["}", ""]
    section = "\n".join(lines).rstrip("\n") + "\n" + END + "\n"
    import os
    os.makedirs("harvest/out", exist_ok=True)
    open(OUT, "w").write(section)
    print("kept %d Met objects -> %s" % (len(objects), OUT))


if __name__ == "__main__":
    import urllib.parse
    main()
