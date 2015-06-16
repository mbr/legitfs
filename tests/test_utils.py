from legitfs.util import split_using


def test_split_using():
    assert (split_using(lambda v: v > 5, [5, 4, 2, 9, 8, 3])
            == ([5, 4, 2, 9], [8, 3]))
