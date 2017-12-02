import re

# Regexes taken from:
# http://cpansearch.perl.org/src/MKANAT/Parse-StackTrace-0.08/lib/Parse/
# This could be expanded to handle Python backtraces using code from the same
# library

_SPECIAL_LINES = (
    re.compile(r"""
        ^\#\d+\s+                             # #1
        (?:
            (?:0x[A-Fa-f0-9]{4,}\s+in\b)      # 0xdeadbeef in
            |
            (?:[A-Za-z_\*]\S+\s+\()           # some_function_name
            |
            (?:<signal \s handler \s called>)
        )
        """, re.VERBOSE | re.MULTILINE),
    re.compile(r'^\(gdb\) '),
    re.compile(r'^Thread \d+ \(.*\):$'),
    re.compile(r'^\[Switching to Thread .+ \(.+\)\]$'),
    re.compile(r'^Program received signal SIG[A-Z]+,'),
    re.compile(r'^Breakpoint \d, [A-Za-z_\*]\S+\s+\('),
)

_IGNORE_LINES = (
    'No symbol table info available.',
    'No locals.',
    '---Type <return> to continue, or q <return> to quit---',
)


def _is_special(line):
    if line in _IGNORE_LINES:
        return True
    return any(map(lambda r: r.search(line), _SPECIAL_LINES))


def _quote_stack_trace(lines):
    start = end = -1
    in_backtrace = False
    possible_end = False
    for ix, l in enumerate(lines):
        if not in_backtrace:
            if _is_special(l):
                start = ix
                in_backtrace = True
                possible_end = False
            continue

        if _is_special(l):
            possible_end = False
            continue

        if not l or l.isspace():
            possible_end = True
            continue

        # If this is a non-special, non-blank line following a number of
        # blank lines, then we're done
        if possible_end:
            end = ix - 1
            break
    else:
        if not in_backtrace:
            return lines
        end = ix + 1

    lines.insert(end, '```')
    lines.insert(start, '```')

    lines[end + 3:] = _quote_stack_trace(lines[end + 3:])
    return lines


def quote_stack_traces(text):
    """Looks for possible GDB backtraces in @text, and surrounds them with
    triple backticks in order to quote them for Markdown."""

    if not _SPECIAL_LINES[0].search(text):
        return text

    return '\n'.join(_quote_stack_trace(re.split(r'\r?\n', text)))
