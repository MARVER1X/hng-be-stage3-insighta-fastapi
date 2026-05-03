from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import time
import re
import httpx

app = FastAPI(title="Insighta Labs API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "profiles.db"

# Country name → ISO 2-letter code mapping (for NLP parser)
COUNTRY_NAME_TO_ID = {
    "nigeria": "NG", "nigerian": "NG",
    "ghana": "GH", "ghanaian": "GH",
    "kenya": "KE", "kenyan": "KE",
    "south africa": "ZA", "south african": "ZA",
    "ethiopia": "ET", "ethiopian": "ET",
    "tanzania": "TZ", "tanzanian": "TZ",
    "uganda": "UG", "ugandan": "UG",
    "angola": "AO", "angolan": "AO",
    "mozambique": "MZ",
    "cameroon": "CM", "cameroonian": "CM",
    "niger": "NE",
    "mali": "ML", "malian": "ML",
    "malawi": "MW", "malawian": "MW",
    "zambia": "ZM", "zambian": "ZM",
    "senegal": "SN", "senegalese": "SN",
    "zimbabwe": "ZW", "zimbabwean": "ZW",
    "guinea": "GN", "guinean": "GN",
    "rwanda": "RW", "rwandan": "RW",
    "benin": "BJ", "beninese": "BJ",
    "burundi": "BI", "burundian": "BI",
    "tunisia": "TN", "tunisian": "TN",
    "somalia": "SO", "somali": "SO",
    "chad": "TD", "chadian": "TD",
    "sierra leone": "SL",
    "togo": "TG", "togolese": "TG",
    "libya": "LY", "libyan": "LY",
    "congo": "CG",
    "democratic republic of congo": "CD",
    "dr congo": "CD", "drc": "CD",
    "central african republic": "CF",
    "liberia": "LR", "liberian": "LR",
    "mauritania": "MR",
    "eritrea": "ER", "eritrean": "ER",
    "namibia": "NA", "namibian": "NA",
    "gambia": "GM", "gambian": "GM",
    "botswana": "BW",
    "gabon": "GA", "gabonese": "GA",
    "lesotho": "LS",
    "algeria": "DZ", "algerian": "DZ",
    "morocco": "MA", "moroccan": "MA",
    "egypt": "EG", "egyptian": "EG",
    "sudan": "SD", "sudanese": "SD",
    "south sudan": "SS",
    "ivory coast": "CI", "côte d'ivoire": "CI", "cote d'ivoire": "CI",
    "burkina faso": "BF",
    "madagascar": "MG", "malagasy": "MG",
    "mauritius": "MU",
    "seychelles": "SC",
    "comoros": "KM",
    "djibouti": "DJ",
    "eswatini": "SZ", "swaziland": "SZ",

    "united states": "US", "usa": "US", "america": "US", "american": "US",
    "united kingdom": "GB", "uk": "GB", "britain": "GB", "british": "GB",
    "france": "FR", "french": "FR",
    "germany": "DE", "german": "DE",
    "italy": "IT", "italian": "IT",
    "spain": "ES", "spanish": "ES",
    "portugal": "PT", "portuguese": "PT",
    "brazil": "BR", "brazilian": "BR",
    "india": "IN", "indian": "IN",
    "china": "CN", "chinese": "CN",
    "japan": "JP", "japanese": "JP",
    "russia": "RU", "russian": "RU",
    "canada": "CA", "canadian": "CA",
    "australia": "AU", "australian": "AU",
    "mexico": "MX", "mexican": "MX",
}

COUNTRY_ID_TO_NAME = {
    v: k.title() for k, v in COUNTRY_NAME_TO_ID.items()
}

# UUID v7 generator
def generate_uuid_v7() -> str:
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")

    uuid_int = (
        (ts_ms & 0xFFFFFFFFFFFF) << 80 |
        (0x7 << 76) |
        ((rand >> 50) & 0xFFF) << 64 |
        (0b10 << 62) |
        (rand & 0x3FFFFFFFFFFFFFFF)
    )

    h = format(uuid_int, "032x")
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"



# Time helper
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Age grouping
def get_age_group(age: int) -> str:
    if age <= 12:
        return "child"
    if age <= 19:
        return "teenager"
    if age <= 59:
        return "adult"
    return "senior"


# DB connection
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# DB schema init
def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            gender TEXT,
            gender_probability REAL,
            age INTEGER,
            age_group TEXT,
            country_id TEXT,
            country_name TEXT,
            country_probability REAL,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()

# Fast lookup helpers 
def row_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "gender": row["gender"],
        "gender_probability": row["gender_probability"],
        "age": row["age"],
        "age_group": row["age_group"],
        "country_id": row["country_id"],
        "country_name": row["country_name"],
        "country_probability": row["country_probability"],
        "created_at": row["created_at"],
    }

