import argparse
import base64
import datetime
import json
import os
import re
import sys

import phabricator

from . import bt
from . import template
from . import users
from . import common

ON_WINDOWS = os.name == 'nt'

KEYWORD_MAP = {
    "Pitivi tasks for newcomers": "4. Newcomers",
    "translations": "8. Translation",
    "titles editor": "title clips",
    "bundles": "binaries"
}


MIGR_TEMPLATE = """# GitLab Migration Automatic Message

This bug has been migrated to freedesltop.org's GitLab instance and has been closed \
from further activity.

You can subscribe and participate further through the new bug through this \
link to our GitLab instance: {}.
"""


class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

    force_disable = False

    @classmethod
    def disable(cls):
        cls.HEADER = ''
        cls.OKBLUE = ''
        cls.OKGREEN = ''
        cls.WARNING = ''
        cls.FAIL = ''
        cls.ENDC = ''

    @classmethod
    def enable(cls):
        if cls.force_disable:
            return

        cls.HEADER = '\033[95m'
        cls.OKBLUE = '\033[94m'
        cls.OKGREEN = '\033[92m'
        cls.WARNING = '\033[93m'
        cls.FAIL = '\033[91m'
        cls.ENDC = '\033[0m'


class PhabGitLab(common.GitLab):
    """GitLab pabricator importer"""

    def __init__(self, glurl, giturl, token, product, target_project=None,
                 automate=False, close_tasks=False):
        super().__init__(glurl, giturl, token, product, target_project,
                         automate)
        self.close_tasks = close_tasks

    def import_from_phab(self, phab, start_at):
        """Imports project tasks from phabricator"""

        if self.target_project:
            projname = self.target_project.split("/")[1]
        else:
            projname = self.project

        for _id, task in sorted(phab.tasks.items()):
            if start_at and _id < start_at:
                continue

            description = \
                template.render_issue_description(
                    None, task, phab.escape_markdown(
                        task["description"]), phab.users,
                    importing_address=os.path.join(phab.phabricator_uri, "T"),
                    bug_url_function=phab.task_url)

            labels = ['phabricator']
            for project in task.projects.values():
                if project["name"] != projname:
                    # FIXME - Find a way to generically strip what should be
                    # stripped.
                    label = KEYWORD_MAP.get(project["name"], project["name"])
                    for to_strip in ["pitivi_", "pitivi", "ptv_", "ptv",
                                     "Pitivi", " "]:
                        label = label.strip(to_strip)
                    labels.append(label)

            if not task["title"]:
                print("WARNING task %s doesn't have a title!" % _id)
                continue

            # Assign bug to actual account if exists
            phabauthor = phab.users.get(task["authorPHID"])
            if phabauthor:
                author = self.find_user_by_nick(phabauthor.username)
                if author:
                    author = author.id
            else:
                author = None

            phabowner = phab.users.get(task["ownerPHID"])
            if phabowner:
                assignee = self.find_user_by_nick(phabowner.username)
            else:
                assignee = None

            issue = self.create_issue(_id, task["title"],
                                      description, labels,
                                      None,
                                      datetime.datetime.fromtimestamp(
                int(task["dateCreated"])
            ).strftime('%Y-%m-%d %H:%M:%S')#, sudo=author
            )

            if assignee:
                issue.assignee_id = assignee.id

            print("Created %s - %s: %s" %
                  (_id, issue.get_id(), issue.attributes['title']))

            for comment in task.comments:
                emoji, action, body = ('speech_balloon', 'said',
                                       comment["comments"])
                author = phab.users[comment["authorPHID"]]
                if phabowner:
                    sudo = self.find_user_by_nick(author.username)
                    if sudo:
                        sudo = sudo.id
                else:
                    sudo = None
                assignee = None
                gitlab_comment = template.render_comment(
                    None, emoji, author.display_name(),
                    action, phab.escape_markdown(body),
                    "", bug_url_function=phab.task_url)

                issue.notes.create({
                    'body': gitlab_comment,
                    'created_at': datetime.datetime.fromtimestamp(
                        int(task["dateCreated"])
                    ).strftime('%Y-%m-%d %H:%M:%S')
                })#, sudo=sudo)

            state_event = 'reopen'
            if task.resolved:
                state_event = "close"
            issue.state_event = state_event

            issue.save(state_event=state_event)

            if self.close_tasks:
                phab.phabricator.maniphest.edit(
                    objectIdentifier=str(_id),
                    transactions=[{
                        "type": "comment",
                        "value": MIGR_TEMPLATE.format(issue.web_url)}])
                phab.phabricator.maniphest.update(id=_id, status='resolved')


