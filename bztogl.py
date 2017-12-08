#!/usr/bin/env python3

#    Copyright 2017 Alberto Ruiz <aruiz@gnome.org>
#    Copyright 2017 Philip Chimento <philip.chimento@gmail.com>

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import sys
import argparse
import urllib.parse
import time
import json

import bugzilla
import gitlab

import bt
import users

# Note, the \n\ is to prevent trailing whitespace from being stripped by
# people's editors. It is there intentionally.

DESC_TEMPLATE = """## Submitted by {submitter}  \n\
{assigned_to}
**[Link to original bug (#{id})]\
(https://bugzilla.gnome.org/show_bug.cgi?id={id})**  \n\
## Description
{body}

{dependencies}
"""

DEPENDENCIES_TEMPLATE = """{depends_on}
{blocks}
"""

COMMENT_TEMPLATE = """:{emoji}: **{author}** {action}:
{body}  \n\
{attachment}
"""

ATTACHMENT_TEMPLATE = """  \n\
{obsolete}**{kind} {atid}**{obsolete}, "{summary}":  \n\
{markdown}
"""

MIGR_TEMPLATE = """-- GitLab Migration Automatic Message --

This bug has been migrated to GNOME's GitLab instance and has been closed \
from further activity.

You can subscribe and participate further through the new bug through this \
link to our GitLab instance: {}.
"""

NEEDINFO_LABEL = "2. Needs Information"
KEYWORD_MAP = {
    "accessibility": "8. Accessibility",
    "newcomers": "4. Newcomers",
    "security": "1. Security"
}

GIT_ORIGIN_PREFIX = 'https://git.gnome.org/browse/'


class GitLab:
    GITLABURL = "https://gitlab-test.gnome.org/"

    def __init__(self, token, product, target_project=None, automate=False):
        self.gl = None
        self.token = token
        self.product = product
        self.target_project = target_project
        self.automate = automate

    def connect(self):
        print("Connecting to %s" % self.GITLABURL)
        self.gl = gitlab.Gitlab(self.GITLABURL, self.token)
        self.gl.auth()
        # If not target project was given, set the project under the user
        # namespace
        if self.target_project is None:
            self.target_project = self.gl.user.username + '/' + self.product
            print("Using target project '{}' since --target-project was not provided".format(self.target_project))

    def get_project(self):
        return self.gl.projects.get(self.target_project)

    def create_issue(self, id, summary, description, labels, creation_time):
        return self.get_project().issues.create({
            'title': summary,
            'description': description,
            'labels': ','.join(labels),
            'created_at': creation_time
        })

    def find_user(self, email):
        possible_users = self.gl.users.search(email)
        if len(possible_users) == 1:
            return possible_users[0]
        return None

    def remove_project(self, project):
        try:
            project.delete()
        except Exception as e:
            raise Exception("Could not remove project: {}".format(project))

    def get_import_status(self, project):
        url = (self.GITLABURL +
               "api/v4/projects/{}".format(project.id))
        self.gl.session.headers = {"PRIVATE-TOKEN": self.token}
        ret = self.gl.session.get(url)
        if ret.status_code != 200:
            raise Exception("Could not get import status: {}".format(ret.text))

        ret_json = json.loads(ret.text)
        return ret_json.get('import_status')

    def import_project(self):
        import_url = GIT_ORIGIN_PREFIX + self.product
        print('Importing project from ' + import_url +
              ' to ' + self.target_project)

        try:
            project = self.get_project()
        except Exception as e:
            project = None

        if project is not None:
            print('##############################################')
            print('#                  WARNING                   #')
            print('##############################################')
            print('THIS WILL DELETE YOUR PROJECT IN GITLAB.')
            print('ARE YOU SURE YOU WANT TO CONTINUE? Y/N')

            if not self.automate:
                answer = input('')
            else:
                answer = 'Y'
                print('Y (automated)')

            if answer == 'Y':
                self.remove_project(project)
            else:
                print('Bugs will be added to the existing project')
                return

        project = self.gl.projects.create({'name': self.product,
                                           'import_url': import_url,
                                           'visibility_level': 20})

        import_status = self.get_import_status(project)
        while(import_status == 'none'):
            print('Importing project, status: ' + import_status)
            time.sleep(1)
            import_status = self.get_import_status(project)


