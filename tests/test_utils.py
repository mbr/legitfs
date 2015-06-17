from legitfs.util import split_using, split_git
import pytest


@pytest.mark.parametrize('input, top, tail', [
    ([5, 4, 2, 9, 8, 3], [5, 4, 2, 9], [8, 3]),
    ([9, 8, 4], [9], [8, 4]),
])
def test_split_using(input, top, tail):
    assert split_using(lambda v: v > 5, input) == (top, tail)


def test_split_not_found():
    with pytest.raises(ValueError):
        split_using(lambda v: v > 5, [3])


@pytest.mark.parametrize('input, top, tail', [
    ('foo.git', 'foo.git', ''),
    ('test/.git', 'test/.git', ''),
    ('hello/my/.git/refs/heads/master', 'hello/my/.git', 'refs/heads/master'),
    ('sub.git/foo', 'sub.git', 'foo'),

    # also try absolute variants
    ('/foo.git', '/foo.git', ''),
    ('/test/.git', '/test/.git', ''),
    ('/hello/m/.git/refs/heads/master', '/hello/m/.git', 'refs/heads/master'),
    ('/sub.git/foo', '/sub.git', 'foo'),

    # and non-git-paths
    ('foo', 'foo', None),
    ('test/x', 'test/x', None),
    ('/foo', '/foo', None),
    ('/test/x', '/test/x', None),

    # root should work too
    ('/', '/', None)
])
def test_split_git(input, top, tail):
    assert split_git(input) == (top, tail)

    # trailing slashes should be ignored
    assert split_git(input + '/') == (top, tail)
    assert split_git(input + '//') == (top, tail)
