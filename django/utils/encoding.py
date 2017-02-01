import codecs
import datetime
import locale
from decimal import Decimal
from urllib.parse import quote, unquote_to_bytes

from django.utils import six
from django.utils.functional import Promise


class DjangoUnicodeDecodeError(UnicodeDecodeError):
    def __init__(self, obj, *args):
        self.obj = obj
        UnicodeDecodeError.__init__(self, *args)

    def __str__(self):
        original = UnicodeDecodeError.__str__(self)
        return '%s. You passed in %r (%s)' % (original, self.obj, type(self.obj))


# For backwards compatibility. (originally in Django, then added to six 1.9)
python_2_unicode_compatible = six.python_2_unicode_compatible


def smart_text(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Return a string representing 's'. Treat bytestrings using the 'encoding'
    codec.

    If strings_only is True, don't convert (some) non-string-like objects.
    """
    if isinstance(s, Promise):
        # The input is the result of a gettext_lazy() call.
        return s
    return force_text(s, encoding, strings_only, errors)


_PROTECTED_TYPES = (
    type(None), int, float, Decimal, datetime.datetime, datetime.date, datetime.time,
)


def is_protected_type(obj):
    """Determine if the object instance is of a protected type.

    Objects of protected types are preserved as-is when passed to
    force_text(strings_only=True).
    """
    return isinstance(obj, _PROTECTED_TYPES)


def force_text(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Similar to smart_text, except that lazy instances are resolved to
    strings, rather than kept as lazy objects.

    If strings_only is True, don't convert (some) non-string-like objects.
    """
    # Handle the common case first for performance reasons.
    if issubclass(type(s), str):
        return s
    if strings_only and is_protected_type(s):
        return s
    try:
        if isinstance(s, bytes):
            s = str(s, encoding, errors)
        else:
            s = str(s)
    except UnicodeDecodeError as e:
        if not isinstance(s, Exception):
            raise DjangoUnicodeDecodeError(s, *e.args)
        else:
            # If we get to here, the caller has passed in an Exception
            # subclass populated with non-ASCII bytestring data without a
            # working __str__() method. Try to handle this without raising a
            # further exception by individually forcing the exception args
            # to strings.
            s = ' '.join(force_text(arg, encoding, strings_only, errors)
                         for arg in s)
    return s


def smart_bytes(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Returns a bytestring version of 's', encoded as specified in 'encoding'.

    If strings_only is True, don't convert (some) non-string-like objects.
    """
    if isinstance(s, Promise):
        # The input is the result of a gettext_lazy() call.
        return s
    return force_bytes(s, encoding, strings_only, errors)


def force_bytes(s, encoding='utf-8', strings_only=False, errors='strict'):
    """
    Similar to smart_bytes, except that lazy instances are resolved to
    strings, rather than kept as lazy objects.

    If strings_only is True, don't convert (some) non-string-like objects.
    """
    # Handle the common case first for performance reasons.
    if isinstance(s, bytes):
        if encoding == 'utf-8':
            return s
        else:
            return s.decode('utf-8', errors).encode(encoding, errors)
    if strings_only and is_protected_type(s):
        return s
    if isinstance(s, memoryview):
        return bytes(s)
    if isinstance(s, Promise):
        return str(s).encode(encoding, errors)
    if not isinstance(s, str):
        try:
            return str(s).encode(encoding)
        except UnicodeEncodeError:
            if isinstance(s, Exception):
                # An Exception subclass containing non-ASCII data that doesn't
                # know how to print itself properly. We shouldn't raise a
                # further exception.
                return b' '.join(force_bytes(arg, encoding, strings_only, errors)
                                 for arg in s)
            return str(s).encode(encoding, errors)
    else:
        return s.encode(encoding, errors)


smart_str = smart_text
force_str = force_text

smart_str.__doc__ = """
Apply smart_text in Python 3 and smart_bytes in Python 2.

This is suitable for writing to sys.stdout (for instance).
"""

force_str.__doc__ = """
Apply force_text in Python 3 and force_bytes in Python 2.
"""


def iri_to_uri(iri):
    """
    Convert an Internationalized Resource Identifier (IRI) portion to a URI
    portion that is suitable for inclusion in a URL.

    This is the algorithm from section 3.1 of RFC 3987, slightly simplified
    since the input is assumed to be a string rather than an arbitrary byte
    stream.

    Take an IRI (string or UTF-8 bytes, e.g. '/I ♥ Django/' or
    b'/I \xe2\x99\xa5 Django/') and return a string containing the encoded
    result with ASCII chars only (e.g. '/I%20%E2%99%A5%20Django/').
    """
    # The list of safe characters here is constructed from the "reserved" and
    # "unreserved" characters specified in sections 2.2 and 2.3 of RFC 3986:
    #     reserved    = gen-delims / sub-delims
    #     gen-delims  = ":" / "/" / "?" / "#" / "[" / "]" / "@"
    #     sub-delims  = "!" / "$" / "&" / "'" / "(" / ")"
    #                   / "*" / "+" / "," / ";" / "="
    #     unreserved  = ALPHA / DIGIT / "-" / "." / "_" / "~"
    # Of the unreserved characters, urllib.quote already considers all but
    # the ~ safe.
    # The % character is also added to the list of safe characters here, as the
    # end of section 3.1 of RFC 3987 specifically mentions that % must not be
    # converted.
    if iri is None:
        return iri
    elif isinstance(iri, Promise):
        iri = str(iri)
    return quote(iri, safe="/#%[]=:;$&()+,!?*@'~")


def uri_to_iri(uri):
    """
    Converts a Uniform Resource Identifier(URI) into an Internationalized
    Resource Identifier(IRI).

    This is the algorithm from section 3.2 of RFC 3987.

    Takes an URI in ASCII bytes (e.g. '/I%20%E2%99%A5%20Django/') and returns
    a string containing the encoded result (e.g. '/I \xe2\x99\xa5 Django/').
    """
    if uri is None:
        return uri
    uri = force_bytes(uri)
    iri = unquote_to_bytes(uri)
    return repercent_broken_unicode(iri).decode('utf-8')


def escape_uri_path(path):
    """
    Escape the unsafe characters from the path portion of a Uniform Resource
    Identifier (URI).
    """
    # These are the "reserved" and "unreserved" characters specified in
    # sections 2.2 and 2.3 of RFC 2396:
    #   reserved    = ";" | "/" | "?" | ":" | "@" | "&" | "=" | "+" | "$" | ","
    #   unreserved  = alphanum | mark
    #   mark        = "-" | "_" | "." | "!" | "~" | "*" | "'" | "(" | ")"
    # The list of safe characters here is constructed subtracting ";", "=",
    # and "?" according to section 3.3 of RFC 2396.
    # The reason for not subtracting and escaping "/" is that we are escaping
    # the entire path, not a path segment.
    return quote(path, safe="/:@&+$,-_.!~*'()")


def repercent_broken_unicode(path):
    """
    As per section 3.2 of RFC 3987, step three of converting a URI into an IRI,
    we need to re-percent-encode any octet produced that is not part of a
    strictly legal UTF-8 octet sequence.
    """
    try:
        path.decode('utf-8')
    except UnicodeDecodeError as e:
        repercent = quote(path[e.start:e.end], safe=b"/#%[]=:;$&()+,!?*@'~")
        path = repercent_broken_unicode(
            path[:e.start] + force_bytes(repercent) + path[e.end:])
    return path


def filepath_to_uri(path):
    """Convert a file system path to a URI portion that is suitable for
    inclusion in a URL.

    This method will encode certain chars that would normally be recognized as
    special chars for URIs.  Note that this method does not encode the '
    character, as it is a valid character within URIs.  See
    encodeURIComponent() JavaScript function for more details.

    Return a string containing the result.
    """
    if path is None:
        return path
    # I know about `os.sep` and `os.altsep` but I want to leave
    # some flexibility for hardcoding separators.
    return quote(path.replace("\\", "/"), safe="/~!*()'")


def get_system_encoding():
    """
    The encoding of the default system locale but falls back to the given
    fallback encoding if the encoding is unsupported by python or could
    not be determined.  See tickets #10335 and #5846
    """
    try:
        encoding = locale.getdefaultlocale()[1] or 'ascii'
        codecs.lookup(encoding)
    except Exception:
        encoding = 'ascii'
    return encoding


DEFAULT_LOCALE_ENCODING = get_system_encoding()
