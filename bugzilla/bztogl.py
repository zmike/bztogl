#!/usr/bin/python

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

import sys
import argparse

import bugzilla
import gitlab

DESC_TEMPLATE = """## Submitted by {submitter}  
**Assigned to {asigned_to}**  
**[Link to original bug (#{id})](https://bugzilla.gnome.org/show_bug.cgi?id={id})**  
## Description
{body}
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
    GITLABURL = "https://gitlab.gnome.org/"

    def __init__ (self, token, product, target_product=None):
        Target.__init__(self, token, product, target_product)
        self.gl = None

    def connect (self):
        print("Connecting to %s" % self.GITLABURL)
        self.gl = gitlab.Gitlab(self.GITLABURL, self.token)

    def get_project(self):
        return self.gl.projects.get(self.target_product)

    def create_issue(self, id, summary, description):
        return self.get_project().issues.create({'title': summary,
            'description': description,
            'labels': 'bugzillacreate'})

def body_to_markdown_quote (body):
    return ">>>\n{}\n>>>  \n".format(body.encode('utf-8'))

def id_to_name (bzid, user_cache):
    if bzid.endswith("gnome.bugs"):
        return bzid
    name = user_cache[bzid].encode('utf-8')
    result = "{} <<{}..@..{}>>".format(name, bzid[:3], bzid[-3:])
    return result

def populate_user_cache(bgo, target, user_cache):
    real_names = {}
    for bzu in bgo.getusers(user_cache.keys()):
        real_names[bzu.email] = bzu.real_name

    return real_names

def initial_comment_to_issue_description(bug, text, user_cache):
    if not text:
        text = ""

    return DESC_TEMPLATE.format(submitter=id_to_name(bug.creator, user_cache),
                                asigned_to=id_to_name(bug.assigned_to, user_cache),
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
                files={'file': (filename, f)})
        if ret.status_code != 201:
            raise Exception("Could not upload file: {}".format(ret.text))
        return ret.json ()

    attachment_metadata = get_attachments_metadata (bzbug)
    comments = bzbug.getcomments()

    firstcomment = None if len(comments) < 1 else comments[0]
    desctext = None
    if firstcomment['author'] == bzbug.creator:
        desctext = firstcomment['text']
        comments = comments[1:]

    user_cache = {}

    user_cache[bzbug.creator] = None
    for comment in comments:
        user_cache[comment['creator']] = None

    user_cache = populate_user_cache (bgo, target, user_cache)

    summary = "[BZ#{}] {}".format(bzbug.id, bzbug.summary.encode('utf-8'))
    description = initial_comment_to_issue_description (bzbug, desctext, user_cache)

    issue = target.create_issue (bzbug.id, summary, description)

    print ("Migrating comments: ")
    c = 0
    for comment in comments:
        c = c + 1
        print("  [{}/{}]".format(c, len(comments)))
        comment_attachment = ""
        if 'attachment_id' in comment:
            atid = comment['attachment_id']

            print ("    Attachment {} found, migrating".format(attachment_metadata[atid]['file_name']))
            attfile = bgo.openattachment(atid)
            ret = gitlab_upload_file(target, attachment_metadata[atid]['file_name'], attfile)
            comment_attachment = "  \n**Attachment ({}):**  \n{}".format (ret["alt"], ret['markdown'])

        issue.notes.create({'body': "## Submitted by {}\n{}  \n{}".format (id_to_name(comment['author'], user_cache),
            body_to_markdown_quote(comment['text']),
            comment_attachment)})

    issue.labels = ['bugzilla']
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
        bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org")

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