def bugzilla_url(bugid):
    return 'https://bugzilla.gnome.org/show_bug.cgi?id={}'.format(bugid)


def autolink_markdown(text):
    text = re.sub(r'([Bb]ug) ([0-9]+)',
                  '[\\1 \\2]({})'.format(bugzilla_url('\\2')), text)
    # Prevent spurious links to other GitLab issues
    text = re.sub(r'([Cc]omment) #([0-9]+)', '\\1 \\2', text)
    # Quote stack traces as preformatted text
    text = bt.quote_stack_traces(text)
    return text


def body_to_markdown_quote(body):
    if not body:
        return '\n'
    return ">>>\n{}\n>>>\n".format(autolink_markdown(body))


def initial_comment_to_issue_description(bug, text, user_cache):
    if not text:
        text = ""

    # Assignment of $PROJECT@gnome.bugs effectively means unassigned
    assigned_to = ""
    assignee = user_cache[bug.assigned_to]
    if assignee is not None:
        assigned_to = "**Assigned to {}**  \n".format(assignee.display_name())

    deps = ""
    if bug.depends_on:
        deps += "### Depends on\n"
        for bugid in bug.depends_on:
            deps += "  * [Bug {}]({})\n".format(bugid, bugzilla_url(bugid))

    blocks = ""
    if bug.blocks:
        blocks += "### Blocking\n"
        for bugid in bug.blocks:
            blocks += "  * [Bug {}]({})\n".format(bugid, bugzilla_url(bugid))

    dependencies = DEPENDENCIES_TEMPLATE.format(depends_on=deps, blocks=blocks)
    return DESC_TEMPLATE.format(
        submitter=user_cache[bug.creator].display_name(),
        assigned_to=assigned_to, id=bug.id, body=body_to_markdown_quote(text),
        dependencies=dependencies)


def bugzilla_migration_closing_comment(gl_issue):
    return MIGR_TEMPLATE.format(gl_issue.web_url)


