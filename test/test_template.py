import collections

from bztogl import template


Bug = collections.namedtuple('Bug', 'id creator assigned_to blocks depends_on')


def test_bugzilla_url():
    url = template._bugzilla_url(123456)
    assert url == 'https://bugzilla.gnome.org/show_bug.cgi?id=123456'


def _check_processed_markdown(input, expected):
    processed_text = template._autolink_markdown(input)
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
    bug = Bug(712869, 'geary-maint@gnome.bugs', '', None, None)
    user_cache = collections.defaultdict(lambda: None)
    template.render_issue_description(bug, 'Text body', user_cache)


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
