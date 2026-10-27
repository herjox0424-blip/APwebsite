
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discord_id = db.Column(db.String(30), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    aura_points = db.Column(db.Integer, default=0, nullable=False)

    rewards = db.relationship("Reward", backref="member", lazy=True)


class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("member.id"), nullable=False
    )
    description = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default="pending", nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), default=utc_now, nullable=False
    )


class APChange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(
        db.Integer, db.ForeignKey("member.id"), nullable=False
    )

    # Positive = AP awarded; negative = AP deducted.
    amount = db.Column(db.Integer, nullable=False)

    # Total before and after the change.
    # Nullable so existing history entries remain compatible.
    old_points = db.Column(db.Integer, nullable=True)
    new_points = db.Column(db.Integer, nullable=True)

    reason = db.Column(db.String(250), nullable=False)

    # Keep the existing field for compatibility.
    admin_name = db.Column(db.String(100), nullable=False)

    # Discord account that performed the action.
    actor_discord_id = db.Column(db.String(30), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), default=utc_now, nullable=False
    )
