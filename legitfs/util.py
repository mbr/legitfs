import os


def split_using(predicate, iterable):
    values = [i for i in iterable]

    for idx, v in enumerate(values):
        if predicate(v):
            break
    else:
        raise ValueError('Not value satisfies predicate')

    return values[:idx+1], values[idx+1:]


def split_git(path):
    """Translates a path into repository/repo_path components.

    All paths will be considered relative, regardless of whether or not they
    start with '/'.

    :return: (leading_path, repo_path)
    """

    # cleanup trailing slashes
    path = path.rstrip(os.sep)

    if not path:
        return '/', None

    try:
        return tuple(
            os.sep.join(c) if c else '' for c in
            split_using(lambda v: v.endswith('.git'), path.split(os.sep))
        )
    except ValueError:
        return path, None
