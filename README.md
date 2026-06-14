# 🎰 VaultBet — Virtual Casino Platform

> A locally-hosted virtual casino with **no real money**, **no real payments**, and **no external APIs**.  
> Built with **FastAPI** · **SQLite** · **Jinja2** · **Vanilla CSS/JS** — runs entirely on `localhost:8000`.

---

## ⚠️ Disclaimer

**VaultBet is a toy project for entertainment and learning purposes only.**

- No real money is involved at any point.
- No payment gateways, no Stripe, no crypto.
- Passwords are stored as **Base64 encoding** (not encryption) — this is intentional and clearly noted in the source code. Do **not** use real passwords.
- Do **not** deploy this to a public server.

---

## 🚀 Quick Start (How to Run)

### 1. Clone the repo
```bash
git clone https://github.com/your-username/vaultbet.git
cd vaultbet
```

### 2. Create a virtual environment (recommended)
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. INSTALL REQUIREMENTS FIRST (Crucial Step!)
```bash
pip install -r requirements.txt
```

### 4. Run the server
```bash
python main.py
```

### 5. Open in your browser
```
http://localhost:8000
```

Register a new account → receive 500 starting credits → start playing!

---

## ✨ Features

### 🔐 Auth System
- Username + password registration and login
- Passwords stored as Base64-encoded strings (local toy project only — explicitly noted in comments)
- Signed session cookies via Starlette `SessionMiddleware`
- Banned users see a dedicated suspension screen and cannot log in

### 💰 Virtual Credit System
- Every new user starts with **500 credits**
- Balances can go **negative** (debt state) — shown clearly in the UI with a red ⚠️ banner
- **Instant ban** if balance reaches **−500 credits** (debt floor)

### 🏦 Loan System
| Feature | Detail |
|---|---|
| Loan amounts | 100, 250, or 500 credits |
| Interest | Flat 20% added at creation |
| Grace period | 30 minutes |
| Default penalty | **Permanent account ban** |
| Repayment | One click — deducts full repay amount from balance |
| Live countdown | JS timer on the sidebar loan widget |

### 🎮 12 RNG-Based Games

> **All outcomes are pure RNG** — `random` or `secrets` called fresh per play. No house edge manipulation based on player state.

| # | Game | Min Bet | Mechanic |
|---|---|---|---|
| 1 | Coin Flip | 10 | 50/50 · 2× |
| 2 | Dice Roll | 15 | Roll > 3 wins · 1.8× |
| 3 | Slot Machine | 20 | 3 symbols · Match 3 = 10× · Match 2 = 1.5× |
| 4 | Roulette | 25 | Red/Black/Green · Green = 14× · Others = 2× |
| 5 | Hi-Lo Card | 15 | Higher or lower card (1–13) · 1.9× |
| 6 | Lucky Number | 20 | Pick 1–10 · Exact match = 8× |
| 7 | Crash Multiplier | 30 | Cash out before it crashes (1×–10×) |
| 8 | Scratch Card | 10 | Reveal 3 of 9 · Match 2 = 2× · Match 3 = 15× |
| 9 | Plinko Drop | 25 | 5-peg board · 6 buckets (0×–3×) |
| 10 | War (Card Battle) | 20 | Higher card wins · 1.9× · Ties push |
| 11 | Number Roulette | 20 | Pick exact 0–36 · 30× |
| 12 | Wheel of Fortune | 15 | 8-segment wheel · Up to 5× |

Each game features:
- **"How to Play" tutorial modal** — shown automatically on first visit (stored in `localStorage`)
- **ⓘ Info button** to re-open the guide at any time
- **Animated visuals** — spinning coins, rolling dice, slot reels, Plinko ball physics, wheel spin, crash graph

### 🏆 Leaderboard
- Top 10 players ranked by **all-time total credits won**
- Current user's row is always highlighted (shown below the table if outside top 10)
- Updates after every game result

---

## 🗂️ Project Structure

```
vaultbet/
├── main.py           # FastAPI app: routes, game logic, auth, loan scheduler
├── database.py       # SQLite setup and table initialization
├── models.py         # CRUD helpers for users, loans, game history, leaderboard
├── requirements.txt  # Python dependencies
├── .gitignore
├── LICENSE
├── README.md
├── templates/
│   ├── base.html         # Global layout: nav, balance badge, loan widget, debt banner
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html    # 12-game card grid + recent history
│   ├── game.html         # Universal game view with per-game JS/CSS
│   ├── leaderboard.html
│   └── banned.html
└── static/
    └── style.css         # Dark casino theme: glassmorphism, gold/neon palette, animations
```

---

## ⚙️ Configuration

Open `main.py` and edit these constants near the top:

```python
# Loan grace period before default (minutes)
LOAN_DURATION_MINUTES = 30
```

The debt floor ban threshold (−500 credits) is enforced in `models.py` inside `add_game_record`.

---

## 🛡️ Security Notes

This project is **intentionally insecure** in several ways because it is a local toy:

| Area | Implementation | Why |
|---|---|---|
| Passwords | Base64 encoding | Clearly noted in source comments — local use only |
| Session key | Random on startup | New key each server restart |
| Database | SQLite flat file | Sufficient for local single-user use |
| Auth | No rate limiting | Not needed for localhost |

**Never use real credentials. Never deploy publicly.**

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend | [FastAPI](https://fastapi.tiangolo.com/) |
| Server | [Uvicorn](https://www.uvicorn.org/) |
| Templating | [Jinja2](https://jinja.palletsprojects.com/) |
| Database | SQLite (Python `sqlite3` stdlib) |
| Frontend | Vanilla HTML, CSS, JavaScript |
| Sessions | Starlette `SessionMiddleware` |
| RNG | Python `random` + `secrets` |

---

## 📸 Screenshots

> Register → Dashboard → Pick a game → Place a bet → See live results

The UI features:
- Deep navy/charcoal dark theme
- Gold accents and buttons
- Neon green wins · Neon red losses
- Glassmorphism game cards
- Animated slot reels, coin flips, dice rolls, Plinko ball, crash graph, spinning wheel

---

## 🤝 Contributing

Pull requests are welcome for:
- New game mechanics
- UI improvements
- Bug fixes

Please open an issue first to discuss major changes.

---

## 📄 License

[Custom Open License](LICENSE) — open source, free to use and modify, just drop a small credit line if you use it. No warranty. No liability. Made by a teenager as a first project.
