import re
import urllib

from . import bt

# Note, the \n\ is to prevent trailing whitespace from being stripped by
# people's editors. It is there intentionally.

DESC_TEMPLATE = """## Submitted by {submitter}  \n\
{assigned_to}
**[Link to original bug (#{id})]\
({link_url})**  \n\
## Description
{body}

{dependencies}
"""

DEPENDENCIES_TEMPLATE = """{depends_on}
{blocks}
{see_also}
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

This bug has been migrated to {instance}'s GitLab instance and has been \
closed from further activity.

You can subscribe and participate further through the new bug through this \
link to our GitLab instance: {gitlab_url}.
"""


def _bugzilla_url(instance_base, bugid):
    url = '{instance_base}/show_bug.cgi?id={bugid}'
    return url.format(instance_base=instance_base, bugid=bugid)


def _autolink_markdown(instance_base, text):
    text = re.sub(r'([Bb]ug) ([0-9]+)',
                  '[\\1 \\2]({})'.format(_bugzilla_url(instance_base, '\\2')),
                                         text)
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
        instance_base, bug, text, user_cache, importing_address=None,
        bug_url_function=_bugzilla_url):
    if not text:
        text = ""
    if not importing_address:
        importing_address = "{}/show_bug.cgi?id=".format(instance_base)

    assigned_to = ""
    assignee = None
    if bug.assigned_to:
      assignee = user_cache[bug.assigned_to]
    if assignee is not None:
        assigned_to = "Assigned to **{}**  \n".format(assignee.display_name())

    deps = ""
    if bug.depends_on:
        deps += "### Depends on\n"
        for bugid in bug.depends_on:
            deps += "  * [Bug {}]({})\n".format(bugid,
                                                bug_url_function(instance_base,
                                                                 bugid))

    blocks = ""
    if bug.blocks:
        blocks += "### Blocking\n"
        for bugid in bug.blocks:
            blocks += "  * [Bug {}]({})\n".format(bugid,
                                                  bug_url_function(instance_base,
                                                                   bugid))

    see_also = ""
    if bug.see_also:
        see_also += "### See also\n"
        for url in bug.see_also:
            is_bz = False
            try:
                bug_url = urllib.parse.urlparse(url)
                query = urllib.parse.parse_qs(bug_url.query)
            except Exception as e:
                pass
            else:
                ids = query.get('id', [])
                # XXX
                if bug_url.netloc == 'bugzilla.gnome.org' and ids:
                    is_bz = True
                    see_also += "  * [Bug {}]({})\n".format(ids[0], url)

            if not is_bz:
                see_also += "  * {}\n".format(url)

    dependencies = DEPENDENCIES_TEMPLATE.format(depends_on=deps,
                                                blocks=blocks,
                                                see_also=see_also)
    if bug_url_function == _bugzilla_url:
        body = _autolink_markdown(instance_base, text)
    else:
        body = text

    if bug.version and bug.version not in ('master', 'unspecified'):
        body += '\n\nVersion: {}'.format(bug.version)

    submitter = 'an unknown user'
    if bug.creator in user_cache:
        try:
            submitter = user_cache[bug.creator].display_name()
        except AttributeError:
            pass

    return DESC_TEMPLATE.format(
        link_url=importing_address, submitter=submitter,
        assigned_to=assigned_to, id=bug.id,
        body=body,
        dependencies=dependencies)


def render_bugzilla_migration_comment(instance, gl_issue):
    return MIGR_TEMPLATE.format(instance=instance, gitlab_url=gl_issue.web_url)


def render_comment(instance_base, emoji, author, action, body, attachment,
                   bug_url_function=_bugzilla_url):

    if bug_url_function == _bugzilla_url and body:
        body = _autolink_markdown(instance_base, body)

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
