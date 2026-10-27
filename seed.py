
from app import app
from models import db, Member

SEED_MEMBERS = [
    ("1386924961901576376", ".limieszy (Co-Owner)", 2170),
    ("1493521025395068948", "pi.qt", 1058),
    ("825250962075287572", "syno963", 780),
    ("1459819492644356231", "yo038653", 345),
    ("1372629786626887761", "josh15ok", 200),
    ("1159584442659131543", "elcizmit0", 130),
    ("1009714933430235167", "a_1703.", 125),
    ("1218991911033896961", "a_glitched_person.", 125),
    ("1381142241728528455", "gws_c00lk1dd", 100),
    ("1527721353564782748", "ki.anqp.", 100),
    ("1388882734142853331", "probablynotyuta", 75),
    ("1472880217675530240", "duskyyducky", 50),
    ("815694492316991549", "tvpesk", 31),
    ("1500016860035416114", "sfjsj_is_happyheh.", 25),
]

with app.app_context():
    keep_ids = {str(discord_id) for discord_id, _, _ in SEED_MEMBERS}

    added = 0
    updated = 0
    removed = 0

    # Remove members that are no longer in the list.
    existing_members = Member.query.all()

    for member in existing_members:
        if str(member.discord_id) not in keep_ids:
            db.session.delete(member)
            removed += 1

    # Add or update members in the current list.
    for discord_id, name, points in SEED_MEMBERS:
        member = Member.query.filter_by(
            discord_id=str(discord_id)
        ).first()

        if member is None:
            member = Member(
                discord_id=str(discord_id),
                display_name=name,
                aura_points=points
            )
            db.session.add(member)
            added += 1
        else:
            member.display_name = name
            member.aura_points = points
            updated += 1

    db.session.commit()

    print("================================")
    print("AuraLeaderboard sync complete!")
    print(f"New members added: {added}")
    print(f"Existing members updated: {updated}")
    print(f"Members removed: {removed}")
    print(f"Total members now: {Member.query.count()}")
    print("================================")
