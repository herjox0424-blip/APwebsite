
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import (
    Flask, render_template, redirect, request,
    session, url_for, flash
)
from dotenv import load_dotenv
from models import db, Member, APChange


load_dotenv()

app = Flask(__name__)

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is missing. "
        "Configure it in your .env file locally or in Render Environment."
    )

app.config["SECRET_KEY"] = secret_key
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///aura.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "http://127.0.0.1:5000/callback"
)
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# App-level staff permissions, matched by Discord user ID.

STAFF = {
    "1386924961901576376": {
        "name": "Cassy",
        "role": "Co-Owner",
        "can_manage_staff": True,
    },
    "1500016860035416114": {
        "name": "Sfjsj",
        "role": "Head Moderator",
        "can_manage_staff": False,
    },
    "815694492316991549": {
        "name": "Tvpesk",
        "role": "Moderator",
        "can_manage_staff": False,
    },
    "1472880217675530240": {
        "name": "Dusky",
        "role": "Moderator",
        "can_manage_staff": False,
    },
    "1526153680666234991": {
        "name": "Ly",
        "role": "Moderator",
        "can_manage_staff": False,
    },
    "1337799636651479164": {
        "name": "Clover",
        "role": "Moderator",
        "can_manage_staff": False,
    },
    "1500334645928263863": {
        "name": "Jox",
        "role": "Owner",
        "can_manage_staff": True,
    },
}



def current_staff():
    user_id = session.get("discord_id")
    return STAFF.get(user_id)


def staff_required():
    return current_staff() is not None


@app.route("/")
def leaderboard():
    members = Member.query.order_by(
        Member.aura_points.desc(),
        Member.display_name.asc()
    ).all()

    return render_template("leaderboard.html", members=members)


@app.route("/login")
def login():
    if not all([
        DISCORD_CLIENT_ID,
        DISCORD_CLIENT_SECRET,
        DISCORD_GUILD_ID,
        DISCORD_REDIRECT_URI,
    ]):
        return "Discord OAuth settings are missing from .env.", 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }

    return redirect(
        "https://discord.com/oauth2/authorize?"
        + urlencode(params)
    )


@app.route("/callback")
def callback():
    if request.args.get("error"):
        flash("Discord login was cancelled or denied.")
        return redirect(url_for("leaderboard"))

    code = request.args.get("code")
    state = request.args.get("state")

    saved_state = session.pop("oauth_state", None)

    if not code or not saved_state or not secrets.compare_digest(
        state or "", saved_state
    ):
        return "Invalid login state. Please try logging in again.", 400

    try:
        token_response = requests.post(
            "https://discord.com/api/v10/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            timeout=15,
                )

        if token_response.status_code == 429:
            app.logger.warning(
                "Discord OAuth rate limited. Retry-After: %s",
                token_response.headers.get("Retry-After", "not provided"),
            )

        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {access_token}"}

        user_response = requests.get(
            "https://discord.com/api/v10/users/@me",
            headers=headers,
            timeout=15,
        )
        user_response.raise_for_status()
        user = user_response.json()

        guilds_response = requests.get(
            "https://discord.com/api/v10/users/@me/guilds",
            headers=headers,
            timeout=15,
        )
        guilds_response.raise_for_status()
        guilds = guilds_response.json()

    except (requests.RequestException, ValueError, KeyError):
        app.logger.exception("Discord OAuth request failed")
        return (
            "Discord login failed. Check your OAuth settings and try again.",
            502,
        )

    user_id = str(user.get("id", ""))

    # Verify the account belongs to the configured Discord server.
    is_server_member = any(
        str(guild.get("id")) == DISCORD_GUILD_ID
        for guild in guilds
    )

    if not is_server_member:
        session.clear()
        return "You must belong to our Discord server to continue.", 403

    # Only explicitly approved Discord IDs can enter the staff area.
    if user_id not in STAFF:
        session.clear()
        return "Your Discord account is not on the staff allowlist.", 403

    session.clear()
    session["discord_id"] = user_id
    session["discord_username"] = user.get("username", "Unknown")
    session["csrf_token"] = secrets.token_urlsafe(32)

    return redirect(url_for("staff_dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    if not secrets.compare_digest(
        request.form.get("csrf_token", ""),
        session.get("csrf_token", ""),
    ):
        return "Invalid security token.", 400

    session.clear()
    return redirect(url_for("leaderboard"))


@app.route("/staff", methods=["GET", "POST"])
def staff_dashboard():
    if not staff_required():
        return redirect(url_for("login"))

    staff = current_staff()

    if request.method == "POST":
        if not secrets.compare_digest(
            request.form.get("csrf_token", ""),
            session.get("csrf_token", ""),
        ):
            return "Invalid security token. Refresh and try again.", 400

        try:
            member_id = int(request.form.get("member_id", ""))
            amount = int(request.form.get("amount", ""))
        except (TypeError, ValueError):
            flash("Choose a member and enter a whole-number AP change.")
            return redirect(url_for("staff_dashboard"))

        reason = request.form.get("reason", "").strip()

        if not reason or len(reason) > 250:
            flash("Reason is required and must be 250 characters or fewer.")
            return redirect(url_for("staff_dashboard"))

        member = db.session.get(Member, member_id)

        if member is None:
            flash("That member could not be found.")
            return redirect(url_for("staff_dashboard"))

        old_points = member.aura_points
        new_points = old_points + amount

        if amount == 0:
            flash("The AP change must not be zero.")
            return redirect(url_for("staff_dashboard"))

        if new_points < 0:
            flash("A member's AP cannot become negative.")
            return redirect(url_for("staff_dashboard"))

        entry = APChange(
            member_id=member.id,
            amount=amount,
            old_points=old_points,
            new_points=new_points,
            reason=reason,
            admin_name=staff["name"],
            actor_discord_id=session["discord_id"],
        )

        try:
            member.aura_points = new_points
            db.session.add(entry)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to save AP change")
            flash("The AP change could not be saved.")
            return redirect(url_for("staff_dashboard"))

        flash(
            f"Updated {member.display_name}: "
            f"{old_points} → {new_points} AP."
        )
        return redirect(url_for("staff_dashboard"))

    members = Member.query.order_by(Member.display_name.asc()).all()

    return render_template(
        "staff.html",
        members=members,
        staff=staff,
        csrf_token=session["csrf_token"],
    )


@app.route("/history")
def history():
    if not staff_required():
        return redirect(url_for("login"))

    entries = APChange.query.order_by(
        APChange.created_at.desc(),
        APChange.id.desc(),
    ).all()

    return render_template(
        "history.html",
        entries=entries,
        staff=current_staff(),
        csrf_token=session["csrf_token"],
    )


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)
