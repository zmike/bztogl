Bugzilla to Gitlab migration tool
=================================

The GNOME project's source code is moving from git.gnome.org to
gitlab.gnome.org, and our bugs from bugzilla.gnome.org are moving to
Gitlab, too!

While Git repositories can be easily moved to Gitlab — just add a Git
remote for gitlab.gnome.org and push all the refs —, bugs need to be
moved by a different tool.  This project, `bztogl`, provides that tool.

# Requirements

`bztogl` is a Python 3 script, and it requires the `bugzilla` and
`python-gitlab` modules.  You can set up a virtualenv (essentially a
personal sandbox for Python modules) for these like this:

```sh
mkdir ~/src/virtualenvs
virtualenv ~/src/virtualenvs/bztogl
source ~/src/virtualenvs/bztogl/bin/activate
# at this point your shell prompt will change to something like "(bztogl) $_"
pip install bugzilla
pip install python-gitlab
```