def processbug(bgo, target, user_cache, bzbug):
    print("Processing bug #%d: %s" % (bzbug.id, bzbug.summary))
    # bzbug.cc
    # bzbug.id
    # bzbug.summary
    # bzbug.creator
    # bzbug.creationtime
    # bzbug.target_milestone
    # bzbug.blocks
    # bzbug.depends_on
    # bzbug.assigned_to

    def get_attachments_metadata(self):
        # pylint: disable=protected-access
        proxy = self.bugzilla._proxy
        # pylint: enable=protected-access

        if "attachments" in self.__dict__:
            attachments = self.attachments
        else:
            rawret = proxy.Bug.attachments(
                {"ids": [self.bug_id], "exclude_fields": ["data"]})
            attachments = rawret["bugs"][str(self.bug_id)]

        index = {}
        for at in attachments:
            atid = at.pop('id')
            index[atid] = at
        return index

    def gitlab_upload_file(target, filename, f):
        url = (target.GITLABURL +
               "api/v3/projects/{}/uploads".format(target.get_project().id))
        target.gl.session.headers = {"PRIVATE-TOKEN": target.token}
        ret = target.gl.session.post(url, files={
            'file': (urllib.parse.quote(filename), f)
        })
        if ret.status_code != 201:
            raise Exception("Could not upload file: {}".format(ret.text))
        return ret.json()

    def migrate_attachment(comment, metadata):
        atid = comment['attachment_id']

        filename = metadata[atid]['file_name']
        print("    Attachment {} found, migrating".format(filename))
        attfile = bgo.openattachment(atid)
        ret = gitlab_upload_file(target, filename, attfile)

        return ATTACHMENT_TEMPLATE.format(
            atid=atid,
            kind='Patch' if metadata[atid]['is_patch'] else 'Attachment',
            obsolete='~~' if metadata[atid]['is_obsolete'] else '',
            summary=metadata[atid]['summary'],
            markdown=ret['markdown'])

    def remove_first_lines(text, numlines):
        return '\n'.join(text.split('\n')[numlines:])

    def convert_review_comments_to_markdown(text):
        paragraphs = text.split('\n\n')
        converted_paragraphs = []
        for paragraph in paragraphs:
            # Quick check if this is a diff block
            if paragraph[:2] not in ('::', '@@'):
                converted_paragraphs.append(paragraph)
                continue

            # Slow check if this is a diff block
            lines = paragraph.split('\n')
            if not all([line[0] in ':@+- ' for line in lines]):
                converted_paragraphs.append(paragraph)
                continue

            converted_paragraphs.append('```diff\n{}\n```'.format(paragraph))

        return '\n\n'.join(converted_paragraphs)

    def analyze_bugzilla_comment(comment, attachment_metadata):
        body = comment['text']

        if re.match(r'Created attachment ([0-9]+)\n', body):
            # Remove two lines of attachment description and blank line
            body = remove_first_lines(body, 3)
            if attachment_metadata[comment['attachment_id']]['is_patch']:
                return 'hammer_and_wrench', 'submitted a patch', body
            return 'paperclip', 'uploaded an attachment', body

        match = re.match(r'Review of attachment ([0-9]+):\n', body)
        if match:
            body = remove_first_lines(body, 2)
            body = convert_review_comments_to_markdown(body)
            return 'mag', 'reviewed patch {}'.format(match.group(1)), body

        match = re.match(r'Comment on attachment ([0-9]+)\n', body)
        if match:
            body = remove_first_lines(body, 3)

            # git-bz will push a single commit as a comment on the patch
            if re.match(r'Attachment [0-9]+ pushed as [0-9a-f]+ -', body):
                return 'arrow_heading_up', 'committed a patch', body

            kind = 'attachment'
            if attachment_metadata[comment['attachment_id']]['is_patch']:
                kind = 'patch'
            action = 'commented on {} {}'.format(kind, match.group(1))
            return 'speech_balloon', action, body

        # git-bz pushing multiple commits is just a plain comment. Add
        # formatting so that the lines don't run together
        if re.match(r'Attachment [0-9]+ pushed as [0-9a-f]+ -', body):
            body = body.replace('\n', '  \n')
            return 'arrow_heading_up', 'committed some patches', body

        if re.match(r'\*\*\* Bug [0-9]+ has been marked as a duplicate of '
                    'this bug. \*\*\*', body):
            return 'link', 'closed a related bug', body

        return 'speech_balloon', 'said', body

    attachment_metadata = get_attachments_metadata(bzbug)
    comments = bzbug.getcomments()

    firstcomment = None if len(comments) < 1 else comments[0]
    desctext = None
    if firstcomment['author'] == bzbug.creator:
        desctext = firstcomment['text']
        if 'attachment_id' in firstcomment:
            desctext += '\n' + migrate_attachment(firstcomment,
                                                  attachment_metadata)
        comments = comments[1:]

    summary = "[BZ#{}] {}".format(bzbug.id, bzbug.summary)
    description = initial_comment_to_issue_description(bzbug, desctext,
                                                       user_cache)
    labels = ['bugzilla']
    if bzbug.status == 'NEEDINFO':
        labels += [NEEDINFO_LABEL]

    labels.append('5. {}'.format(bzbug.component.title()))

    for kw in bzbug.keywords:
        if kw in KEYWORD_MAP:
            labels += [KEYWORD_MAP[kw]]

    issue = target.create_issue(bzbug.id, summary, description, labels,
                                str(bzbug.creation_time))

    # Assign bug to actual account if exists
    assignee = user_cache[bzbug.assigned_to]
    if assignee and assignee.id is not None:
        issue.assignee_id = assignee.id

    print("Migrating comments: ")
    c = 0
    for comment in comments:
        c = c + 1
        print("  [{}/{}]".format(c, len(comments)))
        comment_attachment = ""
        # Only migrate attachment if this is the comment where it was created
        if 'attachment_id' in comment and \
                comment['text'].startswith('Created attachment'):
            comment_attachment = migrate_attachment(comment,
                                                    attachment_metadata)

        emoji, action, body = analyze_bugzilla_comment(comment,
                                                       attachment_metadata)
        author = user_cache[comment['author']].display_name()

        issue.notes.create({
            'body': COMMENT_TEMPLATE.format(
                emoji=emoji, author=author, action=action,
                body=body_to_markdown_quote(body),
                attachment=comment_attachment),
            'created_at': str(comment['creation_time'])
        })

    # Do last, so that previous actions don't all send an email
    for cc_email in bzbug.cc:
        subscriber = user_cache[cc_email]
        if subscriber and subscriber.id is not None:
            try:
                issue.subscribe(sudo=subscriber.username)
            except gitlab.GitlabSubscribeError as e:
                if e.response_code in (201, 304):
                    # 201 == workaround for python-gitlab bug
                    # https://github.com/python-gitlab/python-gitlab/pull/382
                    # 304 == already subscribed
                    continue
                if e.response_code == 403:
                    print("WARNING: Subscribing users requires admin. "
                          "Subscribers will not be migrated.")
                    break
                raise e

    issue.save()

    print("New GitLab issue created from bugzilla bug "
          "{}: {}".format(bzbug.id, issue.web_url))

    if bzbug.bugzilla.logged_in:
        bz = bzbug.bugzilla
        print("Adding a comment in bugzilla and closing the bug there")
        # TODO: Create a resolution for this specific case? MIGRATED or FWDED?
        bz.update_bugs(bzbug.bug_id, bz.build_update(
            comment=bugzilla_migration_closing_comment(issue),
            status='RESOLVED',
            resolution='OBSOLETE'))


