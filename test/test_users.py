import collections
from unittest import mock

import pytest

from bztogl import users

# NB. All names are randomly generated

# Mock GitLab and Bugzilla user records
GLU = collections.namedtuple('GLU', 'id name username')
BZU = collections.namedtuple('BZU', 'email real_name')


class TestUser:
    def test_display_name_with_gitlab_username(self):
        user = users.User(id=5, email='shaniya.clements@src.gnome.org',
                          real_name='Shaniya Clements', username='shaniya')
        assert user.display_name() == 'Shaniya Clements `@shaniya`'

    def test_display_name_with_no_gitlab_username(self):
        user = users.User(id=None, email='aarav.paul@src.gnome.org',
                          real_name='Aarav Paul', username=None)
        assert user.display_name() == 'Aarav Paul'

    def test_display_name_with_email_only(self):
        user = users.User(id=None, email='mariam.kane@src.gnome.org',
                          real_name=None, username=None)
        assert user.display_name() == 'mar..@..me.org'


@pytest.fixture
def cache():
    gitlab_users = {
        'jsparks@src.gnome.org': GLU(1, 'Jamar Sparks', 'jamars'),
    }
    gitlab = mock.Mock()
    gitlab.find_user = mock.Mock(side_effect=gitlab_users.get)

    bugzilla_users = {
        'gjs-maint@gnome.bugs': BZU('gjs-maint@gnome.bugs', ''),
        'jsparks@src.gnome.org': BZU('jsparks@src.gnome.org', 'Jamar Sparks'),
        'swoods@src.gnome.org': BZU('swoods@src.gnome.org', 'Sydnee Woods'),
        'jbriggs@src.gnome.org': BZU('jbriggs@src.gnome.org',
                                     'Jeffrey (not reading bugmail) Briggs'),
    }
    bugzilla = mock.Mock()
    bugzilla.getuser = mock.Mock(side_effect=bugzilla_users.get)

    return users.UserCache(gitlab, bugzilla)


class TestUserCache:
    def test_gnome_bugs_user_is_not_treated_as_real_user(self, cache):
        assert cache['gjs-maint@gnome.bugs'] is None

    def test_lookup_gitlab_user(self, cache):
        user = cache['jsparks@src.gnome.org']
        assert user.email == 'jsparks@src.gnome.org'
        assert user.real_name == 'Jamar Sparks'
        assert user.username == 'jamars'
        assert user.id == 1

    def test_lookup_bugzilla_user_not_on_gitlab(self, cache):
        user = cache['swoods@src.gnome.org']
        assert user.email == 'swoods@src.gnome.org'
        assert user.real_name == 'Sydnee Woods'
        assert user.id is None
        assert user.username is None

    def test_lookup_bugzilla_user_with_junk_in_username(self, cache):
        user = cache['jbriggs@src.gnome.org']
        assert user.real_name == 'Jeffrey Briggs'
