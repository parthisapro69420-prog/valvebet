import asyncio
import base64
import os
import random
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from database import init_db, get_db_connection
import models

# Loan configuration
LOAN_DURATION_MINUTES = 30

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database tables
    init_db()
    # Start the background loan checker task
    task = asyncio.create_task(loan_checker_loop())
    yield
    # Shutdown: Clean up background task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

# Session middleware configuration (generates a fresh key on startup)
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja2 Templates configuration
templates = Jinja2Templates(directory="templates")


# --- Game Metadata ---

GAMES_INFO = {
    "coin_flip": {
        "name": "Coin Flip",
        "min_bet": 10,
        "instructions": "Place a bet and predict Heads or Tails. If the coin lands on your choice, you win 2x your bet. Otherwise, you lose."
    },
    "dice_roll": {
        "name": "Dice Roll",
        "min_bet": 15,
        "instructions": "Place a bet. A single six-sided die is rolled. If the outcome is greater than 3 (4, 5, or 6), you win 1.8x your bet. Otherwise, you lose."
    },
    "slots": {
        "name": "Slot Machine",
        "min_bet": 20,
        "instructions": "Spin the slots with 6 symbols (🍒, 🍋, 🍊, 🍇, 🔔, 💎). Get 3 matching symbols to win a massive 10x payout. Get 2 matching symbols to win a 1.5x payout. Otherwise, you lose."
    },
    "roulette": {
        "name": "Roulette",
        "min_bet": 25,
        "instructions": "Select Red, Black, or Green and place your bet. The wheel rolls a number 0 to 36. Red and Black numbers pay 2x. Green (0) pays 14x. Otherwise, you lose."
    },
    "hilo": {
        "name": "Hi-Lo Card",
        "min_bet": 15,
        "instructions": "Guess if the next card drawn (1-13) will be Higher or Lower than the current card. Correct guess pays 1.9x. Equal card ranks result in a Push (refund)."
    },
    "lucky_number": {
        "name": "Lucky Number",
        "min_bet": 20,
        "instructions": "Choose a number between 1 and 10. If the host draws your exact chosen number, you win 8x your bet. Otherwise, you lose."
    },
    "crash": {
        "name": "Crash Multiplier",
        "min_bet": 30,
        "instructions": "Watch the multiplier grow from 1.0x to 10.0x. You must click 'Cash Out' before the rocket crashes. If you cash out successfully, you win your bet multiplied by the cash out multiplier. If it crashes, you lose your bet."
    },
    "scratch": {
        "name": "Scratch Card",
        "min_bet": 10,
        "instructions": "Buy a scratch card and reveal exactly 3 cells from the 9 hidden cells. Match 2 cells to win 2x your bet. Match 3 cells to win 15x your bet. Otherwise, you lose."
    },
    "plinko": {
        "name": "Plinko Drop",
        "min_bet": 25,
        "instructions": "Drop the ball through the pegboard. It lands in one of 6 buckets at the bottom. Landing multipliers are: 3x, 1.5x, 1x, 1x, 0.5x, and 0x."
    },
    "war": {
        "name": "War (Card Battle)",
        "min_bet": 20,
        "instructions": "Draw a card (1-13) against the dealer. Higher card wins 1.9x. Equal cards result in a Push (refund). Lower card loses."
    },
    "number_roulette": {
        "name": "Number Roulette",
        "min_bet": 20,
        "instructions": "Pick an exact number between 0 and 36. An exact match pays a whopping 30x. Otherwise, you lose."
    },
    "wheel": {
        "name": "Wheel of Fortune",
        "min_bet": 15,
        "instructions": "Spin the 8-segment wheel. Win up to 5x your bet, or dodge the 0x crash spaces."
    }
}


# --- Helpers & Background Task ---

def encode_password(password: str) -> str:
    """Base64 encoding helper.
    Explicit note: Base64 is encoding, NOT encryption.
    This is a local toy project only.
    """
    return base64.b64encode(password.encode('utf-8')).decode('utf-8')

def verify_password(plain_password: str, encoded_password: str) -> bool:
    """Checks if plain password encodes to the stored value."""
    return encode_password(plain_password) == encoded_password

