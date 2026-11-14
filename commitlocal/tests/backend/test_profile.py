# test_profile.py — the Profile tab's account routes (/api/profile...): each user only ever sees and changes their OWN
# account (no route takes a user id), name / username / email / phone / occupation / password rules, and the password
# hash never appears in any reply of /api/auth/* or /api/profile*.
import pytest
from sqlalchemy import select

import database
from conftest import PASSWORD, log_in, username_for
from models import LoginSession, User

NEW_PASSWORD = "Newer!Pass2"


def profile(client):
    res = client.get("/api/profile")
    assert res.status_code == 200
    return res.json()


def assert_no_hash(res):
    """No reply may contain the password hash, the word password_hash or a bcrypt "$2b$" prefix."""
    text = res.text
    assert "password_hash" not in text and "$2b$" not in text and "$2a$" not in text


@pytest.fixture
def two_users(new_client, sent_codes):
    """Asha and Bob, each logged in on their own "browser"."""
    asha = log_in(new_client(), sent_codes, "asha@example.com")
    bob = log_in(new_client(), sent_codes, "bob@example.com")
    return asha, bob


# ===== READ =====
def test_get_profile_shows_own_details_only(two_users):
    asha, bob = two_users
    assert profile(asha) == {"full_name": "Asha", "username": username_for("asha@example.com"),
                             "email": "asha@example.com", "phone": None, "occupation": None}
    assert profile(bob)["email"] == "bob@example.com" and profile(bob)["username"] == username_for("bob@example.com")


def test_profile_needs_login(client):
    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile/username", json={"username": "someone"}).status_code == 401


# ===== NAME + USERNAME =====
def test_change_name_rules(logged_in):  # same rules as registration: 1–100 characters, not blank, trimmed
    assert logged_in.put("/api/profile/name", json={"full_name": "  Asha Kumar "}).json()["full_name"] == "Asha Kumar"
    assert logged_in.put("/api/profile/name", json={"full_name": "   "}).json()["code"] == "NAME_REQUIRED"
    assert logged_in.put("/api/profile/name", json={"full_name": ""}).json()["code"] == "INVALID_NAME"
    assert logged_in.put("/api/profile/name", json={"full_name": "x" * 101}).status_code == 422
    assert profile(logged_in)["full_name"] == "Asha Kumar"


def test_change_username(logged_in):  # trimmed + lowercase; bad ones -> 422 INVALID_USERNAME, nothing changed
    assert logged_in.put("/api/profile/username", json={"username": " Asha.K-99 "}).json()["username"] == "asha.k-99"
    for bad in ["ab", "has space", "a" * 31, ""]:
        res = logged_in.put("/api/profile/username", json={"username": bad})
        assert res.status_code == 422 and res.json()["code"] == "INVALID_USERNAME"
    assert profile(logged_in)["username"] == "asha.k-99"


def test_username_taken_by_someone_else(two_users):  # another account's username (any case) -> 409 USERNAME_TAKEN
    asha, bob = two_users
    asha.put("/api/profile/username", json={"username": "asha"})
    res = bob.put("/api/profile/username", json={"username": "ASHA"})
    assert res.status_code == 409 and res.json()["code"] == "USERNAME_TAKEN"
    assert asha.put("/api/profile/username", json={"username": "Asha"}).status_code == 200  # own name again is fine
    assert profile(bob)["username"] == username_for("bob@example.com")


def test_old_account_without_username_can_add_one(logged_in):  # accounts made before 0008 have no username
    with database.open_db() as db:
        db.scalar(select(User)).username = None
    assert profile(logged_in)["username"] is None
    assert logged_in.put("/api/profile/username", json={"username": "asha_new"}).json()["username"] == "asha_new"


# ===== EMAIL =====
def test_change_email(logged_in):  # lowercase; needs the current password; the next login uses the new email
    res = logged_in.put("/api/profile/email", json={"email": "Asha.New@Example.COM", "current_password": PASSWORD})
    assert res.status_code == 200 and res.json()["email"] == "asha.new@example.com"
    new_login = logged_in.post("/api/auth/login", json={"email": "asha.new@example.com", "password": PASSWORD})
    assert new_login.status_code == 200
    assert logged_in.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 401


