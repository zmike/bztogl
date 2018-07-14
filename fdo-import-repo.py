#!/usr/bin/env python3

# freedesktop.org GitLab import script
#
# This script will read from stdin line-by-line, with the following format:
# fdorepo/name gitlabgroup/gitlabproject
#
# It will:
#   - disable direct pushes to ssh://git.freedesktop.org/git/fdorepo/name
#     and enable force-pushes so it can be a perfect mirror
#   - create a GitLab repo at https://gitlab.freedesktop.org/gitlabgroup/gitlabproject
#   - mirror the content from the fd.o repo into the GitLab repo
#
# It does _not_ set up mirroring from GitLab to fd.o, as this requires direct
# shell access to the GitLab cluster. To do so, please send admins entries in
# the same format you feed as input to this script.
#
# This requires you have sufficient shell access to kemper.freedesktop.org, and
# that the 'gitlab-mirror' user has been added to the correct group on LDAP.
#
# Author: Daniel Stone <daniels@collabora.com>

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.parse

import gitlab

class Config:
    def __init__(self):
        self.gitlab_token = None
        self.gitlab = None
        self.kemper_host = None
        self.issues = False
        self.merge_requests = False
        self.gitlab = None

class Repo:
    def __init__(self, config, url_fdo, url_gitlab):
        self.config = config
        self.url_gitlab = url_gitlab
        self.url_fdo = url_fdo
        self.project = None
        self.imported = False

    def gitlab_repo_file_path(self):
        return "/gitlab-data/git-data/repositories/%s.git" % self.url_gitlab

    def gitlab_repo_mirror_cmd(self):
        return 'GIT_DIR=%s git config --local fdo.mirror-dir %s && mkdir %s/custom_hooks && ln -s /gitlab-ssh-keys/git-post-receive-mirror %s/custom_hooks/post-receive' % (self.gitlab_repo_file_path(), self.url_fdo, self.gitlab_repo_file_path(), self.gitlab_repo_file_path())

    def legacy_file_path(self):
        return "/srv/git.freedesktop.org/git/%s.git" % self.url_fdo

    def legacy_clone_path(self):
        return "git://anongit.freedesktop.org/git/%s" % self.url_fdo

    def prepare_repo_kemper(self):
        # Accept non-fast-forwards (to make a perfect mirror), and disable
        # direct user pushes, as the only pushes will come from GitLab.
        cmd = ["ssh", self.config.kemper_host, "sh", "-c",
               "'GIT_DIR=%s git config --local receive.denynonfastforwards false && ln -s /srv/git.freedesktop.org/hooks/pre-receive-gitlab %s/hooks/pre-receive'" % (self.legacy_file_path(), self.legacy_file_path())] 
        subprocess.run(cmd, check=True)

    def rollback_repo_kemper(self):
        # Accept non-fast-forwards (to make a perfect mirror), and disable
        # direct user pushes, as the only pushes will come from GitLab.
        cmd = ["ssh", self.config.kemper_host, "sh", "-c",
               "'GIT_DIR=%s git config --local receive.denynonfastforwards true && rm -f %s/hooks/pre-receive'" % (self.legacy_file_path(), self.legacy_file_path())] 
        subprocess.run(cmd, check=True)

    def get_namespace_id(self):
        # Surely there has to be a cleaner way to do this ... ?
        namespace = self.url_gitlab.split('/')[:-1]
        for ns in self.config.gitlab.namespaces.list(search=namespace[-1]):
            if ns.full_path == "/".join(namespace):
                return ns.id
        raise Exception("Couldn't find GitLab namespace %s" % namespace)

    def begin_gitlab_import(self):
        self.project = self.config.gitlab.projects.create({
            "name": self.url_gitlab.split('/')[-1],
            "namespace_id": self.get_namespace_id(),
            "import_url": self.legacy_clone_path(),
            "issues_enabled": self.config.issues,
            "merge_requests_enabled": self.config.merge_requests,
            "wiki_enabled": False,
            "merge_method": "ff",
            "visibility": "public"
        })

    def get_import_status(self):
        self.config.gitlab.session.headers = { "PRIVATE-TOKEN": self.config.gitlab_token }
        url = "https://gitlab.freedesktop.org/api/v4/projects/%d" % self.project.id
        ret = self.config.gitlab.session.get(url)
        if ret.status_code != 200:
            raise Exception("Status query for %s failed: %s" % (self.url_gitlab, ret.text))
        return json.loads(ret.text).get("import_status") == "finished"
        


