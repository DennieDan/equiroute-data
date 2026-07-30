#!/usr/bin/env python3
"""Seed social-style feedback threads for every JalanLens street part.

Uses the frontend publishable Supabase key from earth_accessibility.html without printing it.
Idempotent by checking existing seed title prefixes before inserting.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "earth_accessibility.html").read_text()
url_match = re.search(r'const SUPABASE_URL = "([^"]+)"', HTML)
key_match = re.search(r'const SUPABASE_PUBLISHABLE_KEY =\s*"([^"]+)"', HTML, re.S)
if not url_match or not key_match:
    raise RuntimeError("Could not locate Supabase frontend config")
URL = url_match.group(1)
KEY = key_match.group(1)
HEADERS = {
    "apikey": KEY,
    "Authorization": "Bearer " + KEY,
    "Content-Type": "application/json",
}

TEMPLATES = [
    ("Narrow pavement pinch point", "Wheelchair users may need to slow down here because the clear walking width feels tight during peak-hour crowding."),
    ("Crossing timing feels short", "The crossing feels stressful for seniors and PMA users; a longer green-man phase or clearer waiting area would help."),
    ("Shelter gap during rain", "There is a short exposed stretch where users with mobility aids may have to stop or detour when it rains."),
    ("Wayfinding cue unclear", "Tactile or visual guidance could be clearer so visually impaired commuters know which side of the path to follow."),
    ("Kerb transition needs review", "The kerb/ramp transition should be checked for smoothness because small level changes can block wheelchair movement."),
    ("Crowding near transport node", "This footpath can become crowded near the bus/MRT connection, making it hard for caregivers and PMA users to pass safely."),
]


def request(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = dict(HEADERS)
    if method == "POST":
        headers["Prefer"] = "return=representation"
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
        return json.loads(body) if body else None


def get_rows(table, query):
    return request("GET", f"/rest/v1/{table}?{query}")


def main():
    parts = get_rows("street_parts", "select=id,external_id,metrics&order=external_id.asc")
    existing = get_rows("feedback_threads", "select=street_part_id,title&limit=5000")
    existing_titles = {(r["street_part_id"], r["title"]) for r in existing}
    now = datetime.now(timezone.utc)
    payloads = []
    for i, part in enumerate(parts):
        for j in range(2):
            title, body = TEMPLATES[(i + j) % len(TEMPLATES)]
            part_number = int(part['external_id'].replace('street_part_', '')) + 1 if part['external_id'].startswith('street_part_') else i + 1
            full_title = f"{title} · Footpath {part_number}"
            if (part["id"], full_title) in existing_titles:
                continue
            created = now - timedelta(days=(i % 12), hours=(j * 5 + i) % 24, minutes=(i * 7 + j * 11) % 60)
            score = int(4 + ((i * 3 + j * 5) % 28))
            payloads.append({
                "street_part_id": part["id"],
                "feature_id": None,
                "created_by": None,
                "title": full_title,
                "body": body,
                "status": "open" if (i + j) % 5 else "triaged",
                "priority_score": score,
                "created_at": created.isoformat(),
                "updated_at": created.isoformat(),
            })
    inserted = 0
    for k in range(0, len(payloads), 25):
        batch = payloads[k:k+25]
        if not batch:
            continue
        rows = request("POST", "/rest/v1/feedback_threads", batch)
        inserted += len(rows or batch)
    final = get_rows("feedback_threads", "select=street_part_id&limit=5000")
    covered = {r["street_part_id"] for r in final}
    print(json.dumps({
        "project_ref": URL.split("//",1)[1].split(".",1)[0],
        "street_parts": len(parts),
        "inserted": inserted,
        "feedback_threads_total": len(final),
        "street_parts_with_feedback": len(covered),
    }, indent=2))

if __name__ == "__main__":
    main()
