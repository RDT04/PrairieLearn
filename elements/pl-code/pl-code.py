import prairielearn as pl
import lxml.html
from html import escape, unescape
import chevron
import os

import pygments
import pygments.lexers
import pygments.lexer
import pygments.formatters
import pygments.util
from pygments.token import Token

LANGUAGE_DEFAULT = None
NO_HIGHLIGHT_DEFAULT = False
SOURCE_FILE_NAME_DEFAULT = None
PREVENT_SELECT_DEFAULT = False
HIGHLIGHT_LINES_DEFAULT = None
HIGHLIGHT_LINES_COLOR_DEFAULT = '#b3d7ff'


class NoHighlightingLexer(pygments.lexer.Lexer):
    """
    Dummy lexer for when syntax highlighting is not wanted, but we still
    want to run it through the highlighter for styling and code escaping.
    """
    def __init__(self, **options):
        pygments.lexer.Lexer.__init__(self, **options)
        self.compress = options.get('compress', '')

    def get_tokens_unprocessed(self, text):
        return [(0, Token.Text, text)]


class HighlightingHtmlFormatter(pygments.formatters.HtmlFormatter):
    """
    Subclass of the default HTML formatter to provide more flexibility
    with highlighted lines.
    """
    def __init__(self, **options):
        pygments.formatters.HtmlFormatter.__init__(self, **options)
        self.hl_color = options.get('hl_color', HIGHLIGHT_LINES_COLOR_DEFAULT)

    def _highlight_lines(self, tokensource):
        """
        Highlighted the lines specified in the `hl_lines` option by post-processing the token stream.
        Based on the code at "https://github.com/pygments/pygments/blob/master/pygments/formatters/html.py#L816"
        """
        for i, (t, value) in enumerate(tokensource):
            if t != 1:
                yield t, value
            if i + 1 in self.hl_lines:  # i + 1 because Python indexes start at 0
                yield 1, f'<span class="pl-code-highlighted-line" style="background-color: {self.hl_color}">{value}</span>'
            else:
                yield 1, value


def parse_highlight_lines(highlight_lines):
    """
    Parses a string like "1", "1-4", "1-3,5,7-8" into a list of lines like
    [1], [1,2,3,4], and [1,2,3,5,7,8]
    """
    lines = []
    components = highlight_lines.split(',')
    for component in components:
        component = component.strip()
        try:
            line = int(component)
            lines.append(line)
        except ValueError:
            # Try parsing as "##-###"
            numbers = component.split('-')
            if len(numbers) != 2:
                return None
            try:
                start = int(numbers[0])
                end = int(numbers[1])
                for i in range(start, end + 1):
                    lines.append(i)
            except ValueError:
                return None
    return lines


def prepare(element_html, data):
    element = lxml.html.fragment_fromstring(element_html)
    required_attribs = []
    optional_attribs = ['language', 'no-highlight', 'source-file-name', 'prevent-select', 'highlight-lines', 'highlight-lines-color']
    pl.check_attribs(element, required_attribs, optional_attribs)

    language = pl.get_string_attrib(element, 'language', LANGUAGE_DEFAULT)
    if language is not None:
        try:
            pygments.lexers.get_lexer_by_name(language)
        except pygments.util.ClassNotFound:
            allowed_languages = map(pygments.lexers.get_all_lexers(), lambda tup: tup[1][0])
            raise Exception(f'Unknown language: "{language}". Must be one of {",".join(allowed_languages)}')

    source_file_name = pl.get_string_attrib(element, 'source-file-name', SOURCE_FILE_NAME_DEFAULT)
    if source_file_name is not None:
        if element.text is not None and not str(element.text).isspace():
            raise Exception('Existing code cannot be added inside html element when "source-file-name" attribute is used.')

    highlight_lines = pl.get_string_attrib(element, 'highlight-lines', HIGHLIGHT_LINES_DEFAULT)
    if highlight_lines is not None:
        if parse_highlight_lines(highlight_lines) is None:
            raise Exception('Could not parse highlight-lines attribute; check your syntax')


def render(element_html, data):
    element = lxml.html.fragment_fromstring(element_html)
    language = pl.get_string_attrib(element, 'language', LANGUAGE_DEFAULT)
    no_highlight = pl.get_boolean_attrib(element, 'no-highlight', NO_HIGHLIGHT_DEFAULT)
    specify_language = (language is not None) and (not no_highlight)
    source_file_name = pl.get_string_attrib(element, 'source-file-name', SOURCE_FILE_NAME_DEFAULT)
    prevent_select = pl.get_boolean_attrib(element, 'prevent-select', PREVENT_SELECT_DEFAULT)
    highlight_lines = pl.get_string_attrib(element, 'highlight-lines', HIGHLIGHT_LINES_DEFAULT)
    highlight_lines_color = pl.get_string_attrib(element, 'highlight-lines-color', HIGHLIGHT_LINES_COLOR_DEFAULT)

    if source_file_name is not None:
        base_path = data['options']['question_path']
        file_path = os.path.join(base_path, source_file_name)
        if not os.path.exists(file_path):
            raise Exception(f'Unknown file path: "{file_path}".')
        f = open(file_path, 'r')
        code = ''
        for line in f.readlines():
            code += line

        # Chop off ending newlines
        if code[:-2] == '\r\n':
            code = code[:-2]
        if code[:-1] == '\n':
            code = code[:-1]

        f.close()
        # Automatically escape code in file source (important for: html/xml).
        code = escape(code)
    else:
        # Strip a single leading newline from the code, if present. This
        # avoids having spurious newlines because of HTML like:
        #
        # <pl-code>
        # some_code
        # </pl-code>
        #
        # which technically starts with a newline, but we probably
        # don't want a blank line at the start of the code block.
        code = pl.inner_html(element)
        if len(code) > 1 and code[0] == '\r' and code[1] == '\n':
            code = code[2:]
        elif len(code) > 0 and (code[0] == '\n' or code[0] == '\r'):
            code = code[1:]

    if specify_language:
        lexer = pygments.lexers.get_lexer_by_name(language)
    else:
        lexer = NoHighlightingLexer()

    formatter_opts = {
        'style': 'friendly',
        'cssclass': 'mb-2 rounded',
        'prestyles': 'padding: 0.5rem; margin-bottom: 0px',
        'noclasses': True
    }
    if highlight_lines is not None:
        formatter_opts['hl_lines'] = parse_highlight_lines(highlight_lines)
        formatter_opts['hl_color'] = highlight_lines_color
    formatter = HighlightingHtmlFormatter(**formatter_opts)

    code = pygments.highlight(unescape(code), lexer, formatter)

    html_params = {
        'no_highlight': no_highlight,
        'code': code,
        'prevent_select': prevent_select,
    }

    with open('pl-code.mustache', 'r', encoding='utf-8') as f:
        html = chevron.render(f, html_params).strip()

    return html
