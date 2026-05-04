from datetime import datetime, timezone, timedelta
import asyncio
from fastapi import FastAPI, Header, HTTPException, Depends, Request, Cookie
from fastapi.responses import JSONResponse, Response, StreamingResponse, RedirectResponse
import csv
import io
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os
import time
import re
import httpx
import secrets
import hashlib
import base64
from jose import jwt, JWTError
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging

# Load environment variables from .env
load_dotenv()

# App Secrets
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

app = FastAPI(title="Insighta Labs API")

# Rate Limiter is initialized
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Structured Logging Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insighta")

# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Stopwatch is started
    start_time = time.time()
    
    # Request is processed by downstream routes
    response = await call_next(request)
    
    # Duration is calculated in milliseconds
    duration = (time.time() - start_time) * 1000
    
    # Audit log entry: [METHOD] [PATH] [STATUS] [DURATION]ms
    logger.info(
        f"{request.method} {request.url.path} | "
        f"Status: {response.status_code} | "
        f"Duration: {duration:.2f}ms"
    )
    
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "insighta.db"

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            github_id TEXT UNIQUE NOT NULL,
            username TEXT,
            email TEXT,
            avatar_url TEXT,
            role TEXT DEFAULT 'analyst',
            is_active BOOLEAN DEFAULT 1,
            last_login_at TEXT,
            created_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            id TEXT PRIMARY KEY,
            token TEXT UNIQUE NOT NULL,
            revoked_at TEXT
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

# API Versioning Dependency
async def require_api_version(x_api_version: str = Header(None)):
    if x_api_version != "1":
        raise HTTPException(
            status_code=400,
            detail="API version header required"
        )

# Pagination Helper
def get_paginated_response(request: Request, data: list, total: int, page: int, limit: int):
    # Ceiling division to find total pages
    total_pages = (total + limit - 1) // limit
    
    # Get the base URL
    base_url = str(request.url).split('?')[0]
    
    # Helper to build the next/prev URLs
    def make_link(p):
        if p < 1 or p > total_pages:
            return None
        return f"{base_url}?page={p}&limit={limit}"

    return {
        "status": "success",
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": total_pages,
        "links": {
            "self": make_link(page),
            "next": make_link(page + 1),
            "prev": make_link(page - 1)
        },
        "data": data
    }

# AUTHENTICATION & SECURITY

# Temporary in-memory store for PKCE verifiers.
pkce_store = {}

def create_access_token(user_id: str, role: str) -> str:
    # Creates a short-lived VIP Pass (3 minutes)
    expire = datetime.now(timezone.utc) + timedelta(minutes=3)
    payload = {"sub": user_id, "role": role, "type": "access", "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    # Creates a longer-lived Renewal Voucher (5 minutes)
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"sub": user_id, "type": "refresh", "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

@app.get("/auth/github")
@limiter.limit("10/minute")
async def github_login(request: Request, state: str = None, code_challenge: str = None):
    if not state or not code_challenge:
        # PKCE keys are generated for web flow
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        
        # 'code_challenge' is created using SHA-256
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

        # Verifier is stored for validation
        pkce_store[state] = code_verifier

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&scope=read:user user:email"
    )
    return RedirectResponse(github_url)

