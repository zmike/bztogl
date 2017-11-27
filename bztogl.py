#!/usr/bin/env python2.7

#    Copyright 2017 Alberto Ruiz <aruiz@gnome.org>

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
import urllib

import bugzilla
import gitlab

DESC_TEMPLATE = """## Submitted by {submitter}  
{assigned_to}
**[Link to original bug (#{id})](https://bugzilla.gnome.org/show_bug.cgi?id={id})**  
## Description
{body}
"""

COMMENT_TEMPLATE = """:{emoji}: **{author}** {action}:
{body}  
{attachment}
"""

ATTACHMENT_TEMPLATE = """  
{obsolete}**{kind} {atid}**{obsolete}, "{summary}":  
{markdown}
"""

MIGR_TEMPLATE = """-- GitLab Migration Automatic Message --

This bug has been migrated to GNOME's GitLab instance and has been closed from further activity.

You can subscribe and participate further through the new bug through this link to our GitLab instance: {}.
"""

class Target:
    def __init__ (self, token, product, target_product=None):
        self.token = token
        self.product = product
        if target_product:
            self.target_product = target_product
        else:
            self.target_product = "gnome/" + product

class GitLab(Target):
    GITLABURL = "https://gitlab-test.gnome.org/"

    def __init__ (self, token, product, target_product=None):
        Target.__init__(self, token, product, target_product)
        self.gl = None

    def connect (self):
        print("Connecting to %s" % self.GITLABURL)
        self.gl = gitlab.Gitlab(self.GITLABURL, self.token)

    def get_project(self):
        return self.gl.projects.get(self.target_product)

    def create_issue(self, id, summary, description, creation_time):
        return self.get_project().issues.create({'title': summary,
            'description': description,
            'labels': 'bugzilla',
            'created_at': creation_time})

    def find_user(self, email):
        possible_users = self.gl.users.search(email)
        if len(possible_users) == 1:
            return possible_users[0]
        return None

def autolink_markdown(text):
    text = re.sub(r'([Bb]ug) ([0-9]+)', '[\\1 \\2](https://bugzilla.gnome.org/show_bug.cgi?id=\\2)', text)
    # Prevent spurious links to other GitLab issues
    text = re.sub(r'([Cc]omment) #([0-9]+)', '\\1 \\2', text)
    return text

def body_to_markdown_quote (body):
    if not body:
        return '\n'
    return ">>>\n{}\n>>>\n".format(autolink_markdown(body.encode('utf-8')))

def id_to_name (bzid, user_cache):
    if bzid.endswith("gnome.bugs"):
        return bzid
    return user_cache[bzid].encode('utf-8')

def populate_user_cache(bgo, target, user_cache):
    real_names = {}
    for bzu in bgo.getusers(user_cache.keys()):
        gitlab_user = target.find_user(bzu.email)
        if gitlab_user is not None:
            real_names[bzu.email] = '@' + gitlab_user.username
        elif bzu.real_name:
            # Heuristically remove "(not reading bugmail) or (not receiving bugmail)"
            real_names[bzu.email] = re.sub(r' \(not .+ing bugmail\)', '', bzu.real_name)
        else:
            real_names[bzu.email] = '{}..@..{}'.format(bzu.email[:3], bzu.email[-3:])

    return real_names

def initial_comment_to_issue_description(bug, text, user_cache):
    if not text:
        text = ""

    # Assignment of $PROJECT@gnome.bugs effectively means unassigned
    assigned_to = ""
    if not bug.assigned_to.endswith("gnome.bugs"):
        assigned_to = "**Assigned to {}**  \n".format(id_to_name(bug.assigned_to, user_cache))

    return DESC_TEMPLATE.format(submitter=id_to_name(bug.creator, user_cache),
                                assigned_to=assigned_to,
                                id=bug.id,
                                body=body_to_markdown_quote(text))

def bugzilla_migration_closing_comment (gl_issue):
    return MIGR_TEMPLATE.format(gl_issue.web_url)