def test_change_email_bad_format_and_wrong_password(logged_in):
    res = logged_in.put("/api/profile/email", json={"email": "not-an-email", "current_password": PASSWORD})
    assert res.status_code == 422 and res.json()["code"] == "INVALID_EMAIL"
    res = logged_in.put("/api/profile/email", json={"email": "new@example.com", "current_password": "Wrong!Pass1"})
    assert res.status_code == 400 and res.json()["code"] == "WRONG_PASSWORD"
    assert logged_in.put("/api/profile/email", json={"email": "new@example.com"}).status_code == 422  # no password
    assert profile(logged_in)["email"] == "asha@example.com"


def test_change_email_already_used(two_users):  # someone else's email, also in another case -> 409 EMAIL_IN_USE
    asha, bob = two_users
    for email in ["bob@example.com", "BOB@Example.com"]:
        res = asha.put("/api/profile/email", json={"email": email, "current_password": PASSWORD})
        assert res.status_code == 409 and res.json()["code"] == "EMAIL_IN_USE"
    assert profile(asha)["email"] == "asha@example.com" and profile(bob)["email"] == "bob@example.com"


# ===== PHONE + OCCUPATION =====
def put_phone(client, phone, password=PASSWORD):
    return client.put("/api/profile/phone", json={"phone": phone, "current_password": password})


def put_email(client, email, password=PASSWORD):
    return client.put("/api/profile/email", json={"email": email, "current_password": password})


def test_phone_set_normalise_and_remove(logged_in):  # needs the current password (the phone can be a login)
    assert put_phone(logged_in, "+230 5123-4567").json()["phone"] == "+23051234567"
    res = put_phone(logged_in, "12")
    assert res.status_code == 422 and res.json()["code"] == "INVALID_PHONE"
    assert put_phone(logged_in, "52223333", "Wrong!Pass1").json()["code"] == "WRONG_PASSWORD"
    assert logged_in.put("/api/profile/phone", json={"phone": "52223333"}).status_code == 422  # no password
    assert profile(logged_in)["phone"] == "+23051234567"
    assert put_phone(logged_in, "").json()["phone"] is None
    assert put_phone(logged_in, None).json()["phone"] is None


def test_phone_taken_by_someone_else(two_users):  # two accounts can't share a phone -> 409 PHONE_TAKEN
    asha, bob = two_users
    assert put_phone(asha, "51234567").status_code == 200
    res = put_phone(bob, "+230 5123 4567")
    assert res.status_code == 409 and res.json()["code"] == "PHONE_TAKEN"
    assert put_phone(asha, "5123-4567").status_code == 200  # own number again is fine
    assert profile(bob)["phone"] is None


def test_cannot_remove_both_email_and_phone(logged_in):  # one of them must stay (it is how the user logs in)
    res = put_email(logged_in, "")
    assert res.status_code == 400 and res.json()["code"] == "NEED_EMAIL_OR_PHONE"
    assert put_phone(logged_in, "51234567").status_code == 200
    assert put_email(logged_in, "").json()["email"] is None  # phone left: the email may go
    res = put_phone(logged_in, "")
    assert res.status_code == 400 and res.json()["code"] == "NEED_EMAIL_OR_PHONE"
    assert profile(logged_in)["phone"] == "+23051234567"


def test_occupation_set_and_clear(logged_in):
    put = lambda value: logged_in.put("/api/profile/occupation", json={"occupation": value})  # noqa: E731
    assert put(" Student ").json()["occupation"] == "Student"
    assert put("Music teacher").json()["occupation"] == "Music teacher"  # own text, not only the suggestions
    assert put("x" * 61).status_code == 422
    assert put("   ").json()["occupation"] is None
    assert put(None).json()["occupation"] is None


def test_changes_never_touch_the_other_user(two_users):  # routes take no user id: Bob's edits only change Bob
    asha, bob = two_users
    bob.put("/api/profile/name", json={"full_name": "Bob"})
    put_phone(bob, "52223333")
    bob.put("/api/profile/occupation", json={"occupation": "Employed"})
    bob.put("/api/profile/username", json={"username": "bob_b"})
    assert profile(asha) == {"full_name": "Asha", "username": username_for("asha@example.com"),
                             "email": "asha@example.com", "phone": None, "occupation": None}
    me = bob.get("/api/auth/me").json()
    assert me["username"] == "bob_b" and me["email"] == "bob@example.com"
    assert "asha" not in bob.get("/api/profile").text


# ===== PASSWORD =====
def change_password(client, current=PASSWORD, new=NEW_PASSWORD, confirm=None):
    return client.put("/api/profile/password", json={"current_password": current, "new_password": new,
                                                     "confirm_password": new if confirm is None else confirm})


