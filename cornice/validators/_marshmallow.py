# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import inspect

from six import with_metaclass


def _generate_marshmallow_validator(location):
    """
    Generate a marshmallow validator for data from the given location.

    :param location: The location in the request to find the data to be
        validated, such as "body" or "querystring".
    :type location: str
    :return: Returns a callable that will validate the request at the given
        location.
    :rtype: callable
    """

    def _validator(request, schema=None, deserializer=None, **kwargs):
        """
        Validate the location against the schema defined on the service.

        The content of the location is deserialized, validated and stored in
        the ``request.validated`` attribute.

        .. note::

            If no schema is defined, this validator does nothing.

        :param request: Current request
        :type request: :class:`~pyramid:pyramid.request.Request`

        :param schema: The marshmallow schema
        :param deserializer: Optional deserializer, defaults to
            :func:`cornice.validators.extract_cstruct`
        """
        import marshmallow

        if schema is None:
            return

        schema = _instantiate_schema(schema)

        class ValidatedField(marshmallow.fields.Field):
            def _deserialize(self, value, attr, data):
                schema.context.setdefault('request', request)
                deserialized = schema.load(value)
                # marshmallow 2.x returns a tuple, 3/x will always throw
                # and returns just data
                if isinstance(deserialized, tuple):
                    deserialized, errors = deserialized[0], deserialized[1]
                    # this should cover both non-strict and strict forms
                    if errors:
                        raise marshmallow.ValidationError(
                            errors)  # pragma: no cover
                return deserialized

        class Meta(object):
            strict = True
            ordered = True

        class RequestSchemaMeta(type):
            """
            A metaclass that will inject a location class attribute into
            RequestSchema.
            """

            def __new__(cls, name, bases, class_attrs):
                """
                Instantiate the RequestSchema class.

                :param name: The name of the class we are instantiating. Will
                    be "RequestSchema".
                :type name: str
                :param bases: The class's superclasses.
                :type bases: tuple
                :param dct: The class's class attributes.
                :type dct: dict
                """

                class_attrs[location] = ValidatedField(
                    required=True, load_from=location)
                class_attrs['Meta'] = Meta
                return type(name, bases, class_attrs)

        class RequestSchema(with_metaclass(
                RequestSchemaMeta, marshmallow.Schema)):
            """A schema to validate the request's location attributes."""
            pass

        validator(request, RequestSchema, deserializer, **kwargs)
        request.validated = request.validated.get(location, {})

    return _validator


body_validator = _generate_marshmallow_validator('body')
headers_validator = _generate_marshmallow_validator('header')
path_validator = _generate_marshmallow_validator('path')
querystring_validator = _generate_marshmallow_validator('querystring')


def _message_normalizer(exc, no_field_name="_schema"):
    """
    Normally `normalize_messages` will exist on `ValidationError` but pre 2.10
    versions don't have it
    :param exc:
    :param no_field_name:
    :return:
    """
    if isinstance(exc.messages, dict):
        return exc.messages
    if len(exc.field_names) == 0:
        return {no_field_name: exc.messages}
    return dict((name, exc.messages) for name in exc.field_names)


def validator(request, schema=None, deserializer=None, **kwargs):
    """
    Validate the full request against the schema defined on the service.

    Each attribute of the request is deserialized, validated and stored in the
    ``request.validated`` attribute
    (eg. body in ``request.validated['body']``).

    .. note::

        If no schema is defined, this validator does nothing.

    :param request: Current request
    :type request: :class:`~pyramid:pyramid.request.Request`

    :param schema: The marshmallow schema
    :param deserializer: Optional deserializer, defaults to
        :func:`cornice.validators.extract_cstruct`
    """
    import marshmallow
    from cornice.validators import extract_cstruct

    if deserializer is None:
        deserializer = extract_cstruct

    if schema is None:
        return

    schema = _instantiate_schema(schema)
    schema.context.setdefault('request', request)

    cstruct = deserializer(request)
    try:
        deserialized = schema.load(cstruct)
        # marshmallow 2.x returns a tuple, 3/x will always throw
        # and returns just data
        if isinstance(deserialized, tuple):
            deserialized, errors = deserialized[0], deserialized[1]
            # this should cover both non-strict and strict forms
            if errors:
                raise marshmallow.ValidationError(errors)
    except marshmallow.ValidationError as err:
        # translate = request.localizer.translate
        normalized_errors = _message_normalizer(err)
        for location, details in normalized_errors.items():
            location = location if location != '_schema' else ''
            if hasattr(details, 'items'):
                for subfield, msg in details.items():
                    request.errors.add(location, subfield, msg)
            else:
                request.errors.add(location, location, details)
    else:
        request.validated.update(deserialized)


def _instantiate_schema(schema):
    if not inspect.isclass(schema):
        raise ValueError('You need to pass Marshmallow class instead '
                         'of schema instance')
    return schema()
