import argparse
import base64
import datetime
import json
import os
import re
import sys
import time

import phabricator

from . import bt
from . import template
from . import users
from . import common

ON_WINDOWS = os.name == 'nt'

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

    def import_tasks_from_phab(self, phab, start_at):
        """Imports project tasks from phabricator"""

        if self.target_project:
            projname = self.target_project.split("/")[1]
        else:
            projname = self.project

        for _id, task in phab.tasks.items():
            if start_at and _id < start_at:
                continue

            description = \
                template.render_issue_description(
                    None, task, phab.escape_markdown(
                        task["description"]), phab.users,
                    task['uri'],
                    bug_url_function=phab.task_url)

            labels = ['phabricator']
            milestone = None
            for project in task.projects.values():
                if project['fields']['milestone']:
                    if project['fields']['parent']['phid'] in phab.used_projects:
                        milestone = project['fields']["name"]
                elif project['fields']["name"] != projname:
                    labels.append(project['fields']["name"])

            labels.append(task['priority'])

            if not task["title"]:
                print("WARNING task %s doesn't have a title!" % _id)
                continue
            creation_time = datetime.datetime.fromtimestamp(
                int(task["dateCreated"])
                ).strftime('%Y-%m-%d %H:%M:%S')

            # Assign bug to actual account if exists
            phabauthor = phab.users.get(task["authorPHID"])
            if phabauthor:
                author = self.find_user_by_nick(phabauthor.username)
                if not author:
                    try:
                        author = self.create_user(phabauthor.username)
                    except:
                        pass
                author = phabauthor.username
            else:
                author = None

            phabowner = phab.users.get(task["ownerPHID"])
            if phabowner:
                assignee = self.find_user_by_nick(phabowner.username)
                if not assignee:
                    try:
                        assignee = self.create_user(phabowner.username)
                    except:
                        pass
            else:
                assignee = None

            issue = self.create_issue(_id, task["title"],
                                      description, labels,
                                      milestone,
                                      creation_time#, sudo=author
            )

            if assignee:
                issue.assignee_id = assignee.id

            print("Created %s - %s: %s" %
                  (_id, issue.get_id(), issue.attributes['title']))

            for comment in task.comments:
                sudo = None
                emoji, action, body = ('speech_balloon', 'said',
                                       comment["comments"])
                comment_author = comment["authorPHID"]
                if comment_author.startswith("PHID-APPS"):
                    author = comment_author.rsplit("-")[2]
                else:
                    author = phab.users[comment_author].display_name()
                    if phabowner:
                        sudo = self.find_user_by_nick(phab.users[comment_author].username)
                        if sudo:
                            sudo = sudo.id
                assignee = None
                gitlab_comment = template.render_comment(
                    None, emoji, author,
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

    def import_revisions_from_phab(self, phab, start_at):
        """Imports project patches from phabricator"""

        if self.target_project:
            projname = self.target_project.split("/")[1]
        else:
            projname = self.project

        for _id, revision in phab.revisions.items():
            if start_at and _id < start_at:
                continue

            description = \
                template.render_issue_description(
                    None, revision, phab.escape_markdown(
                        revision["summary"]), phab.users,
                    revision['uri'],
                    bug_url_function=phab.diff_url)

            labels = ['phabricator']
            milestone = None
            for project in revision.projects.values():
                if project['fields']['milestone']:
                    if project['fields']['parent']['phid'] in phab.used_projects:
                        milestone = project['fields']["name"]
                elif project['fields']["name"] != projname:
                    labels.append(project['fields']["name"])

            if not revision["title"]:
                print("WARNING revision %s doesn't have a title!" % _id)
                continue
            print("Creating revision %s: %s" % (revision['id'], revision['title']))

            # Assign bug to actual account if exists
            phabauthor = phab.users.get(revision["authorPHID"])
            if phabauthor:
                author = self.find_user_by_nick(phabauthor.username)
                if not author:
                    try:
                        author = self.create_user(phabauthor.username)
                    except:
                        pass
                author = phabauthor.username
            else:
                author = None

            assignee = None
            phabowners = revision["reviewers"]
            if phabowners:
                phabowner = phab.users.get(list(phabowners.values())[0])
                if phabowner:
                    assignee = self.find_user_by_nick(phabowner.username)
                    if not assignee:
                        try:
                            assignee = self.create_user(phabowner.username)
                        except:
                            pass
            if not assignee:
                assignee = None

            if revision.diff != "":
                desc = description + "\n```\n" + revision.diff + "\n```"
            else:
                desc = description
            mergerequest = self.create_mergerequest(_id, revision["title"],
                                      desc, labels,
                                      milestone#, sudo=author
            )

            if assignee:
                mergerequest.assignee_id = assignee.id

            print("Created %s - %s: %s" %
                  (_id, mergerequest.get_id(), mergerequest.attributes['title']))

            state_event = 'reopen'
            if revision.merged:
                # mergerequest.merge()
                if revision['commits']:
                    commits = phab.phabricator.phid.query(phids=revision['commits'])
                    commit = list(commits.values())[0]
                    info = commit['fullName']
                    for callsign in phab.callsigns:
                        msg = info.replace('r' + callsign, '', 1)
                        if msg != info:
                            mergerequest.notes.create({
                                'body': msg,
                            })
                state_event = "close"
            elif revision.abandoned:
                state_event = "close"
            mergerequest.state_event = state_event

            mergerequest.save(state_event=state_event)


class Task:
    def __init__(self, entry, all_projects, all_tasks):
        self.entry = entry
        self.projects = {}
        for phid in entry["projectPHIDs"]:
            self.projects[phid] = all_projects[phid]
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

    @property
    def creator(self):
        return self.entry["authorPHID"]

    def __getitem__(self, key):
        return self.entry[key]

class Revision:
    def __init__(self, entry, all_projects, all_revisions, diff):
        self.entry = entry
        self.projects = {}
        for phid in entry["auxiliary"]['phabricator:projects']:
            self.projects[phid] = all_projects[phid]
        self.depends_on = []
        for phid in entry["auxiliary"]['phabricator:depends-on']:
            if phid in all_revisions:
                self.depends_on.append(all_revisions[phid]["id"])

        self.diff = diff

    @property
    def assigned_to(self):
        for person in self.entry["reviewers"]:
            if not person.startswith("PHID-PROJ"):
                return person
        for person in self.entry["ccs"]:
            if not person.startswith("PHID-PROJ"):
                return person
        return None

    @property
    def id(self):
        return self.entry["id"]

    @property
    def merged(self):
        return self.entry["statusName"] == "Closed"

    @property
    def abandoned(self):
        return self.entry["statusName"] == "Abandoned"

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
        self.phabricator_uri = "https://phab.enlightenment.org/"
        self.projects = options.projects
        self.callsigns = options.callsigns
        self.start_at = options.start_at
        if not self.start_at:
            self.start_at = 1
        self.rev_start_at = options.rev_start_at
        if not self.rev_start_at:
            self.rev_start_at = 1

        self.users = {}
        self.gitlab = gitlab
        self.ensure_project_phids()
        self.retrieve_all_tasks()
        self.retrieve_all_revisions()

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
            r'\b#?([TD][0-9]+)', '[\\1](%s/\\1)' % ("https://phab.enlightenment.org"),
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

    def diff_url(self, garbage, task_id):
        return os.path.join(self.phabricator_uri, "D" + task_id)

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
        all_tasks = {}
        for phid in self.project_phids:
            phidlist = []
            phidlist.append(phid)
            print("fetching tasks for %s (%s)" % (self.all_projects[phid]['fields']['slug'], phidlist))
            cur_tasks = self.phabricator.maniphest.query(limit=9999999999, order='created', projectPHIDs=phidlist)
            all_tasks = {**all_tasks, **cur_tasks}
        for task in sorted(all_tasks.items(), key=lambda t: int(t[1]['id'])):
            print("Evaluating task %s: %s" % (task[1]['id'], task[1]['title']))
            creation_time = datetime.datetime.fromtimestamp(
                int(task[1]["dateCreated"])
                ).strftime('%Y-%m-%d %H:%M:%S')

            if self.gitlab.find_issue(task[1]["title"], creation_time):
                print("Task already exists: %s" % task[1]["title"])
                continue
            skip = False
            for projphid in task[1]['projectPHIDs']:
                if not projphid in self.all_projects:
                    projphidlist = []
                    projphidlist.append(projphid)
                    projects = self.phabricator.project.search(limit=100, constraints=({'phids': projphidlist}))
                    self.all_projects[projphid] = projects.data[0]
                    if projects.data[0]['fields']['name'] == 'Spam':
                        skip = True
                        break
                    print("Adding additional project: %s" % (projects.data[0]['fields']['name']))
            if skip:
                continue
            task = task[1]
            id = int(task["id"])
            if self.start_at and id >= self.start_at:
                ids.append(id)
            self.tasks[id] = Task(task, self.all_projects, all_tasks)
            users.add(task["authorPHID"])
            users.update(task["ccPHIDs"])
            users.add(task["ownerPHID"])


        self.retrieve_all_users(users)
        self.retrieve_all_comments(ids, users)

    def retrieve_all_revisions(self):

        users = set()
        self.revisions = {}
        revs = {}
        all_revisions = self.phabricator.differential.query(limit=9999999999, order='created', paths=list(zip(self.callsigns, [""])))
        for rev in all_revisions:
            revs[rev['id']] = rev
        for rev in sorted(all_revisions, key=lambda t: int(t['id'])):
            id = int(rev["id"])
            if self.rev_start_at and id < self.rev_start_at:
                continue
            print("Evaluating revision %s: %s" % (rev['id'], rev['title']), end='')
            creation_time = datetime.datetime.fromtimestamp(
                int(rev["dateCreated"])
                ).strftime('%Y-%m-%d %H:%M:%S')

            if self.gitlab.find_patch(rev["title"], creation_time):
                print(" || Rev already exists--skipping")
                continue

            for projphid in rev["auxiliary"]['phabricator:projects']:
                if not projphid in self.all_projects:
                    projphidlist = []
                    projphidlist.append(projphid)
                    projects = self.phabricator.project.search(limit=100, constraints=({'phids': projphidlist}))
                    print("Adding additional project: %s" % (projects.data[0]['fields']['name']))
                    self.all_projects[projphid] = projects.data[0]

            diffid = int(rev['diffs'][0])
            diff = self.phabricator.differential.getrawdiff(diffID=str(diffid))
            self.revisions[id] = Revision(rev, self.all_projects, revs, diff.response)
            users.add(rev["authorPHID"])
            users.update(rev["ccs"])
            users.update(rev["reviewers"])
            print(" || Rev doesn't exist--creating")

        self.retrieve_all_users(users)

    def ensure_project_phids(self):
        if len(self.projects) == 1:
          projects = self.phabricator.project.search(limit=100, constraints=({'isMilestone': False, 'name': self.projects[0]}))
        else:
          projects = self.phabricator.project.search(limit=100, constraints=({'isMilestone': False}))
        self.all_projects = {}
        self.project_phids = []
        # add base project phids
        for project in projects.data:
            if project['fields']["color"]['key'] != "disabled" and \
                 project['phid'] not in self.project_phids and \
                 (project['fields']['slug'] in self.projects or project['fields']['name'] in self.projects):
              print("Adding %s" % (project['fields']['slug']))
              self.project_phids.append(project['phid'])
              self.all_projects[project['phid']] = project
        try:
            subprojects = self.phabricator.project.search(limit=100, constraints=({'isMilestone': False, 'ancestors': self.project_phids}))
            for subproject in subprojects.data:
               if subproject['fields']["color"]['key'] != "disabled" and subproject['phid'] not in self.project_phids:
                  print("Adding %s" % (subproject['fields']['slug']))
                  self.project_phids.append(subproject['phid'])
                  self.all_projects[subproject['phid']] = subproject
        except:
            pass

        self.used_projects = self.all_projects

        # print("Evaluating subproject list %s" % (subprojects.data))
        # for project in self.all_projects:
            # print("SLUG Evaluating %s" % (project["fields"]["slug"]))
            # if project["fields"]["slug"] in self.projects:
                # self.project_phids.append(project["phid"])
            # if project["fields"]["parent"]:
                # print("PARENT Evaluating %s" % (project["fields"]["parent"]["name"]))
                # for project["fields"]["parent"]["name"] in self.projects:
                    # self.project_phids.append(project["phid"])

        print("FOUND %s" % (self.project_phids))

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
    parser.add_argument('--callsign', help="phab project callsign", dest="callsigns",
                        required=True, action="append")
    parser.add_argument('--target-project', metavar="USERNAME/PROJECT",
                        help="project name for gitlab, like \
                              'username/project'. If not provided, \
                              $user_namespace/$bugzilla_product will be used")
    parser.add_argument('--start-at',
                        help="The ID of the first task to import",
                        type=int)
    parser.add_argument('--rev-start-at',
                        help="The ID of the first revision to import",
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

    target = PhabGitLab("https://gitlab-prototype.s-opensource.org/",
                        "https://git.enlightenment.org/",
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
        target.import_tasks_from_phab(phab, args.start_at)

    if phab.revisions:
        target.import_revisions_from_phab(phab, args.rev_start_at)


if __name__ == '__main__':
    main()
