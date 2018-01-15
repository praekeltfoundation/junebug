from docutils.nodes import (
    paragraph,
    literal_block, title, description,
    option, option_list, option_list_item, option_group, option_string)
from docutils.parsers.rst.directives import unchanged

from sphinx.util.compat import Directive

from argparse import _HelpAction


class ArgParseDirection(Directive):
    """
    This is a generator that implements just the small subset of features that
    we need from sphinx-argparse, since sphinx-argparse currently does not work
    with readthedocs.
    """
    has_content = True

    option_spec = {
        'module': unchanged,
        'func': unchanged,
        'prog': unchanged,
    }

    def run(self):
        args = load_function(self.options['module'], self.options['func'])()
        args.prog = self.options['prog']

        return [
            el(paragraph, text=args.description),
            el(literal_block, text=args.format_usage()),
            el(title, text='Named Arguments'),
            el(option_list, [
                el(option_list_item, [
                    el(option_group, [
                        el(option, [
                            el(option_string, text=arg),
                        ])
                        for arg in arguments
                    ]),
                    el(description, [
                        el(paragraph, text=descrip),
                    ])
                ])
                for descrip, arguments in get_options(args)
            ]),
        ]


def get_options(parser):
    # We unfortunately have to use private access here, as ArgParse doesn't
    # give us direct access to the arguments, only a formatted string of all
    # arguments. sphinx-argparse does the same thing.
    action = parser._action_groups[1]  # optional arguments
    options = []
    for action in action._group_actions:
        if isinstance(action, _HelpAction):
            continue

        help_string = action.help or None
        options.append((help_string, action.option_strings))
    return options


def el(cls, children=None, **kw):
    element = cls(**kw)
    element += children if children is not None else []
    return element


def load_function(module_path, function_name):
    return getattr(
        __import__(module_path, fromlist=[function_name]),
        function_name)


def setup(app):
    app.add_directive('argparse', ArgParseDirection)
