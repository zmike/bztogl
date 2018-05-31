import collections
import re
import pickle


class User(collections.namedtuple('User', 'email username real_name id')):
    def display_name(self):
        if self.username is not None:
            real_name = (self.real_name + ' ') if self.real_name else ''
            return real_name + '`@{}`'.format(self.username)
        elif self.real_name:
            return self.real_name
        return '{}..@..{}'.format(self.email[:3], self.email[-6:])


class UserCache:
    def __init__(self, target, bugzilla, product):
        self._target = target
        self._bugzilla = bugzilla
        self._gitlab_emails_cache = {}
        self._users_cache = {}

        self._gitlab_emails_cache = self._retrieve_gitlab_emails_cache()
        self._save_gitlab_emails_cache()

        components = self._bugzilla.getcomponentsdetails(product)
        self._default_emails = set(c['initialowner']
                                   for c in components.values())

    def __getitem__(self, email):
        # Default assignees on GNOME projects don't correspond to a GitLab
        # user, and effectively mean unassigned
        # Except fd.o doesn't use these.
        # if email in self._default_emails:
            # return None

        if email in self._users_cache:
            return self._users_cache[email]

        if email in self._gitlab_emails_cache:
            gitlab_user_id = self._gitlab_emails_cache[email]
            gitlab_user = self._target.find_user(gitlab_user_id)
            user = User(email=email, username=gitlab_user.username,
                        real_name=gitlab_user.name, id=gitlab_user.id)
            self._users_cache[email] = user
            return user

        bzu = self._bugzilla.getuser(email)
        # Heuristically remove "(not reading bugmail) or (not receiving
        # bugmail)"
        real_name = re.sub(r' \(not .+ing bugmail\)', '', bzu.real_name)
        user = User(email=email, real_name=real_name, username=None, id=None)
        self._users_cache[email] = user

        return user

    def _retrieve_gitlab_emails_cache(self):
        gitlab_emails_cache = {}
        try:
            with open('users_cache', 'rb') as fp:
                print('Loading users from \'users_cache\' file')
                gitlab_emails_cache = pickle.load(fp)
        except Exception as error:
            print('Downloading users')
            all_gitlab_users = self._target.get_all_users()
            print('Downloading secondary emails')
            for i, user in enumerate(all_gitlab_users):
                emails = user.emails.list()
                # Main email is accesible directly
                gitlab_emails_cache[user.email] = user.id
                for email in emails:
                    # Secondary emails need this hop
                    gitlab_emails_cache[email.email] = email.user_id

                print('[' + str(i) + '/' + str(len(all_gitlab_users)) +
                      '] users processed')

        return gitlab_emails_cache

    def _save_gitlab_emails_cache(self):
        with open('users_cache', 'wb') as fp:
            pickle.dump(self._gitlab_emails_cache, fp)
            print('Wrote users data into file \'users_cache\' for caching \
purposes')
