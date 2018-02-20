import re

from . import bt

# Note, the \n\ is to prevent trailing whitespace from being stripped by
# people's editors. It is there intentionally.

DESC_TEMPLATE = """## Submitted by {submitter}  \n\
{assigned_to}
**[Link to original bug (#{id})]\
({link_url}{id})**  \n\
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


def _bugzilla_url(bugid):
    return 'https://bugzilla.gnome.org/show_bug.cgi?id={}'.format(bugid)


def _autolink_markdown(text):
    text = re.sub(r'([Bb]ug) ([0-9]+)',
                  '[\\1 \\2]({})'.format(_bugzilla_url('\\2')), text)
    # Prevent spurious links to other GitLab issues
    text = re.sub(r'([Cc]omment) #([0-9]+)', '\\1 \\2', text)
    # Quote stack traces as preformatted text
    text = bt.quote_stack_traces(text)
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
                [^`]*?                # Followed by a string with no backticks
            )*?                       # These are skipped over before we find
        )
        (\<\/?[a-zA-Z0-9_="' -]*?\>)  # ...an XML-like tag
        """, re.VERBOSE)
    nsubs = 1
    while nsubs > 0:
        # Matches may overlap, so we have to keep substituting until none left
        text, nsubs = tags_outside_quotes.subn('\\1`\\2`', text)
    return text


def _body_to_markdown_quote(body):
    if not body:
        return '\n'
    return ">>>\n{}\n>>>\n".format(body)


def render_issue_description(
        bug, text, user_cache,
        importing_address="https://bugzilla.gnome.org/show_bug.cgi?id=",
        bug_url_function=_bugzilla_url):
    if not text:
        text = ""

    assigned_to = ""
    assignee = user_cache[bug.assigned_to]
    if assignee is not None:
        assigned_to = "Assigned to **{}**  \n".format(assignee.display_name())

    deps = ""
    if bug.depends_on:
        deps += "### Depends on\n"
        for bugid in bug.depends_on:
            deps += "  * [Bug {}]({})\n".format(bugid, bug_url_function(bugid))

    blocks = ""
    if bug.blocks:
        blocks += "### Blocking\n"
        for bugid in bug.blocks:
            blocks += "  * [Bug {}]({})\n".format(bugid,
                                                  bug_url_function(bugid))

    dependencies = DEPENDENCIES_TEMPLATE.format(depends_on=deps, blocks=blocks)
    if bug_url_function == _bugzilla_url:
        body = _autolink_markdown(text)
    else:
        body = text

    try:
        submitter = user_cache[bug.creator].display_name()
    except AttributeError:
        submitter = 'an unknown user'

    return DESC_TEMPLATE.format(
        link_url=importing_address, submitter=submitter,
        assigned_to=assigned_to, id=bug.id,
        body=body,
        dependencies=dependencies)


def render_bugzilla_migration_comment(gl_issue):
    return MIGR_TEMPLATE.format(gl_issue.web_url)


def render_comment(emoji, author, action, body, attachment,
                   bug_url_function=_bugzilla_url):

    if bug_url_function == _bugzilla_url and body:
        body = _autolink_markdown(body)

    body = _body_to_markdown_quote(body)

    return COMMENT_TEMPLATE.format(
        emoji=emoji, author=author, action=action,
        body=body,
        attachment=attachment)


def render_attachment(atid, metadata, gitlab_ret):
    return ATTACHMENT_TEMPLATE.format(
        atid=atid,
        kind='Patch' if metadata['is_patch'] else 'Attachment',
        obsolete='~~' if metadata['is_obsolete'] else '',
        summary=metadata['summary'],
        markdown=gitlab_ret['markdown'])
