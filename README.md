# HNG Stage 2 Backend — Intelligence Query Engine API

A high-performance REST API built with FastAPI that stores demographic profiles and enables advanced filtering, sorting, pagination, and natural language search.

The system allows clients to query structured demographic data using both traditional query parameters and natural language queries.

🔗 **Live API**: [Demo app](https://your-live-api-url.up.railway.app)

---

## 📌 Features

- Create demographic profiles using external APIs
- Advanced filtering (gender, age, country, probabilities)
- Sorting (age, created_at, gender_probability)
- Pagination (page & limit)
- Natural language search (rule-based parsing)
- Full CRUD support (GET, POST, DELETE)
- SQLite persistent storage

---

## 📌 Endpoints

### 1. Create Profile
**`POST /api/profiles`**

**Request Body:**
```json
{ 
  "name": "emeka" 
}
```

**Success — 201 Created:**
```json
{
  "status": "success",
  "data": {
    "id": "uuid-v7",
    "name": "emeka",
    "gender": "male",
    "gender_probability": 0.99,
    "age": 34,
    "age_group": "adult",
    "country_id": "NG",
    "country_name": "Nigeria",
    "country_probability": 0.85,
    "created_at": "2026-04-23T12:00:00Z"
  }
}
```

**Already Exists — 200 OK:**
```json
{
  "status": "success",
  "message": "Profile already exists",
  "data": { "...existing profile..." }
}
```

---

### 2. Get All Profiles (Filtering + Sorting + Pagination)
**`GET /api/profiles`**

**Query Parameters:**

| Parameter                 | Description                             |
| ------------------------- | --------------------------------------- |
| `gender`                  | male / female                           |
| `age_group`               | child / teenager / adult / senior       |
| `country_id`              | ISO country code                        |
| `min_age`                 | minimum age filter                      |
| `max_age`                 | maximum age filter                      |
| `min_gender_probability`  | confidence filter                       |
| `min_country_probability` | confidence filter                       |
| `sort_by`                 | age / created\_at / gender\_probability |
| `order`                   | asc / desc                              |
| `page`                    | default 1                               |
| `limit`                   | default 10 (max 50)                     |

**Example:**
```
GET /api/profiles?gender=male&country_id=NG&min_age=25&sort_by=age&order=desc&page=1&limit=10
```

**Success — 200 OK:**
```json
{
  "status": "success",
  "page": 1,
  "limit": 10,
  "total": 2026,
  "data": [
    {
      "id": "...",
      "name": "emeka",
      "gender": "male",
      "age": 34,
      "age_group": "adult",
      "country_id": "NG"
    }
  ]
}
```

---

### 3. Natural Language Search (Core Feature)
**`GET /api/profiles/search?q=...`**

**Example:**
```
GET /api/profiles/search?q=young males from nigeria
```

#### 🧠 Natural Language Parsing Logic

The query engine uses rule-based keyword extraction (no AI/LLMs).

**Gender**

| Keyword                        | Output          |
| ------------------------------ | --------------- |
| male, man, men, boys           | gender = male   |
| female, woman, women, girls    | gender = female |

**Age Groups**

| Keyword             | Output               |
| ------------------- | -------------------- |
| child, kids         | age_group = child    |
| teen, teenagers     | age_group = teenager |
| adult, adults       | age_group = adult    |
| senior, elderly     | age_group = senior   |

**Special Age Rules**

| Phrase             | Output                    |
| ------------------ | ------------------------- |
| young              | min_age = 16, max_age = 24 |
| above X / over X   | min_age = X               |
| below X / under X  | max_age = X               |

**Country Matching**

Country names are mapped to ISO codes:
- `"nigeria"` → `NG`
- `"kenya"` → `KE`
- `"ghana"` → `GH`
- `"usa"` → `US`

Adjectives are also supported:
- `"nigerians"` → `NG`
- `"americans"` → `US`

**Example Conversions**

| Query               | Parsed Filters                      |
| ------------------- | ----------------------------------- |
| young males         | gender=male + age 16–24             |
| females above 30    | gender=female + min_age=30          |
| adults from kenya   | age_group=adult + country_id=KE     |
| seniors             | age_group=senior                    |
| elderly women       | gender=female + age_group=senior    |

#### ⚠️ Parsing Limitations

This system is rule-based and does **NOT** use AI.

It cannot handle:
- Complex sentence understanding
- Ambiguous phrases (e.g. `"people like emeka in africa"`)
- Mixed contradictory queries (e.g. `"young seniors"`)
- Multi-country combined filters (`"nigeria and ghana together"`)
- Soft semantic intent beyond defined keywords

**Edge Cases:**
- `"male and female teenagers"` → gender filter is ignored (conflict resolution)
- `"above"` without number → ignored safely
- Unknown words → ignored unless other filters match

If a query cannot be interpreted:
```json
{
  "status": "error",
  "message": "Unable to interpret query"
}
```

---

### 4. Get Single Profile
**`GET /api/profiles/{id}`**

Returns full profile or:
```json
{ 
  "status": "error", 
  "message": "Profile not found" 
}
```

---

### 5. Delete Profile
**`DELETE /api/profiles/{id}`**

- **Success:** 204 No Content
- **Not found:** 404

---

## ❌ Error Responses

```json
{ 
  "status": "error", 
  "message": "<error message>" 
}
```

| Code  | Meaning                       |
| ----- | ----------------------------- |
| `400` | Invalid or missing parameters |
| `422` | Unprocessable input           |
| `404` | Not found                     |
| `502` | External API failure          |

---

## 🗂️ Database Schema

Exact required schema:

| Field                | Type    |
| -------------------- | ------- |
| `id`                 | UUID v7 |
| `name`               | unique  |
| `gender`             | string  |
| `gender_probability` | float   |
| `age`                | integer |
| `age_group`          | string  |
| `country_id`         | string  |
| `country_name`       | string  |
| `country_probability`| float   |
| `created_at`         | datetime|

---

## 🚀 Running Locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## 🧪 Testing

Use Thunder Client or Postman to test the following endpoints:

```
GET  /api/profiles
GET  /api/profiles/search?q=young males
POST /api/profiles
DELETE /api/profiles/{id}
```

---

## 🛠️ Tech Stack

- FastAPI
- SQLite
- httpx
- Python 3.13
- Uvicorn

---

## 👤 Author

**Marvellous**  
GitHub: [@MARVER1X](https://github.com/MARVER1X)

---

## 🏁 Submission Notes

- Database seeded with 2026 profiles
- All filters are combinable
- Natural language parsing is rule-based (no AI)
- Pagination enforced (max 50 limit)
- Fully idempotent seeding supported