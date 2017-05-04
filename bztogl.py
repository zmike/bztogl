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

class Target:
    def __init__ (self, token):
        self.token = token

class GitLab(Target):
    GITLABURL = "https://gitlab.gnome.org/"

    def __init__ (self, token):
        Target.__init__(self, token)

    def connect (self):
        print("Connecting to %s" % self.GITLABURL)
        self.gl = gitlab.Gitlab(self.GITLABURL, self.token)

def initial_comment_to_issue_header(bug, text):
    pass

def attachments_to_comments():
    pass

def convert_bug_comment_stream():
    pass

def processbug (target, bzbug):
    print ("Processing bug #%d: %s" % (bzbug.id, bzbug.summary))
    #bzbug.id
    #bzbug.summary
    #bzbug.creator
    #bzbug.creationtime

    #bzbug.target_milestone
    #bzbug.blocks

    #b1.assigned_to

    #b1.getcomments
    #b1.get_attachment_ids()
    #TODO: Close/close comment
    pass

def options():
    parser = argparse.ArgumentParser(description="Bugzilla migration helper for bugzilla.gnome.org products")
    parser.add_argument('--target', help="target mode (gitlab or phabricator)", choices=['gitlab', 'phab'], required=True)
    parser.add_argument('--token', help="gitlab/phabricator token API", required=True)
    parser.add_argument('--product', help="bugzilla product name", required=True)
    parser.add_argument('--bz-user', help="bugzilla username")
    parser.add_argument('--bz-password', help="bugzilla password")

    return parser.parse_args()

def main():
    target = None
    args = options()

    if args.target == "gitlab":
        target = GitLab (args.token)
    elif args.target == "phab":
        print("Phabricator target super not implemented")
        sys.exit(1)
    else:
        print("%s target support not implemented" % args.target)
        sys.exit(1)

    target.connect()

    print ("Connecting to bugzilla.gnome.org")
    bgo = bugzilla.Bugzilla("https://bugzilla.gnome.org")
    query = bgo.build_query (product=args.product)
    query["status"] = ["NEW", "ASSIGNED", "REOPENED", "NEEDINFO", "UNCONFIRMED"]
    print ("Querying for open bugs for the '%s' product" % args.product)
    bzbugs = bgo.query(query)

    for bzbug in bzbugs:
        processbug (target, bzbug)

if __name__ == '__main__':
    main()

