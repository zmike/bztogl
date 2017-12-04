import collections
import re


class User(collections.namedtuple('User', 'email username real_name id')):
    def display_name(self):
        if self.username is not None:
            real_name = (self.real_name + ' ') if self.real_name else ''
            return real_name + '`@{}`'.format(self.username)
        elif self.real_name:
            return self.real_name
        return '{}..@..{}'.format(self.email[:3], self.email[-6:])


class UserCache:
    def __init__(self, target, bugzilla):
        self._target = target
        self._bugzilla = bugzilla
        self._cache = {}

    def __getitem__(self, email):
        # some_project@gnome.bugs is the default assignee, it doesn't
        # correspond to a GitLab user and effectively means unassigned
        if email.endswith('gnome.bugs'):
            return None

        if email in self._cache:
            return self._cache[email]

        glu = self._target.find_user(email)
        if glu is not None:
            user = User(email=email, username=glu.username,
                        real_name=glu.name, id=glu.id)
            self._cache[email] = user
            return user

        bzu = self._bugzilla.getuser(email)
        # Heuristically remove "(not reading bugmail) or (not receiving
        # bugmail)"
        real_name = re.sub(r' \(not .+ing bugmail\)', '', bzu.real_name)
        user = User(email=email, real_name=real_name, username=None, id=None)
        self._cache[email] = user
        return user
