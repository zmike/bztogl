import bt


def _compare_quoted_backtraces(prefix):
    with open('test/data/{}-input.txt'.format(prefix)) as f:
        raw = f.read().decode('utf-8')

    with open('test/data/{}-expected.txt'.format(prefix)) as f:
        expected = f.read().decode('utf-8')

    actual = bt.quote_stack_traces(raw)
    assert actual == expected


def test_comment_that_is_only_backtrace():
    _compare_quoted_backtraces('bt1')


def test_comment_with_long_full_backtrace_and_other_text():
    _compare_quoted_backtraces('bt2')


def test_comment_with_several_backtraces():
    # Note that this one thinks the backtrace stops at the wrong place
    # due to a blank line in the output of a watchpoint. We can't handle
    # everything...
    _compare_quoted_backtraces('bt3')
