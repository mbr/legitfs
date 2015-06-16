import os


def split_using(predicate, iterable):
    it = iter(iterable)

    top = []
    for cur in it:
        top.append(cur)
        if predicate(cur):
            break

    return top, [i for i in it]


def translate_path(path):
    """Translates a path into repository/repo_path components.

    All paths will be considered relative, regardless of whether or not they
    start with '/'.

    :return: (leading_path, repo_path)
    """
    if path.startswith('/'):
        path = path[1:]

    return tuple(
        os.path.join(*c) if c else '' for c in
        split_using(lambda v: v.endswith('.git'), path.split(os.sep))
    )