async def loan_checker_loop():
    """Background loop that checks for expired active loans every 5 seconds and bans users."""
    while True:
        try:
            current_time = datetime.now().isoformat()
            expired_loans = models.get_expired_active_loans(current_time)
            for loan in expired_loans:
                # Ban the user associated with the defaulted loan
                models.ban_user(loan["user_id"])
                # Mark the loan as inactive (defaulted)
                conn = get_db_connection()
                conn.execute("UPDATE loans SET active = 0 WHERE id = ?", (loan["id"],))
                conn.commit()
                conn.close()
                print(f"[BACKGROUND] Banned User ID {loan['user_id']} due to defaulting on loan ID {loan['id']}")
        except Exception as e:
            print(f"[BACKGROUND ERROR] Loan checker failed: {e}")
        await asyncio.sleep(5)

def check_and_resolve_pending_games(request: Request, user_id: int):
    """Checks for pending Crash or Scratch card sessions and logs them as losses if abandoned."""
    # Crash cleanup
    crash_bet = request.session.pop("crash_bet", None)
    crash_point = request.session.pop("crash_point", None)
    if crash_bet is not None and crash_point is not None:
        models.add_game_record(
            user_id=user_id,
            game_name="Crash",
            bet=crash_bet,
            payout=0,
            result_details=f"Crashed at {crash_point}x (Abandoned/Disconnected).",
            timestamp=datetime.now().isoformat()
        )
    
    # Scratch cleanup
    scratch_bet = request.session.pop("scratch_bet", None)
    scratch_symbols = request.session.pop("scratch_symbols", None)
    if scratch_bet is not None and scratch_symbols is not None:
        models.add_game_record(
            user_id=user_id,
            game_name="Scratch Card",
            bet=scratch_bet,
            payout=0,
            result_details=f"Abandoned Scratch Card (Card: {', '.join(scratch_symbols)}).",
            timestamp=datetime.now().isoformat()
        )


# --- Global Request Dependency ---

class RedirectException(Exception):
    def __init__(self, url: str):
        self.url = url

@app.exception_handler(RedirectException)
async def redirect_exception_handler(request: Request, exc: RedirectException):
    return RedirectResponse(exc.url, status_code=status.HTTP_303_SEE_OTHER)

async def check_ban_and_loans_dependency(request: Request):
    """Dependency checking user status, enforcing loan limits, and performing instant loan bans."""
    path = request.url.path
    
    # Exclude static assets, ban screen, and auth routes to prevent redirection loops
    if path.startswith("/static") or path in ["/banned", "/auth/logout", "/auth/login", "/auth/register"]:
        return
        
    username = request.session.get("username")
    if username:
        user = models.get_user_by_username(username)
        if user:
            # INSTANT LOAN EXPIRATION CHECK: Check active loan before proceeding
            active_loan = models.get_active_loan(user["id"])
            if active_loan:
                current_time = datetime.now().isoformat()
                if current_time > active_loan["deadline"]:
                    # Loan defaulted! Ban the user instantly
                    models.ban_user(user["id"])
                    # Mark loan inactive
                    conn = get_db_connection()
                    conn.execute("UPDATE loans SET active = 0 WHERE id = ?", (active_loan["id"],))
                    conn.commit()
                    conn.close()
                    # Log user out and redirect
                    request.session.clear()
                    raise RedirectException("/banned")
            
            # If user is marked banned, clear session and redirect to /banned
            if user["banned"] == 1:
                request.session.clear()
                raise RedirectException("/banned")
                
            # If username is valid, check and resolve any abandoned games
            check_and_resolve_pending_games(request, user["id"])
        else:
            # Session exists but user is deleted or invalid
            request.session.clear()
            raise RedirectException("/auth/login")
    else:
        # Not logged in
        raise RedirectException("/auth/login")

app.router.dependencies.append(Depends(check_ban_and_loans_dependency))


# --- Auth Routes ---

@app.get("/auth/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if request.session.get("username"):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="login.html", context={})

@app.post("/auth/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = models.get_user_by_username(username)
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password."})
        
    # Check ban status
    if user["banned"] == 1:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "Your account has been suspended due to loan default."})
        
    if verify_password(password, user["password_hash"]):
        request.session["username"] = user["username"]
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
        
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Invalid username or password."})