def test_password_wrong_current_weak_or_mismatched(logged_in):
    assert change_password(logged_in, current="Wrong!Pass1").json()["code"] == "WRONG_PASSWORD"
    assert change_password(logged_in, new="weak", confirm="weak").json()["code"] == "PASSWORD_WEAK"
    assert change_password(logged_in, confirm=NEW_PASSWORD + "x").json()["code"] == "PASSWORDS_DIFFERENT"
    assert change_password(logged_in, current="x" * 100).json()["code"] == "WRONG_PASSWORD"  # > 72 bytes: no crash
    assert logged_in.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 200


def test_password_change_success(new_client, sent_codes):  # new one works, old one doesn't; other devices logged out
    phone = log_in(new_client(), sent_codes)
    laptop = new_client()
    assert laptop.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 200
    laptop.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": sent_codes[-1]})
    res = change_password(phone)
    assert res.status_code == 200 and res.json()["code"] == "PASSWORD_CHANGED"
    assert phone.get("/api/profile").status_code == 200   # this device stays logged in
    assert laptop.get("/api/profile").status_code == 401  # the other device is logged out
    with database.open_db() as db:
        assert db.query(LoginSession).count() == 1
    fresh = new_client()
    assert fresh.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 401
    assert fresh.post("/api/auth/login", json={"email": "asha@example.com", "password": NEW_PASSWORD}).status_code == 200


# ===== THE HASH IS NEVER SENT =====
def test_no_reply_contains_the_password_hash(new_client, sent_codes):
    client = new_client()
    replies = [client.post("/api/auth/register", json={"full_name": "Asha", "username": "asha_k",
                                                       "email": "asha@example.com", "phone": "51234567",
                                                       "password": PASSWORD, "confirm_password": PASSWORD}),
               client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD})]
    replies.append(client.post("/api/auth/verify-code", json={"email": "asha@example.com", "code": sent_codes[-1]}))
    replies += [client.get("/api/auth/me"), client.put("/api/auth/language", json={"language": "fr"}),
                client.get("/api/profile"),
                client.put("/api/profile/name", json={"full_name": "Asha K"}),
                client.put("/api/profile/username", json={"username": "asha_kk"}),
                put_phone(client, "52223333"),
                client.put("/api/profile/occupation", json={"occupation": "Student"}),
                client.put("/api/profile/email", json={"email": "asha2@example.com", "current_password": PASSWORD}),
                client.put("/api/profile/email", json={"email": "x@example.com", "current_password": "Wrong!1aa"}),
                change_password(client, new="weak", confirm="weak"),
                change_password(client),
                client.post("/api/auth/resend-code", json={"email": "asha2@example.com"}),
                client.post("/api/auth/send-login-code", json={"email": "asha2@example.com"}),
                client.post("/api/auth/logout")]
    for res in replies:
        assert res.status_code < 500
        assert_no_hash(res)


# ===== MIGRATION 0008 KEEPS OLD ACCOUNTS =====
def test_migration_0008_keeps_existing_accounts(tmp_path):
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    database.connect(f"sqlite:///{tmp_path.as_posix()}/old.db")
    config = Config(str(database.BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(database.BACKEND_DIR / "migrations"))
    config.attributes["engine"] = database.engine
    command.upgrade(config, "0007")  # the database as it was before this change
    with database.engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users (id, email, password_hash, failed_attempts, is_locked, created_at) "
                                   "VALUES (:id, 'old@example.com', 'x', 0, 0, '2026-01-01')"), {"id": "a" * 32})
        connection.execute(sa.text("INSERT INTO profiles (id, user_id, full_name, updated_at) "
                                   "VALUES (:id, :user, 'Old User', '2026-01-01')"), {"id": "b" * 32, "user": "a" * 32})
        connection.execute(sa.text("INSERT INTO expenses (id, user_id, amount_cents, category, kind, description, date, "
                                   "is_fixed, source, created_at) VALUES (:id, :user, 1500, 'Other', 'need', '', "
                                   "'2026-01-02', 0, 'typed', '2026-01-02')"), {"id": "c" * 32, "user": "a" * 32})
    command.upgrade(config, "head")  # rebuilds `users` (SQLite batch): must NOT cascade-delete the user's rows
    with database.engine.begin() as connection:
        user = connection.execute(sa.text("SELECT email, username FROM users")).one()
        person = connection.execute(sa.text("SELECT full_name, phone, occupation FROM profiles")).one()
        assert tuple(user) == ("old@example.com", None) and tuple(person) == ("Old User", None, None)
        assert connection.execute(sa.text("SELECT amount_cents FROM expenses")).scalar() == 1500
    database.engine.dispose()
