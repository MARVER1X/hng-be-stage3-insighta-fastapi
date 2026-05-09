# Insighta Labs+: Core Intelligence Engine

The central high-performance REST API powering the Insighta ecosystem. Built with FastAPI, it manages demographic intelligence, secure OAuth sequences, and role-based access control for multiple interfaces.

---

## 🔗 Live Demo

[View API on Railway](https://web-production-1d564.up.railway.app/)

---

## 📸 Preview

> A production-grade backend infrastructure providing a single source of truth for the Insighta CLI and Web Portal. It features a robust multi-layered security stack including PKCE-validated GitHub OAuth, HttpOnly cookie session management, and granular Role-Based Access Control (RBAC).

---

## ✅ Core Features

- **GitHub OAuth with PKCE** — Secure multi-interface authentication flow supporting both Browser and CLI environments.
- **Role-Based Access Control (RBAC)** — Granular permission enforcement distinguishing between `Admin` (Full CRUD) and `Analyst` (Read-Only) roles.
- **Intelligence Query Engine** — Advanced filtering, sorting, and pagination across thousands of demographic profiles.
- **Natural Language Parsing** — Interprets human-readable queries (e.g., "Men in Nigeria above 25") into structured SQL operations.
- **Security First** — Enforced API versioning, Rate Limiting, and XSS/CSRF mitigation via secure HttpOnly cookies.

---

## 🚧 Development Status & Upcoming Features

*Note: This project is currently in active production-ready state for HNG Stage 3.*

- [ ] **Real-time WebSockets** — Stream new intelligence detections directly to connected clients.
- [ ] **Advanced NLP with LLM** — Transition from rule-based parsing to vector-based semantic search.
- [ ] **Audit Logging UI** — A dashboard for admins to track system-wide role elevations and deletions.

---

## 🛡️ Authentication & Security Architecture

### **Authentication Flow (PKCE)**

Insighta Labs+ utilizes the **Authorization Code Flow with Proof Key for Code Exchange (PKCE)** to secure multi-interface access.

1. **Initiation**: The client (Web or CLI) generates a cryptographically random `code_verifier` and its SHA-256 hash `code_challenge`.
2. **Handshake**: The client redirects the user to `/auth/github` with the challenge.
3. **Callback**: After GitHub approval, the backend receives the code and verifier, exchanges them for a GitHub token, and issues internal Insighta tokens.

### **Token Handling Approach**

- **Web Portal**: Implements **Stateless HttpOnly Cookies**. JavaScript cannot access the JWT, neutralizing XSS risks.
- **CLI**: Stores tokens in `~/.insighta/credentials.json`. It features an auto-refresh middleware that intercepts 401 errors, attempts a refresh, and retries the original request seamlessly.

### **Natural Language Parsing (NLP)**

The query engine uses a **rule-based extraction approach**:

1. **Tokenization**: Input is normalized and split into keywords.
2. **Entity Mapping**: Keywords are matched against predefined maps (e.g., "young" -> 16-24, "nigeria" -> NG).
3. **Conflict Resolution**: Contradictory filters are ignored to maintain query stability.

### **Role Enforcement Logic**

Roles are embedded within the JWT (`sub` and `role`). The backend uses a structured dependency-injection pattern:

- `get_current_user`: Validates token and checks `is_active` status in the DB.
- `require_admin`: A sub-dependency that enforces `role == "admin"`.

---

## ♿ Accessibility Expectations Met

- **Predictable JSON Schema** — All error and success responses follow a strict, documented structure for easy parsing by screen-reading dev tools.
- **Semantic Error Codes** — Uses standard HTTP status codes (401, 403, 429) to ensure programmatic accessibility for all client types.
- **Rate Limit Transparency** — Provides clear `X-RateLimit` headers so clients can intelligently throttle themselves.

---

## 🗂️ Architecture & Project Structure

```text
├── main.py              # Central FastAPI application, routes, and middleware
├── insighta.db          # SQLite persistent storage (Production-ready)
├── requirements.txt     # Python dependency manifest
├── .github/workflows    # CI/CD Automated build and lint checks
└── seeds.py             # Database initialization and profile enrichment logic
```

---

## 🛠️ Built With

- **Framework** — FastAPI (Python 3.13)
- **State Management / DB** — SQLite with UUID v7 primary keys
- **Authentication** — GitHub OAuth 2.0 with PKCE implementation
- **Security** — SlowAPI (Rate Limiting), Jose (JWT), and HttpOnly Cookies

---

## 👤 Author

**Marvellous**  
GitHub: [@MARVER1X](https://github.com/MARVER1X)