def options():
    parser = argparse.ArgumentParser(
        description="Bugzilla migration helper for bugzilla.gnome.org "
                    "products")
    parser.add_argument('--production', action='store_true',
                        help="target production (gitlab.gnome.org) instead of testing (gitlab-test.gnome.org)")
    parser.add_argument('--recreate', action='store_true',
                        help="remove the project at GitLab if it exists and \
                              import the project from the original repository")
    parser.add_argument('--automate', action='store_true',
                        help="don't wait on user input and answer \'Y\' (yes) \
                              to any question")
    parser.add_argument('--token', help="gitlab token API", required=True)
    parser.add_argument('--product', help="bugzilla product name",
                        required=True)
    parser.add_argument('--bz-user', help="bugzilla username")
    parser.add_argument('--bz-password', help="bugzilla password")
    parser.add_argument('--target-project', metavar="USERNAME/PROJECT",
                        help="project name for gitlab, like 'username/project'. If not provided, \
                              $user_namespace/$bugzilla_product will be used")
    return parser.parse_args()

def check_if_target_project_exists(target):
    try:
        target.get_project()
    except Exception as e:
        print("ERROR: Could not access the project `{}` - are you sure it exists?".format(target.target_project))
        print("You can use the --target-project=username/project option if the project name\n\
               is different from the Bugzilla product name.")
        exit(1)

def main():
    args = options()

    target = GitLab(args.token, args.product, args.target_project,
                    args.automate)
    if args.production:
        target.GITLABURL = "https://gitlab.gnome.org/"

    target.connect()

    check_if_target_project_exists(target)

    if not args.target_project and args.recreate:
        target.import_project()

    print("Connecting to bugzilla.gnome.org")
    if args.bz_user and args.bz_password:
        bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org", args.bz_user,
                                args.bz_password)
    else:
        print("WARNING: Bugzilla credentials were not provided, BZ bugs won't "
              "be closed and subscribers won't notice the migration")
        bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org", tokenfile=None)

    user_cache = users.UserCache(target, bgo)

    query = bgo.build_query(product=args.product)
    query["status"] = "NEW ASSIGNED REOPENED NEEDINFO UNCONFIRMED".split()
    print("Querying for open bugs for the '%s' product" % args.product)
    bzbugs = bgo.query(query)
    print("{} bugs found".format(len(bzbugs)))
    count = 0

    # TODO: Check if there were bugs from this module already filed (i.e. use a
    # tag to mark these)
    for bzbug in bzbugs:
        count += 1
        sys.stdout.write('[{}/{}] '.format(count, len(bzbugs)))
        processbug(bgo, target, user_cache, bzbug)


if __name__ == '__main__':
    main()