def processbug (bgo, target, bzbug):
    print ("Processing bug #%d: %s" % (bzbug.id, bzbug.summary.encode('utf-8')))
    #bzbug.id
    #bzbug.summary
    #bzbug.creator
    #bzbug.creationtime
    #bzbug.target_milestone
    #bzbug.blocks
    #bzbug.assigned_to

    def get_attachments_metadata (self):
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

    def gitlab_upload_file (target, filename, f):
        url = target.GITLABURL + "api/v3/projects/{}/uploads".format(target.get_project().id)
        target.gl.session.headers = {"PRIVATE-TOKEN": target.token}
        ret = target.gl.session.post (url,
                files={'file': (urllib.quote(filename), f)})
        if ret.status_code != 201:
            raise Exception("Could not upload file: {}".format(ret.text))
        return ret.json ()

    def migrate_attachment(comment, metadata):
        atid = comment['attachment_id']

        filename = metadata[atid]['file_name'].encode('utf-8')
        print ("    Attachment {} found, migrating".format(filename))
        attfile = bgo.openattachment(atid)
        ret = gitlab_upload_file(target, filename, attfile)

        return ATTACHMENT_TEMPLATE.format(atid=atid,
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

        if re.match(r'\*\*\* Bug [0-9]+ has been marked as a duplicate of this bug. \*\*\*', body):
            return 'link', 'closed a related bug', body

        return 'speech_balloon', 'said', body

    attachment_metadata = get_attachments_metadata (bzbug)
    comments = bzbug.getcomments()

    firstcomment = None if len(comments) < 1 else comments[0]
    desctext = None
    if firstcomment['author'] == bzbug.creator:
        desctext = firstcomment['text']
        if 'attachment_id' in firstcomment:
            desctext += '\n' + migrate_attachment(firstcomment, attachment_metadata)
        comments = comments[1:]

    user_cache = {}

    user_cache[bzbug.creator] = None
    for comment in comments:
        user_cache[comment['creator']] = None

    user_cache = populate_user_cache (bgo, target, user_cache)

    summary = "[BZ#{}] {}".format(bzbug.id, bzbug.summary.encode('utf-8'))
    description = initial_comment_to_issue_description (bzbug, desctext, user_cache)

    issue = target.create_issue (bzbug.id, summary, description, str(bzbug.creation_time))

    # Assign bug to actual account if exists
    assignee = target.find_user(bzbug.assigned_to)
    if assignee is not None:
        issue.assignee_id = assignee.id

    print ("Migrating comments: ")
    c = 0
    for comment in comments:
        c = c + 1
        print("  [{}/{}]".format(c, len(comments)))
        comment_attachment = ""
        # Only migrate attachment if this is the comment where it was created
        if 'attachment_id' in comment and comment['text'].startswith('Created attachment'):
            comment_attachment = migrate_attachment(comment, attachment_metadata)

        emoji, action, body = analyze_bugzilla_comment(comment, attachment_metadata)
        author = id_to_name(comment['author'], user_cache)

        issue.notes.create({
            'body': COMMENT_TEMPLATE.format(emoji=emoji, author=author,
                action=action,
                body=body_to_markdown_quote(body),
                attachment=comment_attachment),
            'created_at': str(comment['creation_time'])
        })

    issue.save()

    print("New GitLab issue created from bugzilla bug {}: {}".format(bzbug.id, issue.web_url))

    if bzbug.bugzilla.logged_in:
        bz = bzbug.bugzilla
        print("Adding a comment in bugzilla and closing the bug there")
        #TODO: Create a resolution for this specific case? MIGRATED or FWDED?
        bz.update_bugs(bzbug.bug_id,
                       bz.build_update(comment=bugzilla_migration_closing_comment (issue),
                                       status='RESOLVED',
                                       resolution='OBSOLETE'))


def options():
    parser = argparse.ArgumentParser(description="Bugzilla migration helper for bugzilla.gnome.org products")
    parser.add_argument('--production', help="target production instead of testing")
    parser.add_argument('--target', help="target mode (gitlab or phabricator)", choices=['gitlab', 'phab'], required=True)
    parser.add_argument('--token', help="gitlab/phabricator token API", required=True)
    parser.add_argument('--product', help="bugzilla product name", required=True)
    parser.add_argument('--bz-user', help="bugzilla username")
    parser.add_argument('--bz-password', help="bugzilla password")
    parser.add_argument('--target-product', help="product name for the target backend (gitlab/phab)")
    return parser.parse_args()

def main():
    target = None
    args = options()

    if args.target == "gitlab":
        target = GitLab (args.token, args.product, args.target_product)
        if args.production:
            target.GITLABURL = "https://gitlab.gnome.org/"
    elif args.target == "phab":
        print("Phabricator target super not implemented")
        sys.exit(1)
    else:
        print("%s target support not implemented" % args.target)
        sys.exit(1)

    target.connect()
    if not target.get_project():
        print("Project {} not present in {}".format(target.target_product, args.target))
        sys.exit(1)

    print ("Connecting to bugzilla.gnome.org")
    if args.bz_user and args.bz_password:
        bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org", args.bz_user, args.bz_password)
    else:
        print ("WARNING: Bugzilla credentials were not provided, BZ bugs won't be closed and subscribers won't notice the migration")
        bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org", tokenfile=None)

    query = bgo.build_query (product=args.product)
    query["status"] = ["NEW", "ASSIGNED", "REOPENED", "NEEDINFO", "UNCONFIRMED"]
    print ("Querying for open bugs for the '%s' product" % args.product)
    bzbugs = bgo.query(query)
    print ("{} bugs found".format(len(bzbugs)))
    count = 0

    #TODO: Check if there were bugs from this module already filed (i.e. use a tag to mark these)
    for bzbug in bzbugs:
        count += 1
        sys.stdout.write ('[{}/{}] '.format(count,len(bzbugs)))
        processbug (bgo, target, bzbug)

if __name__ == '__main__':
    main()

