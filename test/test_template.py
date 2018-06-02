import collections

from bztogl import template

BZURL = "https://bugzilla.gnome.org"

Bug = collections.namedtuple(
    'Bug', 'id creator assigned_to blocks depends_on see_also version'
)


def test_bugzilla_url():
    url = template._bugzilla_url(BZURL, 123456)
    assert url == 'https://bugzilla.gnome.org/show_bug.cgi?id=123456'


<<<<<<< HEAD
def _check_processed_markdown(input, expected):
    processed_text = template._autolink_markdown(input)
=======
def _check_processed_markdown(input, expected, migrated_issues={}):
    processed_text = template._autolink_markdown(BZURL, input, migrated_issues)
>>>>>>> 7d151cc... Add support for freedesktop.org services
    assert processed_text == expected


def test_bug_autolink_is_preserved():
    _check_processed_markdown(
        'Bug 123456 is related to bug 654321',
        ('[Bug 123456](https://bugzilla.gnome.org/show_bug.cgi?id=123456) is '
         'related to [bug 654321](https://bugzilla.gnome.org/show_bug.cgi?'
         'id=654321)'))


def test_spurious_gitlab_comment_links_are_removed():
    _check_processed_markdown('Comment #3 precedes comment #4',
                              'Comment 3 precedes comment 4')


def test_bug_without_creator_is_handled():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, None, None)
    user_cache = collections.defaultdict(lambda: None)
<<<<<<< HEAD
    template.render_issue_description(bug, 'Text body', user_cache)
=======
    template.render_issue_description(BZURL, bug, 'Text body',
                                      migrated_issues, user_cache)
>>>>>>> 7d151cc... Add support for freedesktop.org services


def test_stack_traces_are_quoted():
    _check_processed_markdown("""
Here's a stack trace.
#0  0x00000003fceb3248 in sys_alloc (m=0x3fcebb040 <_gm_>, nb=72)
    at /usr/src/debug/libffi-3.2.1-2/src/dlmalloc.c:3551

Here's some text after the stack trace.
""", """
Here's a stack trace.
```
#0  0x00000003fceb3248 in sys_alloc (m=0x3fcebb040 <_gm_>, nb=72)
    at /usr/src/debug/libffi-3.2.1-2/src/dlmalloc.c:3551
```

Here's some text after the stack trace.
""")


def test_xml_tags_are_quoted():
    _check_processed_markdown('Here is a <xml>tag</xml>',
                              'Here is a `<xml>`tag`</xml>`')


def test_xml_tags_already_inside_single_backticks_are_not_quoted():
    text = 'Here is an already escaped `<xml>` tag'
    _check_processed_markdown(text, text)


def test_xml_tags_already_inside_code_blocks_are_not_quoted():
    text = """
Here's some text.
```
Here's a <tag style="xml"> inside a code block.
```
"""
    _check_processed_markdown(text, text)


def test_quoting_text_body():
    text = "Here's a paragraph.\n\nHere's another one."
    processed_text = template._body_to_markdown_quote(text)
    assert processed_text == """>>>
Here's a paragraph.

Here's another one.
>>>
"""


def test_empty_version():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, [], None)
    user_cache = collections.defaultdict(lambda: None)
<<<<<<< HEAD
    description = template.render_issue_description(bug,
=======
    migrated_issues = {}
    description = template.render_issue_description(BZURL,
                                                    bug,
>>>>>>> 7d151cc... Add support for freedesktop.org services
                                                    'Text body',
                                                    user_cache)
    assert 'Version:' not in description


def test_master_version():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, [], 'master')
    user_cache = collections.defaultdict(lambda: None)
<<<<<<< HEAD
    description = template.render_issue_description(bug,
=======
    migrated_issues = {}
    description = template.render_issue_description(BZURL,
                                                    bug,
>>>>>>> 7d151cc... Add support for freedesktop.org services
                                                    'Text body',
                                                    user_cache)
    assert 'Version:' not in description


def test_other_version():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, [], '1.0')
    user_cache = collections.defaultdict(lambda: None)
<<<<<<< HEAD
    description = template.render_issue_description(bug,
                                                    'Text body',
=======
    migrated_issues = {}
    description = template.render_issue_description(BZURL, bug, 'Text body',
                                                    migrated_issues,
>>>>>>> 7d151cc... Add support for freedesktop.org services
                                                    user_cache)
    assert 'Version: 1.0' in description


<<<<<<< HEAD
def test_no_see_also():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, None, None)
    user_cache = collections.defaultdict(lambda: None)
    description = template.render_issue_description(bug,
                                                    'Text body',
                                                    user_cache)
    assert 'See also' not in description


def test_empty_see_also():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None, [], None)
    user_cache = collections.defaultdict(lambda: None)
    description = template.render_issue_description(bug,
                                                    'Text body',
                                                    user_cache)
=======
def test_no_relations():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, None, None, None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Blocking' not in description
    assert 'Depends on' not in description
    assert 'See also' not in description


def test_empty_blocks():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              [], None, None, None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Blocking' not in description


def test_bz_blocks():
    block_id = '792388'
    block_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              [block_id], None, None, None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Blocking' in description
    assert 'Bug 792388' in description
    assert block_url in description


def test_migrated_blocks():
    block_id = 792388
    block_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              [block_id], None, None, None)
    issues = {
        792388: Issue(1234)
    }
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Blocking' in description
    assert '#1234' in description
    assert block_url not in description


def test_empty_depends_on():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, [], None, None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Depends on' not in description


def test_bz_depends_on():
    depends_id = '792388'
    depends_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, [depends_id], None, None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Depends on' in description
    assert 'Bug 792388' in description
    assert depends_url in description


def test_migrated_depends_on():
    depends_id = 792388
    depends_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, [depends_id], None, None)
    issues = {
        792388: Issue(1234)
    }
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'Depends on' in description
    assert '#1234' in description
    assert depends_url not in description


def test_empty_see_also():
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, None, [], None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
>>>>>>> 7d151cc... Add support for freedesktop.org services
    assert 'See also' not in description


def test_bz_see_also():
    bug_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
<<<<<<< HEAD
              None, None, [bug_url], None)
    user_cache = collections.defaultdict(lambda: None)
    description = template.render_issue_description(bug,
                                                    'Text body',
                                                    user_cache)
    assert 'See also' in description
    assert 'Bug 792388' in description
    assert bug_url in description
=======
              None, None, [see_also_url], None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'See also' in description
    assert 'Bug 792388' in description
    assert see_also_url in description


def test_migrated_see_also():
    see_also_url = 'https://bugzilla.gnome.org/show_bug.cgi?id=792388'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
              None, None, [see_also_url], None)
    issues = {
        792388: Issue(1234)
    }
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
    assert 'See also' in description
    assert '#1234' in description
    assert see_also_url not in description
>>>>>>> 7d151cc... Add support for freedesktop.org services


def test_bogus_see_also():
    bug_url = 'my hovercraft is full of eels'
    bug = Bug(712869, 'geary-maint@gnome.bugs', '',
<<<<<<< HEAD
              None, None, [bug_url], None)
    user_cache = collections.defaultdict(lambda: None)
    description = template.render_issue_description(bug,
                                                    'Text body',
                                                    user_cache)
=======
              None, None, [see_also_url], None)
    issues = collections.defaultdict(lambda: None)
    description = template.render_issue_relations(BZURL, bug, 'Text body',
                                                  issues)
>>>>>>> 7d151cc... Add support for freedesktop.org services
    assert 'See also' in description
    assert bug_url in description
