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

import argparse
import itertools
import os
import re
import sys
import urllib.parse

import bugzilla
import gitlab

from . import common, milestones, template, users

NEEDINFO_LABEL = "2. Needs Information"
KEYWORD_MAP = {
    "accessibility": "8. Accessibility",
    "newcomers": "4. Newcomers",
    "security": "1. Security"
}

COMPONENT_MAP = {
    'Accessibility': '8. Accessibility',
    'Backend: Broadway': 'Broadway',
    'Backend: Quartz': 'MacOS',
    'Backend: X11': 'X11',
    'Backend: Wayland': 'Wayland',
    'Backend: Win32': 'Windows',
    'Documentation': '8. Developer Docs',
    'Input Methods': 'Input',
    'Language Bindings': 'Introspection',
    'Themes': 'Theme',
    'Widget: GtkComboBox': 'GtkComboBox',
    'Widget: GtkEntry': 'GtkEntry',
    'Widget: GtkFileChooser': '5. FileChooser',
    'Widget: GtkFontChooser': 'GtkFontChooser',
    'Widget: GtkMenu': 'GtkMenu',
    'Widget: GtkNotebook': 'GtkNotebook',
    'Widget: GtkScrolledWindow': 'GtkScrolledWindow',
    'Widget: GtkSpinButton': 'GtkSpinButton',
}


