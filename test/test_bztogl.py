import collections

from bztogl import bztogl, users


def test_create_issue():
    bz = Bugzilla()
    gl = Gitlab()
    milestone_cache = collections.defaultdict(lambda: None)
    bug = Bug(12345, bz)

    # XXX: Create a mock usercache, maybe mock target too ... ?
    issue = bztogl.create_issue(target, None, milestone_cache, bug)
    assert issue is not None


def test_update_content():
    bz = Bugzilla()
    gl = Gitlab()
    user_cache = collections.defaultdict(lambda: None)
    user_cache['test@example.com'] = User()

    bug = Bug(12345, bz)
    bug.assigned_to = 'test@example.com'
    bug_dep = Bug(54321)
    bug.depends_on = [
        bug_dep.bug_id
    ]

    issue = Issue()
    issue_dep = Issue()
    issues = {
        12345: issue,
        54321: issue_dep,
    }

    bztogl.update_content(bz, gl, user_cache, issues, issue, bug)
    assert 'first comment' in issue.description
    assert '#{}'.format(issue_dep.iid) in issue.description


def test_finalise_issue():
    bug = Bug(12345)
    issue = Issue()
    user_cache = collections.defaultdict(lambda: None)

    bztogl.finalise_issue(bug, issue, user_cache)


def test_close_bug():
    bz = Bugzilla()
    bug = Bug(12345, bz)
    issue = Issue()

    bztogl.close_bug(bug, issue)


class Bugzilla:

    def __init__(self):
        self._proxy = object()

    def build_update(self, *args, **kwargs):
        return None

    def update_bugs(self, *args, **kwargs):
        pass


class Bug:

    next_id = 1

    def __init__(self, id, bugzilla=None):
        self.id = Bug.next_id
        self.bug_id = id
        self.bugzilla = bugzilla
        self.summary = ''
        self.creator = 'test@example.com'
        self.creation_time = 12345
        self.assigned_to = None
        self.cc = []
        self.status = 'NEW'
        self.component = 'General'
        self.version = None
        self.target_milestone = None
        self.keywords = []
        self.depends_on = []
        self.blocks = []
        self.see_also = []
        self.attachments = []

        Bug.next_id += 1

    def getcomments(self):
        return [
            {
                'author': self.creator,
                'text': 'first comment'
            }
        ]


class Gitlab:

    def create_issue(self, *args, **kwargs):
        issue = Issue()
        issue.description = args[2]
        return issue


class Issue:

    next_iid = 1

    def __init__(self):
        self.iid = Issue.next_iid
        self.description = ''
        self.web_url = ''

        Issue.next_iid += 1

    def save(self, *args, **kwargs):
        pass


class User:

    def __init__(self):
        self.id = None

    def display_name(self):
        return 'Test User'
