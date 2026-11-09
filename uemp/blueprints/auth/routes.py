"""
auth routes — Authentication module.

LOGIN FLOW
    1. User submits email + password.
    2. If the account is locked (too many wrong tries), refuse.
    3. If the password is wrong, count the failure (lock after 5).
    4. If the account is inactive/suspended, refuse with a clear message.
    5. Otherwise log in, reset the failure counter, record the login in the
       audit trail, and redirect to the dashboard for the user's role
       ("role-based redirection").

We show the SAME error for "no such email" and "wrong password" so attackers
cannot use the login page to discover which emails exist.
"""

from urllib.parse import urlsplit

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ...extensions import db
from ...models import AccountStatus, User
from ...services import accounts, audit
from ...web import attempt
from . import bp
from .forms import ChangePasswordForm, LoginForm


def _is_safe_next(target: str | None) -> bool:
    """Only allow redirects to pages on THIS site (prevents open-redirect attacks)."""
    if not target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and target.startswith("/")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).filter_by(email=email))
        cfg = current_app.config

        if user and user.is_locked():
            flash(f"Too many failed attempts. Try again in {cfg['LOCKOUT_MINUTES']} minutes.", "danger")
        elif user is None or not user.check_password(form.password.data):
            if user:
                user.register_failed_login(cfg["MAX_FAILED_LOGINS"], cfg["LOCKOUT_MINUTES"])
                db.session.commit()
            flash("Incorrect email or password.", "danger")
        elif user.status != AccountStatus.ACTIVE:
            flash(f"Your account is {user.status}. Please contact the administrator.", "danger")
        else:
            # Clear any old session data first (prevents session-fixation attacks).
            session.clear()
            login_user(user, remember=form.remember.data)
            user.register_successful_login()
            audit.record(user, "auth.login", f"{user.email} signed in")
            db.session.commit()

            next_page = request.args.get("next")
            return redirect(next_page if _is_safe_next(next_page) else url_for("main.home"))

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # POST (not GET) so another site cannot log users out with a hidden image link.
    audit.record(current_user, "auth.logout", f"{current_user.email} signed out")
    db.session.commit()
    logout_user()
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Your current password is incorrect.", "danger")
        elif attempt(lambda: accounts.reset_password(current_user, current_user, form.new_password.data),
                     "Your password has been updated."):
            return redirect(url_for("main.home"))
    return render_template("auth/change_password.html", form=form)
