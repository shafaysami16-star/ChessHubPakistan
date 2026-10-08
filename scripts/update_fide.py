import io, os, sys, zipfile, tempfile
import xml.etree.ElementTree as ET
import requests

FIDE_URL = "https://ratings.fide.com/download/players_list_xml.zip"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

def to_int(v):
    try:
        return int(v) if v and v.strip() else None
    except ValueError:
        return None

def download(path):
    with requests.get(FIDE_URL, stream=True, timeout=300,
                      headers={"User-Agent": "ChessHubPakistan/1.0"}) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)

def parse(zip_path):
    players = []
    with zipfile.ZipFile(zip_path) as z:
        name = z.namelist()[0]
        with z.open(name) as xml_file:
            for _, el in ET.iterparse(xml_file, events=("end",)):
                if el.tag != "player":
                    continue
                if (el.findtext("country") or "").strip() == "PAK":
                    flag = (el.findtext("flag") or "").strip().lower()
                    title = (el.findtext("title") or "").strip() or None
                    players.append({
                        "fide_id": int(el.findtext("fideid")),
                        "name": (el.findtext("name") or "").strip(),
                        "title": title,
                        "standard": to_int(el.findtext("rating")),
                        "rapid": to_int(el.findtext("rapid_rating")),
                        "blitz": to_int(el.findtext("blitz_rating")),
                        "birth_year": to_int(el.findtext("birthday")),
                        "sex": (el.findtext("sex") or "").strip() or None,
                        "active": "i" not in flag,
                    })
                el.clear()  # keep memory low on the big file
    return players

def upsert(rows):
    headers = {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    url = f"{SUPABASE_URL}/rest/v1/fide_players?on_conflict=fide_id"
    for i in range(0, len(rows), 500):
        batch = rows[i:i + 500]
        r = requests.post(url, json=batch, headers=headers, timeout=60)
        if not r.ok:
            print(r.status_code, r.text)
            sys.exit(1)
    print(f"Upserted {len(rows)} Pakistani players")

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        zp = os.path.join(tmp, "fide.zip")
        download(zp)
        rows = parse(zp)
    if len(rows) < 100:  # sanity check so a bad download never wipes/overwrites good data
        print(f"Only {len(rows)} players found, aborting")
        sys.exit(1)
    upsert(rows)
