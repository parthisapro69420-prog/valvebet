import datetime
from database import get_db_connection

# --- User CRUD operations ---

def create_user(username: str, password_hash: str) -> int:
    """Creates a new user with default balance of 500 and returns their ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash, balance, banned, total_won) VALUES (?, ?, 500, 0, 0)",
            (username, password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_user_by_username(username: str):
    """Retrieves user by username."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int):
    """Retrieves user by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_balance(user_id: int, amount: int):
    """Updates user balance by adding/subtracting the amount. Can result in negative balance."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def add_user_winnings(user_id: int, payout: int):
    """Accumulates all-time credits won for the leaderboard."""
    if payout <= 0:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET total_won = total_won + ? WHERE id = ?", (payout, user_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def ban_user(user_id: int):
    """Bans the user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET banned = 1 WHERE id = ?", (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# --- Loan operations ---

def create_loan(user_id: int, amount: int, repay_amount: int, created_at: str, deadline: str):
    """Creates a loan and immediately credits the amount to the user's balance."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if user already has an active loan
        cursor.execute("SELECT id FROM loans WHERE user_id = ? AND active = 1", (user_id,))
        if cursor.fetchone():
            raise ValueError("An active loan already exists.")
        
        # Create loan record
        cursor.execute(
            "INSERT INTO loans (user_id, amount, repay_amount, created_at, deadline, active) VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, amount, repay_amount, created_at, deadline)
        )
        
        # Credit user balance
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_active_loan(user_id: int):
    """Gets the active loan for a user if any."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM loans WHERE user_id = ? AND active = 1", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def repay_loan(loan_id: int, user_id: int, repay_amount: int):
    """Repays the loan by deducting repay_amount from the user's balance and marking it inactive."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check active status
        cursor.execute("SELECT active FROM loans WHERE id = ? AND user_id = ?", (loan_id, user_id))
        row = cursor.fetchone()
        if not row or row['active'] == 0:
            raise ValueError("Loan is not active or does not exist.")
        
        # Mark loan as inactive
        cursor.execute("UPDATE loans SET active = 0 WHERE id = ?", (loan_id,))
        
        # Deduct repay amount from user's balance
        cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (repay_amount, user_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_expired_active_loans(current_time_iso: str):
    """Gets all active loans that have passed their deadline."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM loans WHERE active = 1 AND deadline < ?", (current_time_iso,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# --- Game History operations ---

def add_game_record(user_id: int, game_name: str, bet: int, payout: int, result_details: str, timestamp: str):
    """Records a game result in game_history, adjusts balance and updates total won."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Insert history record
        cursor.execute(
            "INSERT INTO game_history (user_id, game_name, bet, payout, result_details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, game_name, bet, payout, result_details, timestamp)
        )
        
        # Adjust user balance: subtract bet, add payout
        net_change = payout - bet
        cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (net_change, user_id))
        
        # If there's a payout, accumulate in total_won
        if payout > 0:
            cursor.execute("UPDATE users SET total_won = total_won + ? WHERE id = ?", (payout, user_id))

        # --- DEBT FLOOR: instant ban if balance reaches -500 or below ---
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row and row["balance"] <= -500:
            cursor.execute("UPDATE users SET banned = 1 WHERE id = ?", (user_id,))
            print(f"[AUTO-BAN] User {user_id} banned: balance hit {row['balance']} (≤ -500 debt floor).")
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_user_history(user_id: int, limit: int = 10):
    """Fetches user's recent game history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM game_history WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# --- Leaderboard operations ---

def get_top_users(limit: int = 10):
    """Retrieves top users sorted by all-time credits won."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, total_won, balance FROM users ORDER BY total_won DESC, username ASC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_rank_info(user_id: int):
    """Returns the rank, username, total_won, and balance of a specific user on the leaderboard."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rank, username, total_won, balance FROM (
            SELECT id, username, total_won, balance,
                   RANK() OVER (ORDER BY total_won DESC, username ASC) as rank
            FROM users
        ) WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