# Global error format helper
def error(message: str, code: int):
    return JSONResponse(
        status_code=code,
        content={
            "status": "error",
            "message": message
        }
    )

# Create profile end point
@app.post("/api/profiles")
async def create_profile(body: dict):
    # Name is extracted to enable validation.
    name = body.get("name")

    if not name:
        return error("Missing or empty name", 400)

    if not isinstance(name, str):
        return error("name must be a string", 422)

    # Input is normalized for lookup consistency.
    name = name.strip().lower()

    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM profiles WHERE name = ?", (name,)
    ).fetchone()

    # Database is checked to avoid redundant API calls.
    if existing:
        conn.close()
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Profile already exists",
                "data": row_to_dict(existing)
            }
        )

    # External data is fetched to enrich the profile.
    async with httpx.AsyncClient() as client:
        try:
            g = await client.get("https://api.genderize.io", params={"name": name})
            a = await client.get("https://api.agify.io", params={"name": name})
            n = await client.get("https://api.nationalize.io", params={"name": name})

            g_data = g.json()
            a_data = a.json()
            n_data = n.json()

        except Exception:
            return error("External API failure", 502)

    # Responses are validated to ensure data integrity.
    if not g_data.get("gender") or not a_data.get("age"):
        return error("Invalid API response", 502)

    countries = n_data.get("country", [])
    if not countries:
        return error("Invalid API response", 502)

    # Top country is isolated to identify nationality.
    top_country = max(countries, key=lambda x: x["probability"])

    created_at = utc_now()
    profile_id = generate_uuid_v7()

    # Profile is persisted for permanent storage.
    conn.execute("""
        INSERT INTO profiles (
            id, name, gender, gender_probability, age, age_group,
            country_id, country_name, country_probability, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        profile_id,
        name,
        g_data["gender"],
        g_data["probability"],
        a_data["age"],
        get_age_group(a_data["age"]),
        top_country["country_id"],
        COUNTRY_ID_TO_NAME.get(
            top_country["country_id"],
            top_country["country_id"]
        ),
        top_country["probability"],
        created_at
    ))
    
    conn.commit()

    row = conn.execute(
        "SELECT * FROM profiles WHERE id = ?", (profile_id,)
    ).fetchone()

    conn.close()

    # Created record is returned for client confirmation.
    return JSONResponse(
        status_code=201,
        content={
            "status": "success",
            "data": row_to_dict(row)
        }
    )

# NLP Parser
def parse_natural_language_query(q: str):
    filters = {}
    q_lower = q.lower()
    tokens = set(q_lower.split())

    # Gender (handle both case properly)
    male_words = {"male", "males", "man", "men", "boy", "boys"}
    female_words = {"female", "females", "woman", "women", "girl", "girls"}

    has_male = bool(tokens & male_words)
    has_female = bool(tokens & female_words)

    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"

    # Age groups
    if bool(tokens & {"child", "children", "kids"}):
        filters["age_group"] = "child"
    elif bool(tokens & {"teens","teenager", "teenagers"}):
        filters["age_group"] = "teenager"
    elif bool(tokens & {"adult", "adults"}):
        filters["age_group"] = "adult"
    elif bool(tokens & {"senior", "seniors", "elder", "elders", "old", "elderly"}):
        filters["age_group"] = "senior"

    # Young (16–24)
    if "young" in tokens:
        filters["min_age"] = 16
        filters["max_age"] = 24

    # Above / Below
    above = re.search(r"(above|over)\s+(\d+)", q_lower)
    if above:
        filters["min_age"] = int(above.group(2))

    below = re.search(r"(below|under)\s+(\d+)", q_lower)
    if below:
        filters["max_age"] = int(below.group(2))

    # Country (simple match)
    for name, code in sorted(COUNTRY_NAME_TO_ID.items(), key=lambda x: -len(x[0])):
        if name in q_lower:
            filters["country_id"] = code
            break

    return filters if filters else None

# Query builder
def build_profile_query(
    gender=None,
    age_group=None,
    country_id=None,
    min_age=None,
    max_age=None,
    min_gender_probability=None,
    min_country_probability=None,
    sort_by="created_at",
    order="asc"
):
    where = []
    params = []

    if gender:
        where.append("LOWER(gender) = ?")
        params.append(gender.lower())

    if age_group:
        where.append("LOWER(age_group) = ?")
        params.append(age_group.lower())

    if country_id:
        where.append("LOWER(country_id) = ?")
        params.append(country_id.lower())

    if min_age is not None:
        where.append("age >= ?")
        params.append(min_age)

    if max_age is not None:
        where.append("age <= ?")
        params.append(max_age)

    if min_gender_probability is not None:
        where.append("gender_probability >= ?")
        params.append(min_gender_probability)

    if min_country_probability is not None:
        where.append("country_probability >= ?")
        params.append(min_country_probability)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    allowed_sort = {"age", "created_at", "gender_probability"}
    sort_by = sort_by if sort_by in allowed_sort else "created_at"

    order = "ASC" if order.lower() != "desc" else "DESC"

    count_q = f"SELECT COUNT(*) FROM profiles {where_sql}"

    data_q = f"""
        SELECT * FROM profiles
        {where_sql}
        ORDER BY {sort_by} {order}
        LIMIT ? OFFSET ?
    """

    return count_q, data_q, params

# Search end points
@app.get("/api/profiles/search")
async def search_profiles(
    q: str = None,
    page: int = 1,
    limit: int = 10
):
    if not q or q.strip() == "":
        return error("Missing query parameter", 400)
    
    # Validate pagination
    if page < 1 or limit < 1 or limit > 50:
        return error("Invalid query parameters", 400)

    filters = parse_natural_language_query(q.strip())

    if not filters:
        return error("Unable to interpret query", 422)

    count_q, data_q, params = build_profile_query(**filters)

    conn = get_db()

    total = conn.execute(count_q, params).fetchone()[0]

    rows = conn.execute(
        data_q,
        params + [limit, (page - 1) * limit]
    ).fetchall()

    conn.close()

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "page": page,
            "limit": limit,
            "total": total,
            "data": [row_to_dict(r) for r in rows]
        }
    )

# Get API profiles
@app.get("/api/profiles")
async def get_profiles(
    gender: str = None,
    age_group: str = None,
    country_id: str = None,
    min_age: int = None,
    max_age: int = None,
    min_gender_probability: float = None,
    min_country_probability: float = None,
    sort_by: str = "created_at",
    order: str = "asc",
    page: int = 1,
    limit: int = 10
):
    # Validate sort_by
    valid_sort = {"age", "created_at", "gender_probability"}
    if sort_by not in valid_sort:
        return error("Invalid query parameters", 400)

    # Validate order
    if order.lower() not in {"asc", "desc"}:
        return error("Invalid query parameters", 400)

    # Validate pagination
    if page < 1:
        return error("Invalid query parameters", 400)

    if limit < 1 or limit > 50:
        return error("Invalid query parameters", 400)
    count_q, data_q, params = build_profile_query(
        gender,
        age_group,
        country_id,
        min_age,
        max_age,
        min_gender_probability,
        min_country_probability,
        sort_by,
        order
    )

    conn = get_db()

    total = conn.execute(count_q, params).fetchone()[0]

    rows = conn.execute(
        data_q,
        params + [limit, (page - 1) * limit]
    ).fetchall()

    conn.close()

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "page": page,
            "limit": limit,
            "total": total,
            "data": [row_to_dict(r) for r in rows]
        }
    )

# Get single profile end point 
@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: str):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM profiles WHERE id = ?",
        (profile_id,)
    ).fetchone()
    conn.close()

    if not row:
        return error("Profile not found", 404)

    return JSONResponse(
        status_code=200,
        content={"status": "success", "data": row_to_dict(row)}
    )

# Delete profile end point
@app.delete("/api/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    conn = get_db()

    result = conn.execute(
        "DELETE FROM profiles WHERE id = ?",
        (profile_id,)
    )

    conn.commit()
    conn.close()

    if result.rowcount == 0:
        return error("Profile not found", 404)

    return Response(status_code=204)