def main():
    parser = argparse.ArgumentParser(description="fd.o GitLab repo import",
                                     epilog="""
This script imports a repository from fd.o's old Git hosting into GitLab.

It accepts input on stdin in the following format, one per line:
fdorepo/name gitlabgroup/gitlabproject

For example:
wayland/wayland wayland/wayland
wayland/weston wayland/weston
wayland/wayland-web wayland/wayland.freedesktop.org
^D

You will need SSH access to kemper (either being in the group, or being root),
as well as a GitLab access token (user menu -> settings -> access tokens) for
an admin account. To make this quicker, you almost certainly want a master
connection active.

The script will create the GitLab project itself, as well as disabling pushes
to the old repository. It will _not_ set up mirroring from GitLab to the old
repository, which will need to be done by someone with shell access to the
Kubernetes cluster.

Please co-ordinate with an admin when doing this script, and later send them
a copy of the repository list you imported.
""")

    parser.add_argument("--kemper-host",
                        default="kemper.freedesktop.org",
                        help="Hostname to pass to SSH for access to kemper",
                        required=True)
    parser.add_argument("--gitlab-token",
                        help="GitLab access token",
                        required=True)
    parser.add_argument("--issues",
                        default=False,
                        action="store_true",
                        help="Enable issues on migrated repos")
    parser.add_argument("--merge-requests",
                        default=False,
                        action="store_true",
                        help="Enable merge requests on migrated repos")
    config = Config()
    parser.parse_args(namespace=config)
    config.gitlab = gitlab.Gitlab("https://gitlab.freedesktop.org",
                                  config.gitlab_token,
                                  api_version=4)

    repos = []

    for line in sys.stdin:
        try:
            (url_fdo, url_gitlab) = line[:-1].split(' ')
        except:
            print("Malformed line '%s': must be in format fdorepo/name gitlabgroup/gitlabproject" % line[:-1])
            continue

        repo = Repo(config, url_fdo, url_gitlab)
        repos.append(repo)

        try:
            repo.prepare_repo_kemper()
        except Exception as e:
            print("Failed to migrate %s to %s: '%s'" % (url_fdo, url_gitlab, e))
            traceback.print_exc()
            continue

        try:
            repo.begin_gitlab_import()
        except Exception as e:
            print("Failed to migrate %s to %s: '%s'" % (url_fdo, url_gitlab, e))
            traceback.print_exc()
            continue

    all_imported = False
    while not all_imported:
        time.sleep(2)
        all_imported = True
        for repo in repos:
            if repo.project and not repo.imported:
                repo.imported = repo.get_import_status()
                if not repo.imported:
                    all_imported = False

    print("SUCCESSFULLY MIGRATED:")
    print("")
    print("")
    for repo in repos:
        if repo.project:
            print("%s -> %s" % (repo.url_fdo, repo.url_gitlab))

    print("")
    print("")
    print("")
    print("FAILED MIGRATION:")
    for repo in repos:
        if not repo.project:
            print("%s -> %s" % (repo.url_fdo, repo.url_gitlab))
            repo.rollback_repo_kemper()

    print("")
    print("")
    print("")
    print("Run on GitLab Kubernetes cluster:")
    for repo in repos:
        print(repo.gitlab_repo_mirror_cmd())

    print("")
    print("")
    print("")
    print("")
    print("Done!")

main()
