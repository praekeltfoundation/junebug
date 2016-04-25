from functools import wraps

from twisted.web import http

from jsonschema import Draft4Validator

from junebug.utils import response


def validate(*validators):
    def validator(fn):
        @wraps(fn)
        def wrapper(api, req, *a, **kw):
            errors = []

            for v in validators:
                errors.extend(v(req, *a, **kw) or [])

            if not errors:
                return fn(api, req, *a, **kw)
            else:
                return response(
                    req, 'api usage error', {'errors': sorted(errors)},
                    code=http.BAD_REQUEST)

        return wrapper

    return validator


def body_schema(schema):
    json_validator = Draft4Validator(schema)

    def validator(req, body, *a, **kw):
        return [{
            'type': 'invalid_body',
            'message': e.message,
            'schema_path': list(e.schema_path),
        } for e in json_validator.iter_errors(body)]

    return validator