@app.get("/auth/github/callback")
@limiter.limit("10/minute")
async def github_callback(request: Request, code: str = None, state: str = None, code_verifier: str = None, redirect_uri: str = None):
    if not code or not state:
        return error("Missing code or state", 400)

    # CLI Proxy Logic: Handled if this is the initial redirect from GitHub for a CLI login
    if state.startswith("cli_") and not code_verifier:
        parts = state.split("_")
        if len(parts) >= 2:
            cli_port = parts[1]
            # Browser is bounced back to CLI local server
            return RedirectResponse(f"http://localhost:{cli_port}/callback?code={code}&state={state}")

    # PKCE verifier and redirect URI are determined
    if code_verifier:
        # Final exchange request is received from CLI
        final_code_verifier = code_verifier
        final_redirect_uri = redirect_uri or GITHUB_REDIRECT_URI
    else:
        # Standard login is performed by Web App
        final_code_verifier = pkce_store.pop(state, None)
        final_redirect_uri = GITHUB_REDIRECT_URI

    if not final_code_verifier:
        return error("Invalid or expired state", 400)

    # Retry loop is used for network calls to GitHub
    max_retries = 3
    gh_access_token = None
    gh_user = None
    primary_email = None

    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                # Code is exchanged for Access Token
                token_res = await client.post(
                    "https://github.com/login/oauth/access_token",
                    json={
                        "client_id": GITHUB_CLIENT_ID,
                        "client_secret": GITHUB_CLIENT_SECRET,
                        "code": code,
                        "redirect_uri": final_redirect_uri,
                        "code_verifier": final_code_verifier,
                    },
                    headers={"Accept": "application/json"},
                    timeout=10.0
                )
                token_res.raise_for_status()
                gh_access_token = token_res.json().get("access_token")
                
                if not gh_access_token:
                    return error("GitHub did not return an access token", 401)

                # User profile is fetched
                user_res = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {gh_access_token}"},
                    timeout=10.0
                )
                user_res.raise_for_status()
                gh_user = user_res.json()

                # User emails are fetched
                emails_res = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {gh_access_token}"},
                    timeout=10.0
                )
                emails_res.raise_for_status()
                emails = emails_res.json()
                primary_email = next((e["email"] for e in emails if e["primary"]), None)
                
                # Loop is ended if all calls succeeded
                break

            except httpx.HTTPStatusError as e:
                # Request error occurred (e.g. 401 Unauthorized)
                return error(f"GitHub identity verification failed: {str(e)}", 401)
            except (httpx.RequestError, httpx.TimeoutException) as e:
                # Network issues occurred (connection lost, timeout, DNS failure)
                if attempt == max_retries - 1:
                    return error(f"Network error talking to GitHub after {max_retries} attempts: {str(e)}", 503)
                await asyncio.sleep(1) # Wait 1 second before retrying
                continue

    github_id = str(gh_user["id"])
    username = gh_user["login"]
    avatar_url = gh_user.get("avatar_url", "")
    
    # User existence is checked in database
    conn = get_db()
    existing_user = conn.execute("SELECT * FROM users WHERE github_id = ?", (github_id,)).fetchone()
    
    if existing_user:
        user_id = existing_user["id"]
        role = existing_user["role"]
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now(), user_id))
    else:
        user_id = generate_uuid_v7()
        role = "analyst"  # Default role
        conn.execute("""
            INSERT INTO users (id, github_id, username, email, avatar_url, role, is_active, last_login_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (user_id, github_id, username, primary_email, avatar_url, role, utc_now(), utc_now()))
    
    # Internal JWT tokens are generated
    access_token = create_access_token(user_id, role)
    refresh_token = create_refresh_token(user_id)
    
    conn.commit()
    conn.close()

    # Response is prepared with JSON body (for CLI) and HTTP-only cookies (for Web)
    response = JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "username": username,
                "role": role
            }
        }
    )
    
    # Access token is stored in a secure, HTTP-only cookie for the Web Portal
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # Should be True in production (HTTPS)
        samesite="lax",
        max_age=180    # 3 minutes
    )
    
    # Refresh token is stored in a secure, HTTP-only cookie for the Web Portal
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Should be True in production (HTTPS)
        samesite="lax",
        max_age=300    # 5 minutes
    )
    
    return response

# Identity check endpoint
@app.get("/auth/me")
@limiter.limit("60/minute")
async def get_me(request: Request, current_user: dict = Depends(get_current_user)):
    return {"status": "success", "data": current_user}

# Refresh access token endpoint
@app.post("/auth/refresh")
@limiter.limit("10/minute")
async def refresh_access_token(request: Request, body: dict):
    # Refresh token is extracted from request body
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        return error("Missing refresh token", 400)

    conn = get_db()
    
    # Token revocation or prior usage is checked
    revoked = conn.execute("SELECT * FROM revoked_tokens WHERE token = ?", (refresh_token,)).fetchone()
    if revoked:
        conn.close()
        return error("Refresh token has been revoked or already used", 401)

    try:
        # Refresh token is decoded and validated
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        # Token type is verified
        if payload.get("type") != "refresh":
            conn.close()
            return error("Invalid token type", 401)

        user_id = payload.get("sub")
        
        # User is fetched from database to verify status and role
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        
        if not user or not user["is_active"]:
            conn.close()
            return error("User not found or inactive", 401)

        # New tokens are generated
        new_access = create_access_token(user_id, user["role"])
        new_refresh = create_refresh_token(user_id)
        
        # Old refresh token is invalidated immediately
        conn.execute(
            "INSERT INTO revoked_tokens (id, token, revoked_at) VALUES (?, ?, ?)", 
            (generate_uuid_v7(), refresh_token, utc_now())
        )
        conn.commit()
        conn.close()

        # New tokens are returned in JSON and set as secure cookies
        response = JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "access_token": new_access,
                "refresh_token": new_refresh
            }
        )
        
        response.set_cookie(
            key="access_token",
            value=new_access,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=180
        )
        
        response.set_cookie(
            key="refresh_token",
            value=new_refresh,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=300
        )
        
        return response

    except JWTError:
        if 'conn' in locals():
            conn.close()
        return error("Invalid or expired refresh token", 401)

# Logout endpoint
@app.post("/auth/logout")
@limiter.limit("10/minute")
async def logout(request: Request, body: dict):
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        return error("Missing refresh token", 400)

    try:
        # Token is decoded to verify validity before blacklisting
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        
        if payload.get("type") != "refresh":
            return error("Invalid token type", 401)
            
        conn = get_db()
        # Token is added to revoked list
        conn.execute(
            "INSERT OR IGNORE INTO revoked_tokens (id, token, revoked_at) VALUES (?, ?, ?)", 
            (generate_uuid_v7(), refresh_token, utc_now())
        )
        conn.commit()
        conn.close()
        
        # Success response is prepared and cookies are cleared
        response = JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Logged out successfully"}
        )
        
        # Cookies are deleted by setting them to empty with immediate expiry
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        
        return response
    except JWTError:
        return error("Invalid or expired refresh token", 401)

# User is extracted from token (supports Header or Cookie)
async def get_current_user(
    authorization: str = Header(None),
    access_token: str = Cookie(None)
):
    token = None
    
    # Header is checked first (CLI flow)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    # Cookie is checked as fallback (Web flow)
    elif access_token:
        token = access_token
        
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

# User admin status is checked
async def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admins only")
    return current_user

# Global exception handler is used to match required error format
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "message": exc.detail
        }
    )

# Create profile end point
@app.post("/api/profiles", dependencies=[Depends(require_api_version), Depends(require_admin)])
@limiter.limit("60/minute")
async def create_profile(request: Request, body: dict):
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

    # Gender is handled for both cases properly
    male_words = {"male", "males", "man", "men", "boy", "boys"}
    female_words = {"female", "females", "woman", "women", "girl", "girls"}

    has_male = bool(tokens & male_words)
    has_female = bool(tokens & female_words)

    if has_male and not has_female:
        filters["gender"] = "male"
    elif has_female and not has_male:
        filters["gender"] = "female"

    # Age groups are evaluated
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

    # Country is matched
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
@app.get("/api/profiles/search", dependencies=[Depends(require_api_version), Depends(get_current_user)])
@limiter.limit("60/minute")
async def search_profiles(
    request: Request,
    q: str = None,
    page: int = 1,
    limit: int = 10
):
    if not q or q.strip() == "":
        return error("Missing query parameter", 400)
    
    # Pagination is validated
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
        content=get_paginated_response(
            request, 
            [row_to_dict(r) for r in rows], 
            total, 
            page, 
            limit
        )
    )

# CSV Export Endpoint
@app.get("/api/profiles/export", dependencies=[Depends(require_api_version), Depends(get_current_user)])
@limiter.limit("60/minute")
async def export_profiles_csv(
    request: Request,
    format: str = None,
    gender: str = None,
    age_group: str = None,
    country_id: str = None,
    min_age: int = None,
    max_age: int = None,
    min_gender_probability: float = None,
    min_country_probability: float = None,
    sort_by: str = "created_at",
    order: str = "asc"
):
    if format != "csv":
        return error("Invalid format. Only format=csv is supported.", 400)
        
    # Filtered profiles are exported as a CSV file.
    # Same filtering logic as list endpoint is used without pagination.
    count_q, data_q, params = build_profile_query(
        gender, age_group, country_id, min_age, max_age,
        min_gender_probability, min_country_probability, sort_by, order
    )

    # Limits are removed
    data_q = data_q.split("LIMIT")[0]
    
    conn = get_db()
    
    # LIMIT/OFFSET is excluded to fetch all matching rows
    rows = conn.execute(data_q, params).fetchall()
    conn.close()

    if not rows:
        return error("No profiles match the given criteria", 404)

    # StringIO buffer is used to write CSV data in memory
    output = io.StringIO()
    # Columns to export are defined
    fieldnames = [
        "id", "name", "gender", "gender_probability", "age", "age_group",
        "country_id", "country_name", "country_probability", "created_at"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for row in rows:
        writer.writerow(row_to_dict(row))
        
    output.seek(0)
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    headers = {
        "Content-Disposition": f'attachment; filename="profiles_{timestamp}.csv"'
    }

    # Response is streamed with required content type
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)

# Get API profiles
@app.get("/api/profiles", dependencies=[Depends(require_api_version), Depends(get_current_user)])
@limiter.limit("60/minute")
async def get_profiles(
    request: Request,
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
    # Sort parameter is validated
    valid_sort = {"age", "created_at", "gender_probability"}
    if sort_by not in valid_sort:
        return error("Invalid query parameters", 400)

    # Order parameter is validated
    if order.lower() not in {"asc", "desc"}:
        return error("Invalid query parameters", 400)

    # Pagination is validated
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
        content=get_paginated_response(
            request, 
            [row_to_dict(r) for r in rows], 
            total, 
            page, 
            limit
        )
    )

# Get single profile end point 
@app.get("/api/profiles/{profile_id}", dependencies=[Depends(require_api_version), Depends(get_current_user)])
@limiter.limit("60/minute")
async def get_profile(request: Request, profile_id: str):
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
@app.delete("/api/profiles/{profile_id}", dependencies=[Depends(require_api_version), Depends(require_admin)])
@limiter.limit("60/minute")
async def delete_profile(request: Request, profile_id: str):
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

