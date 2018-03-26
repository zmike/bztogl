Bugzilla to Gitlab migration tool
=================================

This is `bztogl`, a tool to migrate bug reports from Bugzilla to Gitlab.

The GNOME project's source code is moving from git.gnome.org to
gitlab.gnome.org, and our bugs from bugzilla.gnome.org are moving to
Gitlab, too!

While Git repositories can be easily moved to Gitlab — just add a Git
remote for gitlab.gnome.org and push all the refs —, bugs need to be
moved by a different tool.  This project, `bztogl`, provides that
tool.

# Installation

`bztogl` is a Python 3 script, and it requires the `python-bugzilla`
and `python-gitlab` modules.  You can set up a virtualenv (essentially
a personal sandbox for Python modules) for these like this:

```sh
mkdir ~/src/virtualenvs
virtualenv ~/src/virtualenvs/bztogl
source ~/src/virtualenvs/bztogl/bin/activate
# at this point your shell prompt will change to something like "(bztogl) $_"
pip3 install python-bugzilla
pip3 install python-gitlab
pip3 install --user -e .
# or use "python3 setup.py install --user" instead of the above
```

# What `bztogl` does

At a high level, `bztogl` needs to be able to do these:

* Connect to Bugzilla.
* Connect to Gitlab.
* Read bugs from Bugzilla, their attachments, etc.
* Write issues to Gitlab.

`bztogl` only deals with bugs that are open in Bugzilla.  *It will not
look at bugs that are already closed.*  Here, by "bugs that are open"
we mean bugs with status `NEW, ASSIGNED, REOPENED, NEEDINFO,
UNCONFIRMED`.

# Know what you are doing

Bugzilla and Gitlab have different ideas of how bug reports or issues
are structured, so **it is important to do a test run first**, to
check if the resulting issues in Gitlab look fine.

**You do not want to do this in a production project.**  Do it in a
test project instead.

## How to do a test run

1. Create a personal project for testing
2. Get an API key
3. Run `bztogl`

Each of these steps is detailed below.

## 1. Create a personal project for testing

You need a personal project for testing, where `bztogl` can create
new issues without affecting the main/public project.  That is, you
want this tool to create issues in `your_username/projectname`,
instead of the public `GNOME/projectname`.

Create a temporary project in your Gitlab account.  Alternatively, you
can register an account in `gitlab-test.gnome.org` and create a
project there.

## 2. Get an API key

`bztogl` needs to talk to the Gitlab API, and for this it needs an API
key.  You can consider `bztogl` to be an application that wants to
talk to Gitlab.

If you are using gitlab-test.gnome.org, get an API key at
https://gitlab-test.gnome.org/profile/personal_access_tokens — you can
use "`bztogl`" for in the **Name** field of the application you want
to register.  Pick an expiration date in the future, and **turn on**
the checkboxes for **api** and **read_user**, so that `bztogl` can
actually modify your test project.  Click on the "*Create personal
access token*" button.

**WRITE DOWN THE API TOKEN** you get right after clicking that
button.  You will not be able to see it again if you navigate away
from that web page!  If you lose the token, you can create a new one
by following the same steps.

## 3. Run `bztogl`

If you used the steps from the [installation] section, you will have a
Python virtualenv with the necessary modules.  Make sure you have the
virtualenv activated with the `activate` command form that example.

Now you can run this:

```sh
bztogl --token <your_api_token> --product myproject
```

You will get some output:

```
Connecting to https://gitlab-test.gnome.org/
Using target project 'username/myproject since --target-project was not provided
Connecting to bugzilla.gnome.org
WARNING: Bugzilla credentials were not provided, BZ bugs won't be closed and subscribers won't notice the migration
Querying for open bugs for the 'myproject' product
```

If everything works fine, `bztogl` will start importing bugs.  This is
a slow process.

**The WARNING about Bugzilla credentials** is completely fine; it
indicates that the bugs in Bugzilla will not be modified, which is
exactly what we want for a test run.

If you get an error, check the following:

* Do you have the correct API key?  Did you enable the **api** and
**read_user** checkboxes when creating the API key?

* Is the Bugzilla product name correct?  It's what you pass to the
`--product` option.

* Is the Gitlab project name correct?  If it is different from
Bugzilla's product name, you can use the
`--target-project=username/project` option.

[installation]: #installation