class Task:
    def __init__(self, entry, all_projects, all_tasks):
        self.entry = entry
        self.projects = {}
        for phid in entry["projectPHIDs"]:
            self.projects[phid] = all_projects.data[phid]
        self.depends_on = []
        for phid in self.entry["dependsOnTaskPHIDs"]:
            if phid in all_tasks:
                self.depends_on.append(all_tasks[phid]["id"])

    @property
    def assigned_to(self):
        if self.entry["ownerPHID"]:
            return self.entry["ownerPHID"]

        return self.entry["authorPHID"]

    @property
    def id(self):
        return self.entry["id"]

    @property
    def resolved(self):
        return self.entry["isClosed"]

    @property
    def creator(self):
        return self.entry["authorPHID"]

    @property
    def comments(self):
        return self.entry.get("comments", [])

    @property
    def blocks(self):
        # FIXME!
        return []

    @property
    def see_also(self):
        return []

    @property
    def version(self):
        return None

    def __getitem__(self, key):
        return self.entry[key]


class Phab:

    FILES_REGEX = re.compile(r'\{F[0-9\(\)]+\}', re.MULTILINE)

    def __init__(self, options, gitlab):
        self._phabricator = None
        self.arcrc = None
        self.phabricator_uri = "https://phabricator.freedesktop.org/"
        self.projects = options.projects

        self.users = {}
        self.ensure_project_phids()
        self.retrieve_all_tasks()
        self.gitlab = gitlab

    def migrate_attachment(self, fileid):
        finfo = self.phabricator.file.info(id=int(fileid))
        attfile = self.phabricator.file.download(phid=finfo["phid"])
        ret = self.gitlab.upload_file(
            finfo["name"], base64.b64decode(attfile.response))

        return ret['markdown']

    def escape_markdown(self, markdown):
        markdown = bt.quote_stack_traces(markdown)

        # Revert possibly double quoted backtraces
        markdown = re.sub(re.compile(
            r'```\n```\n', re.MULTILINE), '\n```\n', markdown)

        for filelink in re.findall(Phab.FILES_REGEX, markdown):
            fileid = filelink.strip("{F").strip("}")
            try:
                markdown = markdown.replace(
                        filelink, self.migrate_attachment(fileid))
            except phabricator.APIError:
                print("WARNING: Could not migrate file: %s" % filelink)
                pass

        # Prevent spurious links to other GitLab issues
        markdown = re.sub(r'([Cc]omment) #([0-9]+)', '\\1 \\2', markdown)

        # Prevent unintended linking to issues.
        markdown = re.sub(r'(\W)#([0-9]+)', '\\1# \\2', markdown)

        # Link Tasks and Differentials
        markdown = re.sub(
            r'\b#?([TD][0-9]+)', '[\\1](%s/\\1)' % ("https://phabricator.freedesktop.org"),
            markdown)

        # Avoid losing new lines.
        markdown = re.sub(r'([^\n])\n', '\\1  \n', markdown)

        # Quote XML-like tags which would otherwise be stripped by GitLab
        tags_outside_quotes = re.compile(r"""
            (
                ^[^`]*                    # An initial string with no backticks
                (?:                       # Then zero or more of...
                    (?:
                        \n```.*?\n```     # A matched pair of triple backticks
                    |
                        `[^`]+`           # Or a matched pair of backticks
                    )
                    [^`]*?                # Followed by a str without backticks
                )*?                       # These are skipped before finding
            )
            (\<\/?[a-zA-Z0-9_="' -]*?\>)  # ...an XML-like tag
            """, re.VERBOSE)

        nsubs = 1
        while nsubs > 0:
            # Matches may overlap, so we have to keep substituting until
            # none left
            markdown, nsubs = tags_outside_quotes.subn('\\1`\\2`', markdown)

        return markdown

    def task_url(self, garbage, task_id):
        return os.path.join(self.phabricator_uri, "T" + task_id)

    def retrieve_all_comments(self, ids, users):
        all_transactions = self.phabricator.maniphest.gettasktransactions(
            ids=ids)
        for tid, transactions in all_transactions.items():
            for transaction in sorted(transactions,
                                      key=lambda x: x['dateCreated']):
                if transaction["transactionType"] == "core:customfield":
                    user = self.users[transaction["authorPHID"]]
                    transaction["comments"] = "%s set git URI to %s" % (
                        user.display_name(), transaction["newValue"]
                    )

                if transaction["comments"]:
                    self.tasks[int(tid)].entry.setdefault(
                        "comments", []).append(transaction)

    def retrieve_all_users(self, usersphids):
        all_users = self.phabricator.user.query(limit=99999999)
        for user in all_users:
            user = users.User(email=user["phid"],
                              real_name=user["realName"],
                              username=user["userName"], id=None)
            self.users[user.email] = user

    def retrieve_all_tasks(self):
        ids = []

        self.tasks = {}
        users = set()
        all_tasks = self.phabricator.maniphest.query(limit=9999999999, status="status-open", projectPHIDs=self.project_phids)
        for task in all_tasks.items():
            for phid in task[1]['projectPHIDs']:
                if phid in self.project_phids:
                    task = task[1]
                    id = int(task["id"])
                    ids.append(id)
                    self.tasks[id] = Task(task, self.all_projects, all_tasks)
                    users.add(task["authorPHID"])
                    users.update(task["ccPHIDs"])
                    users.add(task["ownerPHID"])

                    break

        self.retrieve_all_users(users)
        self.retrieve_all_comments(ids, users)

    def ensure_project_phids(self):
        self.all_projects = self.phabricator.project.query(limit=9999999999, status="status-open")

        self.project_phids = []
        project_map = {}
        for (phid, data) in self.all_projects.data.items():
            project_map[data["name"].lower()] = phid
            for s in data["slugs"]:
                project_map[s.lower()] = phid

        try:
            for p in self.projects:
                if p not in project_map:
                    print("%sProject `%s` doesn't seem to exist%s" %
                          (Colors.FAIL, p, Colors.ENDC))
                    raise
                self.project_phids.append(project_map[p])
        except Exception:
            self.die("Failed to look up projects in Phabricator")

    def setup_login_certificate(self):
        token = input("""LOGIN TO PHABRICATOR
Open this page in your browser and login to Phabricator if necessary:

%s/conduit/login/

Then paste the API Token on that page below.

Paste API Token from that page and press <enter>: """ % self.phabricator_uri)
        path = os.path.join(os.environ['AppData'] if ON_WINDOWS
                            else os.path.expanduser('~'), '.arcrc')

        host = self.phabricator_uri + "/api/"
        host_token = {"token": token}
        try:
            with open(path) as f:
                arcrc = json.load(f)

                if arcrc.get("hosts"):
                    arcrc["hosts"][host] = host_token
                else:
                    arcrc = {
                        "hosts": {host: host_token}}

        except (FileNotFoundError, ValueError):
            arcrc = {"hosts": {host: host_token}}

        with open(path, "w") as f:
            print("Writing %s" % path)
            json.dump(arcrc, f, indent=2)

        return True

    def die(self, message):
        print(message, file=sys.stderr)
        sys.exit(1)

    @property
    def phabricator(self):
        if self._phabricator:
            return self._phabricator

        if self.arcrc:
            try:
                with open(self.arcrc) as f:
                    phabricator.ARCRC.update(json.load(f))
            except FileNotFoundError:
                self.die("Failed to load a given arcrc file, %s" % self.arcrc)

        needs_credential = False
        try:
            host = self.phabricator_uri + "/api/"
            self._phabricator = phabricator.Phabricator(timeout=120, host=host)

            if not self.phabricator.token and not self.phabricator.certificate:
                needs_credential = True

            # FIXME, workaround
            # https://github.com/disqus/python-phabricator/issues/37
            self._phabricator.differential.creatediff.api.interface[
                "differential"]["creatediff"]["required"]["changes"] = dict
        except phabricator.ConfigurationError:
            needs_credential = True

        if needs_credential:
            if self.setup_login_certificate():
                self.die("Try again now that the login certificate has been"
                         " added")
            else:
                self.die("Please setup login certificate before trying again")

        return self._phabricator


