from legitfs.util import split_using, translate_path
import pytest


def test_split_using():
    assert (split_using(lambda v: v > 5, [5, 4, 2, 9, 8, 3])
            == ([5, 4, 2, 9], [8, 3]))


@pytest.mark.parametrize('input, top, tail', [
    ('foo.git', 'foo.git', ''),
    ('test/.git', 'test/.git', ''),
    ('hello/my/.git/refs/heads/master', 'hello/my/.git', 'refs/heads/master'),
    ('sub.git/foo', 'sub.git', 'foo'),
])
def test_translate_path(input, top, tail):
    assert translate_path(input) == (top, tail)
    assert translate_path('/' + input) == (top, tail)
