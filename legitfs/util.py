from itertools import takewhile


def split_using(predicate, iterable):
    it = iter(iterable)

    top = []
    for cur in it:
        top.append(cur)
        if predicate(cur):
            break

    return top, [i for i in it]