@app.get("/auth/register", response_class=HTMLResponse)
async def register_get(request: Request):
    if request.session.get("username"):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="register.html", context={})

@app.post("/auth/register", response_class=HTMLResponse)
async def register_post(request: Request, username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Username and password are required."})
        
    existing_user = models.get_user_by_username(username)
    if existing_user:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Username is already taken."})
        
    try:
        pw_hash = encode_password(password)
        user_id = models.create_user(username, pw_hash)
        request.session["username"] = username
        request.session["user_id"] = user_id
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return templates.TemplateResponse(request=request, name="register.html", context={"error": f"Registration failed: {str(e)}"})

@app.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)


# --- Core Pages ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    username = request.session.get("username")
    user = models.get_user_by_username(username)
    active_loan = models.get_active_loan(user["id"])
    history = models.get_user_history(user["id"], limit=10)
    
    return templates.TemplateResponse(
        request=request, 
        name="dashboard.html", 
        context={
            "user": user, 
            "active_loan": active_loan, 
            "history": history,
            "active_page": "dashboard"
        }
    )

@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard(request: Request):
    username = request.session.get("username")
    user = models.get_user_by_username(username)
    active_loan = models.get_active_loan(user["id"])
    
    top_users = models.get_top_users(10)
    user_rank_info = models.get_user_rank_info(user["id"])
    
    return templates.TemplateResponse(
        request=request,
        name="leaderboard.html",
        context={
            "user": user,
            "active_loan": active_loan,
            "top_users": top_users,
            "user_rank_info": user_rank_info,
            "active_page": "leaderboard"
        }
    )

@app.get("/banned", response_class=HTMLResponse)
async def banned_screen(request: Request):
    return templates.TemplateResponse(request=request, name="banned.html", context={})


# --- Loan Endpoints ---

@app.post("/loan/take")
async def take_loan(request: Request, amount: int = Form(...)):
    username = request.session.get("username")
    user = models.get_user_by_username(username)
    
    if amount not in [100, 250, 500]:
        return HTMLResponse("Invalid loan amount requested.", status_code=status.HTTP_400_BAD_REQUEST)
        
    active_loan = models.get_active_loan(user["id"])
    if active_loan:
        # User already has an active loan - block it
        return HTMLResponse("You already have an active loan. Please repay it first.", status_code=status.HTTP_400_BAD_REQUEST)
        
    created_at = datetime.now()
    deadline = created_at + timedelta(minutes=LOAN_DURATION_MINUTES)
    repay_amount = int(amount * 1.20)  # Flat 20% interest added on top
    
    try:
        models.create_loan(
            user_id=user["id"],
            amount=amount,
            repay_amount=repay_amount,
            created_at=created_at.isoformat(),
            deadline=deadline.isoformat()
        )
    except Exception as e:
        return HTMLResponse(f"Loan processing error: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/loan/repay")