def processbug(bgo, target, user_cache, milestone_cache, bzbug):
    print("Processing bug #%d: %s" % (bzbug.id, bzbug.summary))
    # bzbug.cc
    # bzbug.id
    # bzbug.summary
    # bzbug.creator
    # bzbug.creationtime
    # bzbug.target_milestone
    # bzbug.blocks
    # bzbug.depends_on
    # bzbug.see_also
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
        url = "{}api/v3/projects/{}/uploads".format(target.gl_url,
                                                    target.get_project().id)
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

        return template.render_attachment(atid, metadata[atid], ret)

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

    def is_yorba_import(comment):
        body = comment['text']
        is_yorba = (
            'Original URL: http://redmine.yorba.org/issues/' in body and
            'Searchable id: yorba-bug-' in body
        )
        if is_yorba:
            body = re.sub(r'####\n\n#', '---\n\nComment ', body)
            body = re.sub(
                r'\n(Original [a-zA-Z ]+: [a-zA-Z0-9.:\/ ]+)', r'\n\1  ', body
            )
            body = re.sub(
                r'\n(Searchable id: [a-zA-Z0-9-]+)', r'\n\1  ', body
            )
            body = re.sub(r'\n(related to [a-zA-Z]+ - )', r'\n * \1', body)
            body = re.sub(r'\n(duplicated by [a-zA-Z]+ - )', r'\n * \1', body)
            body = re.sub(r'\n(blocked by [a-zA-Z]+ - )', r'\n * \1', body)
            comment['text'] = body

        return is_yorba

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
    is_yorba = is_yorba_import(firstcomment)
    desctext = None
    if firstcomment['author'] == bzbug.creator or is_yorba:
        desctext = firstcomment['text']
        if 'attachment_id' in firstcomment:
            desctext += '\n' + migrate_attachment(firstcomment,
                                                  attachment_metadata)
        comments = comments[1:]

    description = \
        template.render_issue_description(bzbug, desctext, user_cache)

    labels = ['bugzilla']
    if bzbug.status == 'NEEDINFO':
        labels += [NEEDINFO_LABEL]

    if bzbug.component.lower() not in ('general', '.general', target.product):
        l = COMPONENT_MAP.get(bzbug.component, None)
        if l is not None:
            labels.append(l)
        else:
            labels.append('5. {}'.format(bzbug.component.title()))

    for kw in bzbug.keywords:
        if kw in KEYWORD_MAP:
            labels += [KEYWORD_MAP[kw]]

    milestone = None
    bz_milestone = bzbug.target_milestone
    if bz_milestone and bz_milestone != '---':
        milestone = milestone_cache[bz_milestone]

    issue = target.create_issue(bzbug.id, bzbug.summary, description,
                                labels, milestone,
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

        if user_cache[comment['author']] is not None:
            author = user_cache[comment['author']].display_name()
        else:
            author = comment['author']

        gitlab_comment = template.render_comment(emoji, author, action, body,
                                                 comment_attachment)

        issue.notes.create({
            'body': gitlab_comment,
            'created_at': str(comment['creation_time'])
        })

    # Do last, so that previous actions don't all send an email
    for cc_email in itertools.chain(bzbug.cc, [bzbug.creator]):
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

    # Workaround python-gitlab bug by providing redundant state_event
    # https://github.com/python-gitlab/python-gitlab/pull/389
    issue.save(state_event='reopen')

    print("New GitLab issue created from bugzilla bug "
          "{}: {}".format(bzbug.id, issue.web_url))

    if bzbug.bugzilla.logged_in:
        bz = bzbug.bugzilla
        print("Adding a comment in bugzilla and closing the bug there")
        # TODO: Create a resolution for this specific case? MIGRATED or FWDED?
        bz.update_bugs(bzbug.bug_id, bz.build_update(
            comment=template.render_bugzilla_migration_comment(issue),
            status='RESOLVED',
            resolution='OBSOLETE'))


def options():
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
    parser.add_argument('--product', help="bugzilla product name",
                        required=True)
    parser.add_argument('--component', help="bugzilla component name")
    parser.add_argument('--bz-user', help="bugzilla username")
    parser.add_argument('--bz-password', help="bugzilla password")
    parser.add_argument('--target-project', metavar="USERNAME/PROJECT",
                        help="project name for gitlab, like \
                              'username/project'. If not provided, \
                              $user_namespace/$bugzilla_product will be used")
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

    if args.production:
        glurl = "https://gitlab.gnome.org/"
    else:
        glurl = "https://gitlab-test.gnome.org/"
    bzurl = "https://bugzilla.gnome.org/"
    giturl = "https://git.gnome.org/browse/"
    target = common.GitLab(glurl, giturl, args.token, args.product,
                           args.target_project, args.automate)

    target.connect()

    if not args.recreate and args.target_project is not None:
        check_if_target_project_exists(target)

    if not args.target_project and args.recreate:
        target.import_project()

    if args.only_import:
        return

    print("Connecting to %s" % bzurl)
    if args.bz_user and args.bz_password:
        bgo = bugzilla.Bugzilla(bzurl, args.bz_user, args.bz_password)
    else:
        print("WARNING: Bugzilla credentials were not provided, BZ bugs won't "
              "be closed and subscribers won't notice the migration")
        bgo = bugzilla.Bugzilla(bzurl, tokenfile=None)

    query = bgo.build_query(product=args.product, component=args.component)
    if args.component:
        print("Querying for open bugs for the '%s' product, '%s' component" %
              (args.product, args.component))
    else:
        print("Querying for open bugs for the '%s' product, all components" %
              args.product)
    query["status"] = "NEW ASSIGNED REOPENED NEEDINFO UNCONFIRMED".split()
    bzbugs = bgo.query(query)
    print("{} bugs found".format(len(bzbugs)))
    count = 0

    # There are products without Bugzilla tracking
    if len(bzbugs) != 0:
        milestone_cache = milestones.MilestoneCache(target)
        user_cache = users.UserCache(target, bgo, args.product)

        # TODO: Check if there were bugs from this module already filed (i.e.
        # use a tag to mark these)
        for bzbug in bzbugs:
            count += 1
            sys.stdout.write('[{}/{}] '.format(count, len(bzbugs)))
            processbug(bgo, target, user_cache, milestone_cache, bzbug)

    if os.path.exists('users_cache'):
        print('IMPORTANT: Remove the file \'users_cache\' after use, it \
contains sensitive data')


if __name__ == '__main__':
    main()