def options():
    parser = argparse.ArgumentParser(
        description="Phabricator migration helper for bugzilla.gnome.org "
                    "products")
    parser = argparse.ArgumentParser(
        description="Bugzilla migration helper for bugzilla.gnome.org "
                    "products")
    parser.add_argument('--production', action='store_true',
                        help="target production (gitlab.gnome.org) instead \
                              of testing (gitlab-test.gnome.org)")
    parser.add_argument('--recreate', action='store_true',
                        help="remove the project at GitLab if it exists and \
                              import the project from the original repository")
    parser.add_argument('--only-import', action='store_true',
                        help="only import the module, no migration of issues")
    parser.add_argument('--automate', action='store_true',
                        help="don't wait on user input and answer \'Y\' (yes) \
                              to any question")
    parser.add_argument('--token', help="gitlab token API", required=True)
    parser.add_argument(
        '--close-tasks', help="Close phabricator tasks", action='store_true')
    parser.add_argument('--project', help="phab project name", dest="projects",
                        required=True, action="append")
    parser.add_argument('--target-project', metavar="USERNAME/PROJECT",
                        help="project name for gitlab, like \
                              'username/project'. If not provided, \
                              $user_namespace/$bugzilla_product will be used")
    parser.add_argument('--start-at',
                        help="The ID of the first task to import",
                        type=int)
    return parser.parse_args()


def check_if_target_project_exists(target):
    try:
        target.get_project()
    except Exception as e:
        print("ERROR: Could not access the project `{}` - are you sure \
               it exists?".format(target.target_project))
        print("You can use the --target-project=username/project option if \
               the project name\n\is different from the Bugzilla \
               product name.")
        exit(1)


def main():
    args = options()

    target = PhabGitLab("https://gitlab.freedesktop.org/",
                        "https://cgit.freedesktop.org/",
                        args.token, args.projects[0],
                        args.target_project,
                        args.automate, args.close_tasks)

    target.connect()
    if not args.recreate and args.target_project is not None:
        check_if_target_project_exists(target)

    if not args.target_project and args.recreate:
        target.import_project()

    phab = Phab(args, target)

    if phab.tasks:
        target.import_from_phab(phab, args.start_at)


if __name__ == '__main__':
    main()
