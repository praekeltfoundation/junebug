from pprint import pformat

from docutils.nodes import (
    field_list, field, field_name, field_body, paragraph,
    strong, inline, emphasis, line_block, line, literal, literal_block)
from docutils.parsers.rst.directives import unchanged

from sphinx.util.compat import Directive

from confmodel.config import ConfigField


class ConfModelDirection(Directive):
    has_content = True

    option_spec = {
        'module': unchanged,
        'class': unchanged
    }

    def run(self):
        cls = load_class(self.options['module'], self.options['class'])

        return [
            el(field_list, [
                config_field(name, props)
                for name, props in get_config_fields(cls)
            ])
        ]


def config_field(name, props):
    return el(field, [
        config_field_name(name),
        el(field_body, [
            el(paragraph, text=props.doc),
            el(line_block, [
                el(line, [
                    strong(text='type:'),
                    inline(text=' '),
                    emphasis(text=props.field_type),
                ]),
                el(line, [
                    strong(text='default:'),
                    inline(text=' '),
                    config_field_default(props.default)
                ]),
            ])
        ])
    ])


def config_field_default(default):
    s = pformat(default)

    if '\n' in s:
        return literal_block(text=s)
    else:
        return literal(text=s)


def config_field_name(name):
    # hack to get rtfd.org's theme to newline all field bodies instead of only
    # some of them
    name = name.rjust(23)
    return el(field_name, text=name)


def el(cls, children=None, **kw):
    element = cls(**kw)
    element += children if children is not None else []
    return element


def get_config_fields(cls):
    fields = [
        (name, props)
        for name, props in cls.__dict__.iteritems()
        if isinstance(props, ConfigField)]

    return sorted(fields, key=config_field_order)


def config_field_order(field):
    _name, props = field
    return props.creation_order


def load_class(module_path, class_name):
    return getattr(__import__(module_path, fromlist=[class_name]), class_name)


def setup(app):
    app.add_directive('confmodel', ConfModelDirection)