async def repay_loan(request: Request):
    username = request.session.get("username")
    user = models.get_user_by_username(username)
    
    active_loan = models.get_active_loan(user["id"])
    if not active_loan:
        return HTMLResponse("No active loan to repay.", status_code=status.HTTP_400_BAD_REQUEST)
        
    try:
        # Repay loan (deducts from balance, marks active=0)
        models.repay_loan(
            loan_id=active_loan["id"],
            user_id=user["id"],
            repay_amount=active_loan["repay_amount"]
        )
    except Exception as e:
        return HTMLResponse(f"Repay processing error: {e}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


# --- Game Integration & Routing ---

@app.get("/game/{game_id}", response_class=HTMLResponse)
async def game_page(request: Request, game_id: str):
    if game_id not in GAMES_INFO:
        raise HTTPException(status_code=404, detail="Game not found")
        
    username = request.session.get("username")
    user = models.get_user_by_username(username)
    active_loan = models.get_active_loan(user["id"])
    
    return templates.TemplateResponse(
        request=request,
        name="game.html",
        context={
            "user": user,
            "active_loan": active_loan,
            "game_id": game_id,
            "game_info": GAMES_INFO[game_id]
        }
    )

# Models for game bodies
class GamePlayRequest(BaseModel):
    bet: int
    choice: Optional[str] = None

class LuckyPlayRequest(BaseModel):
    bet: int
    choice: int

class CrashStartRequest(BaseModel):
    bet: int

class CrashCashoutRequest(BaseModel):
    multiplier: float

class ScratchClaimRequest(BaseModel):
    indices: List[int]


# Game 1: Coin Flip
@app.post("/game/coin_flip/play")
async def play_coin_flip(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    user = models.get_user_by_id(user_id)
    
    if body.bet < 10:
        return JSONResponse({"error": "Minimum bet is 10 credits."}, status_code=400)
        
    if body.choice not in ["heads", "tails"]:
        return JSONResponse({"error": "Invalid choice selected."}, status_code=400)
        
    # Pure RNG — no manipulation
    roll = random.choice(["heads", "tails"])
    win = (body.choice == roll)
    payout = body.bet * 2 if win else 0
    
    details = f"You bet on {body.choice.upper()}. Coin landed on {roll.upper()}."
    models.add_game_record(user_id, "Coin Flip", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 2: Dice Roll
@app.post("/game/dice_roll/play")
async def play_dice_roll(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 15:
        return JSONResponse({"error": "Minimum bet is 15 credits."}, status_code=400)
        
    # Pure RNG — no manipulation
    roll = random.randint(1, 6)
    win = (roll > 3)
    payout = int(body.bet * 1.8) if win else 0
    
    details = f"You rolled a {roll} (Win condition: > 3)."
    models.add_game_record(user_id, "Dice Roll", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 3: Slots
@app.post("/game/slots/play")
async def play_slots(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 20:
        return JSONResponse({"error": "Minimum bet is 20 credits."}, status_code=400)
        
    pool = ['🍒', '🍋', '🍊', '🍇', '🔔', '💎']
    
    # Pure RNG — no manipulation
    roll = [random.choice(pool) for _ in range(3)]
    unique_count = len(set(roll))
    
    if unique_count == 1:
        payout = body.bet * 10
        details = f"JACKPOT! Three {roll[0]} match (10x payout)."
    elif unique_count == 2:
        payout = int(body.bet * 1.5)
        # Find which symbol is doubled
        doubled = max(set(roll), key=roll.count)
        details = f"Double! Match 2x {doubled} (1.5x payout)."
    else:
        payout = 0
        details = "No match. Better luck next time!"
        
    models.add_game_record(user_id, "Slot Machine", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 4: Roulette
@app.post("/game/roulette/play")
async def play_roulette(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 25:
        return JSONResponse({"error": "Minimum bet is 25 credits."}, status_code=400)
        
    if body.choice not in ["red", "black", "green"]:
        return JSONResponse({"error": "Invalid color choice."}, status_code=400)
        
    red_numbers = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
    
    # Pure RNG — no manipulation
    roll = random.randint(0, 36)
    
    if roll == 0:
        roll_color = "green"
    elif roll in red_numbers:
        roll_color = "red"
    else:
        roll_color = "black"
        
    win = (body.choice == roll_color)
    if win:
        payout = body.bet * 14 if roll_color == "green" else body.bet * 2
        details = f"Roulette spun {roll} ({roll_color.upper()}). Correct choice! Won {payout} credits."
    else:
        payout = 0
        details = f"Roulette spun {roll} ({roll_color.upper()}). You lost."
        
    models.add_game_record(user_id, "Roulette", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "roll_color": roll_color,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 5: Hi-Lo Deal Initial Card
@app.get("/game/hilo/deal")
async def deal_hilo(request: Request):
    # Pure RNG — no manipulation
    card = random.randint(1, 13)
    suit = random.choice(['S', 'H', 'D', 'C'])
    request.session["hilo_card"] = card
    request.session["hilo_suit"] = suit
    return {"card": card, "suit": suit}

# Game 5: Hi-Lo Card Play
@app.post("/game/hilo/play")
async def play_hilo(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 15:
        return JSONResponse({"error": "Minimum bet is 15 credits."}, status_code=400)
        
    if body.choice not in ["hi", "lo"]:
        return JSONResponse({"error": "Invalid choice."}, status_code=400)
        
    start_card = request.session.get("hilo_card")
    if not start_card:
        # Fallback if session is cleared
        start_card = random.randint(1, 13)
        
    # Pure RNG — no manipulation
    next_card = random.randint(1, 13)
    next_suit = random.choice(['S', 'H', 'D', 'C'])
    
    status_str = "loss"
    payout = 0
    
    if next_card == start_card:
        status_str = "push"
        payout = body.bet  # refund
        details = f"Tie card! Both cards are rank {start_card}. Bet refunded."
    elif (next_card > start_card and body.choice == "hi") or (next_card < start_card and body.choice == "lo"):
        status_str = "win"
        payout = int(body.bet * 1.9)
        details = f"Card rank was {next_card} (Previous: {start_card}). Correct guess!"
    else:
        details = f"Card rank was {next_card} (Previous: {start_card}). Wrong guess!"
        
    # Save the new card as the reference for the next play
    request.session["hilo_card"] = next_card
    request.session["hilo_suit"] = next_suit
    
    models.add_game_record(user_id, "Hi-Lo Card", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "status": status_str,
        "next_card": next_card,
        "next_suit": next_suit,
        "payout": payout,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 6: Lucky Number
@app.post("/game/lucky_number/play")
async def play_lucky_number(request: Request, body: LuckyPlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 20:
        return JSONResponse({"error": "Minimum bet is 20 credits."}, status_code=400)
        
    if not (1 <= body.choice <= 10):
        return JSONResponse({"error": "Pick a number between 1 and 10."}, status_code=400)
        
    # Pure RNG — no manipulation
    roll = random.randint(1, 10)
    win = (body.choice == roll)
    payout = body.bet * 8 if win else 0
    
    if win:
        details = f"Choice: {body.choice}, Host drew: {roll}. Match! Won 8x payout."
    else:
        details = f"Choice: {body.choice}, Host drew: {roll}. No match."
        
    models.add_game_record(user_id, "Lucky Number", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 7: Crash Start Flight
@app.post("/game/crash/start")
async def start_crash(request: Request, body: CrashStartRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 30:
        return JSONResponse({"error": "Minimum bet is 30 credits."}, status_code=400)
        
    # Deduct bet immediately from user's balance
    models.update_user_balance(user_id, -body.bet)
    
    # Pure RNG — no manipulation
    crash_point = round(random.uniform(1.01, 10.0), 2)
    
    # Save flight variables in user session
    request.session["crash_bet"] = body.bet
    request.session["crash_point"] = crash_point
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "status": "started",
        "new_balance": updated_user["balance"],
        "crash_point": crash_point
    }

# Game 7: Crash Cashout Click
@app.post("/game/crash/cashout")
async def cashout_crash(request: Request, body: CrashCashoutRequest):
    user_id = request.session.get("user_id")
    
    crash_bet = request.session.pop("crash_bet", None)
    crash_point = request.session.pop("crash_point", None)
    
    if crash_bet is None or crash_point is None:
        return JSONResponse({"error": "No active flight found."}, status_code=400)
        
    # Check if they cashed out before the crash point
    # We round to prevent precision floating issues
    if round(body.multiplier, 2) <= round(crash_point, 2):
        # Successful Cashout
        payout = int(crash_bet * body.multiplier)
        details = f"Cashed out at {body.multiplier:.2f}x. (Crash point was {crash_point:.2f}x)."
        
        # Credit payout back to balance
        models.update_user_balance(user_id, payout)
        # Accumulate total won
        models.add_user_winnings(user_id, payout)
        
        models.add_game_record(user_id, "Crash Multiplier", crash_bet, payout, details, datetime.now().isoformat())
        
        updated_user = models.get_user_by_id(user_id)
        return {
            "status": "win",
            "payout": payout,
            "new_balance": updated_user["balance"]
        }
    else:
        # Crashed before they could cash out (too late)
        details = f"Crashed! Rocket exploded at {crash_point:.2f}x (Tried cashing out at {body.multiplier:.2f}x)."
        models.add_game_record(user_id, "Crash Multiplier", crash_bet, 0, details, datetime.now().isoformat())
        
        updated_user = models.get_user_by_id(user_id)
        return {
            "status": "crash",
            "crash_point": crash_point,
            "new_balance": updated_user["balance"]
        }

# Game 7: Crash Auto-crashed Endpoint (called when ticker reaches crash point on client)
@app.post("/game/crash/crashed")
async def crashed_crash(request: Request):
    user_id = request.session.get("user_id")
    
    crash_bet = request.session.pop("crash_bet", None)
    crash_point = request.session.pop("crash_point", None)
    
    if crash_bet is not None and crash_point is not None:
        # Flight crashed and was not cashed out. Log loss in game history.
        details = f"Crashed! Rocket exploded at {crash_point:.2f}x."
        models.add_game_record(user_id, "Crash Multiplier", crash_bet, 0, details, datetime.now().isoformat())
        
    updated_user = models.get_user_by_id(user_id)
    return {"status": "resolved", "new_balance": updated_user["balance"]}

# Game 8: Scratch Card Buy Card
@app.post("/game/scratch/buy")
async def buy_scratch(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 10:
        return JSONResponse({"error": "Minimum bet is 10 credits."}, status_code=400)
        
    # Deduct bet immediately from balance
    models.update_user_balance(user_id, -body.bet)
    
    # 5 symbols in pool
    pool = ['🍒', '🍋', '🍇', '🔔', '💎']
    
    # Pure RNG — no manipulation
    # Generate 9 random symbols
    symbols = [random.choice(pool) for _ in range(9)]
    
    # Save card state in session
    request.session["scratch_symbols"] = symbols
    request.session["scratch_bet"] = body.bet
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "symbols": symbols,
        "new_balance": updated_user["balance"]
    }

# Game 8: Scratch Card Claim Payout
@app.post("/game/scratch/claim")
async def claim_scratch(request: Request, body: ScratchClaimRequest):
    user_id = request.session.get("user_id")
    
    symbols = request.session.pop("scratch_symbols", None)
    bet = request.session.pop("scratch_bet", None)
    
    if not symbols or not bet:
        return JSONResponse({"error": "No active scratch card found."}, status_code=400)
        
    if len(body.indices) != 3 or len(set(body.indices)) != 3:
        return JSONResponse({"error": "Must reveal exactly 3 unique cells."}, status_code=400)
        
    if not all(0 <= idx < 9 for idx in body.indices):
        return JSONResponse({"error": "Invalid cell indices revealed."}, status_code=400)
        
    # Get symbols at selected indices
    revealed_symbols = [symbols[idx] for idx in body.indices]
    unique_count = len(set(revealed_symbols))
    
    payout = 0
    win = False
    
    if unique_count == 1:
        # Match 3
        payout = bet * 15
        win = True
        details = f"Match 3! Revealed: {revealed_symbols[0]} {revealed_symbols[1]} {revealed_symbols[2]} (15x payout)."
    elif unique_count == 2:
        # Match 2
        payout = bet * 2
        win = True
        # Find which one matches
        matched = max(set(revealed_symbols), key=revealed_symbols.count)
        details = f"Match 2! Revealed: {revealed_symbols[0]} {revealed_symbols[1]} {revealed_symbols[2]} (2x payout)."
    else:
        details = f"No Match. Revealed: {revealed_symbols[0]} {revealed_symbols[1]} {revealed_symbols[2]}."
        
    # Write history and adjust balance if they won
    models.add_game_record(user_id, "Scratch Card", bet, payout, details, datetime.now().isoformat())
    
    # Refund/payout credit (deductions were done on buy)
    if payout > 0:
        models.update_user_balance(user_id, payout)
        models.add_user_winnings(user_id, payout)
        
    updated_user = models.get_user_by_id(user_id)
    return {
        "win": win,
        "payout": payout,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 9: Plinko Drop
@app.post("/game/plinko/play")
async def play_plinko(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 25:
        return JSONResponse({"error": "Minimum bet is 25 credits."}, status_code=400)
        
    # Plinko multipliers map: sum(5 decisions) where decision is 0 or 1.
    # Total right turns can be 0, 1, 2, 3, 4, or 5.
    # Map to multipliers: [3.0x, 1.5x, 1.0x, 1.0x, 0.5x, 0.0x]
    multipliers = [3.0, 1.5, 1.0, 1.0, 0.5, 0.0]
    
    # Pure RNG — no manipulation
    path = [random.choice([0, 1]) for _ in range(5)]
    right_turns = sum(path)
    mult = multipliers[right_turns]
    payout = int(body.bet * mult)
    
    details = f"Ball bounced through {path} and landed in bucket index {right_turns} ({mult}x payout)."
    models.add_game_record(user_id, "Plinko Drop", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "path": path,
        "payout": payout,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 10: War (Card Battle)
@app.post("/game/war/play")
async def play_war(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 20:
        return JSONResponse({"error": "Minimum bet is 20 credits."}, status_code=400)
        
    # Card values: 1 to 13
    suits = ['S', 'H', 'D', 'C']
    
    # Pure RNG — no manipulation
    player_card = random.randint(1, 13)
    player_suit = random.choice(suits)
    
    dealer_card = random.randint(1, 13)
    dealer_suit = random.choice(suits)
    
    card_names = {1: 'Ace', 11: 'Jack', 12: 'Queen', 13: 'King'}
    def cname(v):
        return card_names.get(v, str(v))
        
    if player_card > dealer_card:
        payout = int(body.bet * 1.9)
        details = f"Your Card: {cname(player_card)}, Dealer: {cname(dealer_card)}. You Win!"
    elif player_card == dealer_card:
        payout = body.bet  # refund
        details = f"Your Card: {cname(player_card)}, Dealer: {cname(dealer_card)}. Push (Tie)."
    else:
        payout = 0
        details = f"Your Card: {cname(player_card)}, Dealer: {cname(dealer_card)}. House Wins."
        
    models.add_game_record(user_id, "War (Card Battle)", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "player_card": player_card,
        "player_suit": player_suit,
        "dealer_card": dealer_card,
        "dealer_suit": dealer_suit,
        "payout": payout,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 11: Number Roulette
@app.post("/game/number_roulette/play")
async def play_number_roulette(request: Request, body: LuckyPlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 20:
        return JSONResponse({"error": "Minimum bet is 20 credits."}, status_code=400)
        
    if not (0 <= body.choice <= 36):
        return JSONResponse({"error": "Pick a number between 0 and 36."}, status_code=400)
        
    # Pure RNG — no manipulation
    roll = random.randint(0, 36)
    win = (body.choice == roll)
    payout = body.bet * 30 if win else 0
    
    if win:
        details = f"Chose: {body.choice}, Ball landed on: {roll}. Jackpots! 30x payout!"
    else:
        details = f"Chose: {body.choice}, Ball landed on: {roll}."
        
    models.add_game_record(user_id, "Number Roulette", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "payout": payout,
        "roll": roll,
        "details": details,
        "new_balance": updated_user["balance"]
    }

# Game 12: Wheel of Fortune
@app.post("/game/wheel/play")
async def play_wheel(request: Request, body: GamePlayRequest):
    user_id = request.session.get("user_id")
    
    if body.bet < 15:
        return JSONResponse({"error": "Minimum bet is 15 credits."}, status_code=400)
        
    # 8 segments: 3x, 0x, 1.5x, 0x, 2x, 0x, 5x, 0x
    segments = [3.0, 0.0, 1.5, 0.0, 2.0, 0.0, 5.0, 0.0]
    
    # Pure RNG — no manipulation
    roll_index = random.randint(0, 7)
    mult = segments[roll_index]
    payout = int(body.bet * mult)
    
    details = f"Wheel spun and landed on segment {roll_index} ({mult}x multiplier)."
    models.add_game_record(user_id, "Wheel of Fortune", body.bet, payout, details, datetime.now().isoformat())
    
    updated_user = models.get_user_by_id(user_id)
    return {
        "roll_index": roll_index,
        "multiplier": mult,
        "payout": payout,
        "details": details,
        "new_balance": updated_user["balance"]
    }


# --- Entrypoint ---

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="localhost", port=8000, reload=True)
