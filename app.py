import os
import secrets
from urllib.parse import urlencode

import requests
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from dotenv import load_dotenv
from models import db, Member, APChange

load_dotenv()

app = Flask(__name__)

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is missing. "
        "Configure it in your local .env file or in Render Environment."
    )

app.config.update(
    SECRET_KEY=secret_key,
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///aura.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=600,
)

db.init_app(app)

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "http://127.0.0.1:5000/callback",
)
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")

# Staff access is granted only to these explicitly approved Discord user IDs.
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


def oauth_settings_present():
    return all(
        [
            DISCORD_CLIENT_ID,
            DISCORD_CLIENT_SECRET,
            DISCORD_GUILD_ID,
            DISCORD_REDIRECT_URI,
        ]
    )


@app.route("/")
def leaderboard():
    members = Member.query.order_by(
        Member.aura_points.desc(),
        Member.display_name.asc(),
    ).all()
    return render_template("leaderboard.html", members=members)


@app.route("/login")
def login():
    if not oauth_settings_present():
        app.logger.error("Discord OAuth configuration is incomplete.")
        return (
            "Discord OAuth settings are missing. Check the environment "
            "variables configured in Render.",
            500,
        )

    # A new state is generated for each login attempt.
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session.permanent = True

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }

    return redirect(
        "https://discord.com/oauth2/authorize?" + urlencode(params)
    )


@app.route("/callback")
def callback():
    # Do not consume a callback URL repeatedly by refreshing it.
    if request.args.get("error"):
        session.pop("oauth_state", None)
        flash("Discord login was cancelled or denied.")
        return redirect(url_for("leaderboard"))

    code = request.args.get("code")
    returned_state = request.args.get("state")
    saved_state = session.pop("oauth_state", None)

    if (
        not code
        or not returned_state
        or not saved_state
        or not secrets.compare_digest(returned_state, saved_state)
    ):
        app.logger.warning(
            "OAuth state validation failed. code_present=%s, "
            "returned_state_present=%s, saved_state_present=%s, "
            "session_cookie_present=%s",
            bool(code),
            bool(returned_state),
            bool(saved_state),
            bool(request.cookies.get(app.config.get("SESSION_COOKIE_NAME", "session"))),
        )
        return (
            "Invalid login state. Please open /login in a new tab and "
            "complete the Discord login once. Do not refresh this page.",
            400,
        )

    if not oauth_settings_present():
        app.logger.error("Discord OAuth configuration is incomplete at callback.")
        return "Discord OAuth settings are missing. Check Render Environment.", 500

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
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )

        if token_response.status_code == 429:
            app.logger.warning(
                "Discord OAuth token endpoint rate limited. "
                "Retry-After=%s, Scope=%s, Global=%s",
                token_response.headers.get("Retry-After", "not provided"),
                token_response.headers.get("X-RateLimit-Scope", "not provided"),
                token_response.headers.get("X-RateLimit-Global", "not provided"),
            )
            return (
                "Discord is temporarily rate-limiting login attempts. "
                "Please wait before trying again; do not refresh this page.",
                429,
                {
                    "Retry-After": token_response.headers.get(
                        "Retry-After", "60"
                    )
                },
            )

        token_response.raise_for_status()
        token_data = token_response.json()
        access_token = token_data["access_token"]

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

    except requests.Timeout:
        app.logger.exception("Timed out while contacting Discord OAuth API.")
        return "Discord took too long to respond. Please try again later.", 502
    except requests.RequestException:
        app.logger.exception("Discord OAuth API request failed.")
        return "Discord login could not be completed. Check Render logs.", 502
    except (ValueError, KeyError):
        app.logger.exception("Discord returned an unexpected OAuth response.")
        return "Discord returned an unexpected response. Please try again later.", 502

    user_id = str(user.get("id", ""))

    is_server_member = any(
        str(guild.get("id")) == DISCORD_GUILD_ID
        for guild in guilds
    )
    if not is_server_member:
        session.clear()
        return "You must belong to our Discord server to continue.", 403

    if user_id not in STAFF:
        session.clear()
        return "Your Discord account is not on the staff allowlist.", 403

    # Clear temporary OAuth state, then establish the authenticated session.
    session.clear()
    session.permanent = True
    session["discord_id"] = user_id
    session["discord_username"] = user.get("username", "Unknown")
    session["csrf_token"] = secrets.token_urlsafe(32)

    return redirect(url_for("staff_dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    submitted_csrf = request.form.get("csrf_token", "")
    saved_csrf = session.get("csrf_token", "")

    if (
        not submitted_csrf
        or not saved_csrf
        or not secrets.compare_digest(submitted_csrf, saved_csrf)
    ):
        return "Invalid security token. Refresh the page and try again.", 400

    session.clear()
    return redirect(url_for("leaderboard"))


@app.route("/staff", methods=["GET", "POST"])
def staff_dashboard():
    if not staff_required():
        return redirect(url_for("login"))

    staff = current_staff()

    if request.method == "POST":
        submitted_csrf = request.form.get("csrf_token", "")
        saved_csrf = session.get("csrf_token", "")
        if (
            not submitted_csrf
            or not saved_csrf
            or not secrets.compare_digest(submitted_csrf, saved_csrf)
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
            app.logger.exception("Failed to save AP change.")
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