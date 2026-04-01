import streamlit as st
import pandas as pd
import sqlite3
import requests
from datetime import date
import matplotlib.pyplot as plt
import random

# PAGE CONFIG

st.set_page_config(page_title="Personal Health Tracker", layout="centered") #main title and layout
st.title("Personal Health Tracker")


# DATABASE FUNCTIONS

def get_connection():
    return sqlite3.connect("health_tracker.db", check_same_thread=False)

def create_tables():
    conn = get_connection()
    cur = conn.cursor()

    # Users table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        password TEXT
    )
    """)

    # Logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        log_date TEXT,
        sleep_hours REAL,
        water_intake REAL,
        mood INTEGER,
        headache INTEGER,
        screen_hours REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Goal progress table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS goal_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        log_date TEXT,
        sleep_progress REAL,
        water_progress REAL,
        screen_progress REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # User personal goals table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        sleep_goal REAL,
        water_goal REAL,
        screen_goal REAL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()

create_tables() #create tables if they don't exist when the app starts 


# USER FUNCTIONS

def add_user(name, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users (name, password) VALUES (?, ?)",
        (name, password)
    )
    conn.commit()
    conn.close() #close connection after adding user

def login_user(name, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name=? AND password=?", (name, password))
    user = cur.fetchone()
    conn.close()
    return user #returns user record if found, otherwise None


# GOAL FUNCTION

def set_user_goals(user_name, sleep_goal, water_goal, screen_goal):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE name=?", (user_name,))
    user_id = cur.fetchone()[0] #get user id based on username to link goals to the correct user

    # Insert or update
    cur.execute("""
    INSERT INTO user_goals (user_id, sleep_goal, water_goal, screen_goal)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        sleep_goal=excluded.sleep_goal,
        water_goal=excluded.water_goal,
        screen_goal=excluded.screen_goal
    """, (user_id, sleep_goal, water_goal, screen_goal))
    conn.commit()
    conn.close() #close connection after setting goals

def get_user_goals(user_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE name=?", (user_name,))
    user_id = cur.fetchone()[0] #get user id based on username to retrieve goals for the correct user

    cur.execute("SELECT sleep_goal, water_goal, screen_goal FROM user_goals WHERE user_id=?", (user_id,))
    result = cur.fetchone()
    conn.close()
    if result:
        return {"sleep_goal": result[0], "water_goal": result[1], "screen_goal": result[2]}
    else:
        # default goals
        return {"sleep_goal": 8, "water_goal": 2.5, "screen_goal": 6} #return default goals if user hasn't set any yet


# LOG FUNCTIONS

def add_log(user_name, log):
    goals = get_user_goals(user_name)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE name=?", (user_name,))
    result = cur.fetchone() #get user id based on username to link log to the correct user

    if result:
        user_id = result[0] #get user id from query result to use in log insertion and goal progress calculation

        # Insert log
        cur.execute("""
            INSERT INTO logs (
                user_id, log_date, sleep_hours, water_intake, mood, headache, screen_hours
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            str(log["date"]),
            log["sleep"],
            log["water"],
            log["mood"],
            log["headache"],
            log["screen"]
        ))

        # Calculate goal progress based on personal goals
        sleep_progress = min(log["sleep"] / goals["sleep_goal"], 1.0)
        water_progress = min(log["water"] / goals["water_goal"], 1.0)
        screen_progress = 1 - min(log["screen"] / goals["screen_goal"], 1.0) #for screen time, less is better, so we invert the progress calculation

        # Save goal progress
        cur.execute("""
            INSERT INTO goal_progress (
                user_id, log_date, sleep_progress, water_progress, screen_progress
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            user_id,
            str(log["date"]),
            sleep_progress,
            water_progress,
            screen_progress
        ))

        conn.commit()
    conn.close()

def load_logs(user_name):
    conn = get_connection()
    query = """
    SELECT log_date, sleep_hours, water_intake, mood, headache, screen_hours
    FROM logs
    JOIN users ON logs.user_id = users.id
    WHERE users.name = ?
    ORDER BY log_date
    """
    df = pd.read_sql_query(query, conn, params=(user_name,))
    conn.close()
    return df # return logs as a DataFrame for easier manipulation and visualization

def load_goal_progress(user_name):
    conn = get_connection()
    query = """
    SELECT log_date, sleep_progress, water_progress, screen_progress
    FROM goal_progress
    JOIN users ON goal_progress.user_id = users.id
    WHERE users.name = ?
    ORDER BY log_date
    """
    df = pd.read_sql_query(query, conn, params=(user_name,))
    conn.close()
    return df # return goal progress as a DataFrame for easier manipulation and visualization


# HEALTH TIP FUNCTION WITH FALLBACK

def get_health_topics():
    fallback_tips = [
        "Drink at least 2–3 liters of water daily.",
        "Aim for 7–9 hours of sleep each night.",
        "Take regular breaks from screens every hour.",
        "Eat more fruits and vegetables daily.",
        "Include some physical activity in your day.",
        "Practice deep breathing or meditation to reduce stress.",
        "Limit sugary snacks and processed foods.",
        "Keep a consistent sleep schedule.",
        "Spend time outdoors for fresh air and sunlight."
    ]
    
    url = "https://odphp.health.gov/myhealthfinder/api/v4/itemlist.json?Type=topic"
    try:
        response = requests.get(url, timeout=6)
        response.raise_for_status()
        data = response.json()
        items = data.get("Result", {}).get("Items", [])
        tips = [item.get("Title") for item in items if item.get("Title")]
        return tips if tips else fallback_tips
    except Exception:
        return fallback_tips


#SESSION STATE

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False


# SIDEBAR LOGIN

st.sidebar.header("Account")

if not st.session_state.logged_in:
    login_name = st.sidebar.text_input("Username")
    login_password = st.sidebar.text_input("Password", type="password")

    if st.sidebar.button("Login"):
        user = login_user(login_name, login_password)
        if user:
            st.session_state.logged_in = True
            st.session_state.user = login_name
            st.sidebar.success("Logged in!")
        else:
            st.sidebar.error("Invalid credentials")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Create Account")
    new_user = st.sidebar.text_input("New Username")
    new_password = st.sidebar.text_input("New Password", type="password")

    if st.sidebar.button("Register"):
        if new_user and new_password:
            add_user(new_user, new_password)
            st.sidebar.success("Account created!")

else:
    selected_user = st.session_state.user
    st.sidebar.success(f"Logged in as {selected_user}")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()


# MAIN APP

if st.session_state.logged_in:
    selected_user = st.session_state.user
    st.header(f"Welcome, {selected_user}!")

    #  Set Personal Goals 
    st.header("Set Personal Goals")
    current_goals = get_user_goals(selected_user)

    sleep_goal = st.number_input("Sleep Goal (hrs)", 1.0, 24.0, float(current_goals["sleep_goal"]))
    water_goal = st.number_input("Water Goal (L)", 0.5, 10.0, float(current_goals["water_goal"]))
    screen_goal = st.number_input("Screen Limit (hrs)", 0.0, 24.0, float(current_goals["screen_goal"]))

    if st.button("Save Goals"):
        set_user_goals(selected_user, sleep_goal, water_goal, screen_goal)
        st.success("Goals saved!")

    # Log Daily Health 
    st.header("Log Daily Health")
    log_date = st.date_input("Date", value=date.today())
    sleep = st.number_input("Sleep Hours", 0.0, 24.0, 7.0)
    water = st.number_input("Water Intake (L)", 0.0, 10.0, 2.0)
    mood = st.number_input("Mood (0–10)", 0, 10, 7)
    headache = st.number_input("Headache (0–10)", 0, 10, 0)
    screen = st.number_input("Screen Hours", 0.0, 24.0, 5.0)

    if st.button("Save Log"):
        add_log(selected_user, {
            "date": log_date,
            "sleep": sleep,
            "water": water,
            "mood": mood,
            "headache": headache,
            "screen": screen
        })
        st.success("Log saved!")

    # Daily Goal Progress Bar Graph 
    st.header("Daily Goal Progress (Bar Graph for 2026)")
    df = load_logs(selected_user)

    if not df.empty:
        df["log_date"] = pd.to_datetime(df["log_date"], errors="coerce")
        df = df.dropna(subset=["log_date"])
        df_2026 = df[df["log_date"].dt.year == 2026].sort_values("log_date")

        if not df_2026.empty:
            goals = get_user_goals(selected_user)
            df_2026["sleep_progress"] = df_2026["sleep_hours"] / goals["sleep_goal"]
            df_2026["water_progress"] = df_2026["water_intake"] / goals["water_goal"]
            df_2026["screen_progress"] = 1 - (df_2026["screen_hours"] / goals["screen_goal"])
            df_2026[["sleep_progress", "water_progress", "screen_progress"]] = df_2026[
                ["sleep_progress", "water_progress", "screen_progress"]
            ].clip(0, 1)

            fig, ax = plt.subplots(figsize=(12, 6))
            width = 0.25
            x = range(len(df_2026))
            ax.bar([i - width for i in x], df_2026["sleep_progress"], width=width, label="Sleep")
            ax.bar(x, df_2026["water_progress"], width=width, label="Water")
            ax.bar([i + width for i in x], df_2026["screen_progress"], width=width, label="Screen")
            ax.set_xticks(x)
            ax.set_xticklabels(df_2026["log_date"].dt.strftime("%b %d"), rotation=45)
            ax.set_ylim(0, 1.0)
            ax.set_ylabel("Goal Completion (%)")
            ax.set_title("Daily Goal Progress for 2026")
            ax.legend()
            ax.grid(axis='y')
            st.pyplot(fig)
        else:
            st.warning("No logs for 2026 yet. Add daily entries to see the bar graph.")
    else:
        st.info("No logs found. Start logging your health data!")

    # Saved Goal Progress 
    st.header("Saved Goal Progress Over Time")
    df_progress = load_goal_progress(selected_user)
    if not df_progress.empty:
        df_progress["log_date"] = pd.to_datetime(df_progress["log_date"])
        st.line_chart(df_progress.set_index("log_date")[["sleep_progress", "water_progress", "screen_progress"]])
    else:
        st.info("No goal progress yet. Log your health to start tracking!")

    #  Health Tip 
    st.header("Health Tip")
    if st.button("Get Tip"):
        tips = get_health_topics()
        st.info(random.choice(tips))