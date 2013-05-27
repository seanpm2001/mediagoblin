# GNU MediaGoblin -- federated, autonomous media hosting
# Copyright (C) 2011, 2012 MediaGoblin contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging

import wtforms

from mediagoblin import mg_globals
from mediagoblin.db.models import User
from mediagoblin.tools.mail import (normalize_email, send_email,
                                    email_debug_message)
from mediagoblin.tools.translate import lazy_pass_to_ugettext as _
from mediagoblin.tools.template import render_template
from mediagoblin.tools.pluginapi import hook_handle
from mediagoblin import auth

_log = logging.getLogger(__name__)

_log = logging.getLogger(__name__)

_log = logging.getLogger(__name__)


def normalize_user_or_email_field(allow_email=True, allow_user=True):
    """
    Check if we were passed a field that matches a username and/or email
    pattern.

    This is useful for fields that can take either a username or email
    address. Use the parameters if you want to only allow a username for
    instance"""
    message = _(u'Invalid User name or email address.')
    nomail_msg = _(u"This field does not take email addresses.")
    nouser_msg = _(u"This field requires an email address.")

    def _normalize_field(form, field):
        email = u'@' in field.data
        if email:  # normalize email address casing
            if not allow_email:
                raise wtforms.ValidationError(nomail_msg)
            wtforms.validators.Email()(form, field)
            field.data = normalize_email(field.data)
        else:  # lower case user names
            if not allow_user:
                raise wtforms.ValidationError(nouser_msg)
            wtforms.validators.Length(min=3, max=30)(form, field)
            wtforms.validators.Regexp(r'^\w+$')(form, field)
            field.data = field.data.lower()
        if field.data is None:  # should not happen, but be cautious anyway
            raise wtforms.ValidationError(message)
    return _normalize_field


class AuthError(Exception):
    def __init__(self):
        self.value = 'No Authentication Plugin is enabled and no_auth = false'\
                     ' in config!'

    def __str__(self):
        return repr(self.value)


def check_auth_enabled():
    no_auth = mg_globals.app_config['no_auth']
    auth_plugin = hook_handle('authentication')

    if no_auth == 'false' and not auth_plugin:
        raise AuthError

    if no_auth == 'true' and not auth_plugin:
        _log.warning('No authentication is enabled')
        return False
    else:
        return True


def no_auth_logout(request):
    """Log out the user if in no_auth mode"""
    if not mg_globals.app.auth:
        request.session.delete()


EMAIL_VERIFICATION_TEMPLATE = (
    u"http://{host}{uri}?"
    u"userid={userid}&token={verification_key}")


def send_verification_email(user, request):
    """
    Send the verification email to users to activate their accounts.

    Args:
    - user: a user object
    - request: the request
    """
    rendered_email = render_template(
        request, 'mediagoblin/auth/verification_email.txt',
        {'username': user.username,
         'verification_url': EMAIL_VERIFICATION_TEMPLATE.format(
                host=request.host,
                uri=request.urlgen('mediagoblin.auth.verify_email'),
                userid=unicode(user.id),
                verification_key=user.verification_key)})

    # TODO: There is no error handling in place
    send_email(
        mg_globals.app_config['email_sender_address'],
        [user.email],
        # TODO
        # Due to the distributed nature of GNU MediaGoblin, we should
        # find a way to send some additional information about the
        # specific GNU MediaGoblin instance in the subject line. For
        # example "GNU MediaGoblin @ Wandborg - [...]".
        'GNU MediaGoblin - Verify your email!',
        rendered_email)


EMAIL_FP_VERIFICATION_TEMPLATE = (
    u"http://{host}{uri}?"
    u"userid={userid}&token={fp_verification_key}")


def send_fp_verification_email(user, request):
    """
    Send the verification email to users to change their password.

    Args:
    - user: a user object
    - request: the request
    """
    rendered_email = render_template(
        request, 'mediagoblin/auth/fp_verification_email.txt',
        {'username': user.username,
         'verification_url': EMAIL_FP_VERIFICATION_TEMPLATE.format(
                host=request.host,
                uri=request.urlgen('mediagoblin.auth.verify_forgot_password'),
                userid=unicode(user.id),
                fp_verification_key=user.fp_verification_key)})

    # TODO: There is no error handling in place
    send_email(
        mg_globals.app_config['email_sender_address'],
        [user.email],
        'GNU MediaGoblin - Change forgotten password!',
        rendered_email)


def basic_extra_validation(register_form, *args):
    users_with_username = User.query.filter_by(
        username=register_form.username.data).count()
    users_with_email = User.query.filter_by(
        email=register_form.email.data).count()

    extra_validation_passes = True

    if users_with_username:
        register_form.username.errors.append(
            _(u'Sorry, a user with that name already exists.'))
        extra_validation_passes = False
    if users_with_email:
        register_form.email.errors.append(
            _(u'Sorry, a user with that email address already exists.'))
        extra_validation_passes = False

    return extra_validation_passes


def register_user(request, register_form):
    """ Handle user registration """
    extra_validation_passes = auth.extra_validation(register_form)

    if extra_validation_passes:
        # Create the user
        user = auth.create_user(register_form)

        # log the user in
        request.session['user_id'] = unicode(user.id)
        request.session.save()

        # send verification email
        email_debug_message(request)
        send_verification_email(user, request)
        return user

    return None


def check_login_simple(username, password, username_might_be_email=False):
    user = auth.get_user(username)
    if not user:
        _log.info("User %r not found", username)
        auth.fake_login_attempt()
        return None
    if not auth.check_password(password, user.pw_hash):
        _log.warn("Wrong password for %r", username)
        return None
    _log.info("Logging %r in", username)
    return user
