#!/usr/bin/python

from itertools import imap, chain
import errno
import fuse
import os
import stat
from warnings import warn

from dulwich.repo import Repo
from dulwich.errors import NotGitRepository

fuse.fuse_python_api = (0, 2)

def dirFromList(list):
    """
    Return a properly formatted list of items suitable to a directory listing.
    [['a', 'b', 'c']] => [[('a', 0), ('b', 0), ('c', 0)]]
    """
    return [[(x, 0) for x in list]]

class VNode(object):
    primary = False

    def __init__(self, name):
        self.name = name
        self.children = {}
        self.parent = None

    def add_child(self, child):
        self.children[child.name] = child
        child.parent = self

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent

    def dfs_iter(self):
        stack = [self]

        while stack:
            item = stack.pop()
            yield item
            stack.extend(reversed(item.children.values()))

    def dumps(self):
        parts = [str(self)]

        for child in self.children.itervalues():
            parts.append(child.dumps())

        return '\n'.join(parts)

    def find_handler(self, path):
        components = path.split(os.sep)
        if components[-1] == '':
            components = components[:-1]

        return self._find_handler(components)

    def remove_child(self, child):
        del self.children[child.name]
        child.parent = None
        return self

    @property
    def debug_name(self):
        return '<%s(%s)>' % (self.__class__.__name__, self.name)

    @property
    def leaf(self):
        return not bool(self.children)

    @property
    def path(self):
        if not self.parent:
            return os.sep + self.name

        names = [a.name for a in reversed(list(self.ancestors()))]
        names.append(self.name)
        return os.sep.join(names)

    def _find_handler(self, path_comp):
        me = path_comp.pop(0)

        assert me == self.name

        if not path_comp:
            # we've reached what we were looking for!
            return self

        if not path_comp[0] in self.children:
            return None

        return self.children[path_comp[0]]._find_handler(path_comp)

    def __str__(self):
        a_names = [a.debug_name for a in reversed(list(self.ancestors()))]
        a_names.append(self.debug_name)
        return '/'.join(a_names)


class DirNode(VNode):
    def fuse_getattr(self, path):
        return fuse.Stat(
            st_mode=stat.S_IFDIR | 0755,  # FIXME
            st_ino=0,
            st_dev=0,
            st_nlink=2,
            st_uid=0,  # FIXME
            st_gid=0,  # FIXME,
            st_size=4096,
            st_atime=0,  # FIXME
            st_mtime=0,  # FIXME,
            st_ctime=0,  # FIXME
        )

    def fuse_opendir(self, path):
        return 0  # opening allowed

    def fuse_readdir(self, path, offset):
        for e in '.', '..':
            yield fuse.Direntry(e)

        for child in self.children:
            yield fuse.Direntry(child)

    def fuse_releasedir(self, path):
        return 0


class VirtualDirNode(DirNode):
    def _find_handler(self, path_comp):
        me = path_comp.pop(0)
        assert me == self.name
        return self  # children are virtual

    def _get_rel_path(self, path):
        return os.path.relpath(path, self.path)


class RepoNode(DirNode):
    primary = True

    def __init__(self, name, repo_path):
        super(RepoNode, self).__init__(name)
        self.repo = Repo(repo_path)
        self.add_child(GitRefNode('HEAD', 'HEAD'))


class GitRefNode(VirtualDirNode):
    primary = True

    def __init__(self, name, ref):
        super(GitRefNode, self).__init__(name)
        self.ref = ref


    def fuse_getattr(self, path):
        if self.path == path:
            return super(GitRefNode, self).fuse_getattr(path)

        mode, blob = self._get_object(path)

        s = fuse.Stat(
            st_mode=mode,
            st_ino=0,
            st_dev=0,
            st_nlink=1,
            st_uid=0,  # FIXME
            st_gid=0,  # FIXME,
            st_size=blob.raw_length(),
            st_atime=0,  # FIXME
            st_mtime=0,  # FIXME,
            st_ctime=0,  # FIXME
        )
        return s
    fuse_fgetattr = fuse_getattr

    def fuse_open(self, path, flags):
        if flags & os.O_APPEND or\
           flags & os.O_CREAT or\
           flags & os.O_DIRECTORY or\
           flags & os.O_EXCL or\
           flags & os.O_LARGEFILE or\
           flags & os.O_NONBLOCK or\
           flags & os.O_TRUNC or\
           flags & os.O_WRONLY or\
           flags & os.O_RDWR:
           return -errno.ENOSYS

        return 0  # always succeed

    def fuse_read(self, path, size, offset):
        mode, blob = self._get_object(path)
        return blob.data[offset:offset+size]  # FIXME: this is horrible

    def fuse_readdir(self, path, offset):
        for de in super(GitRefNode, self).fuse_readdir(path, offset):
            yield de

        mode, tree = self._get_object(path)

        for mode, path, sha in tree.entries():
            yield fuse.Direntry(path)

        # FIXME: symbolic links!
        # "supported": O_NOATIME, O_NOCTTY, O_NOFOLLOW, O_SYNC, O_ASYNC

    def fuse_release(self, path, flags):
        return 0  # always succeed

    @property
    def tree(self):
        ref = self.parent.repo.refs[self.ref]
        commit = self.parent.repo[ref]
        tree = self.parent.repo[commit.tree]

        return tree

    def _get_object(self, path):
        rel_path = self._get_rel_path(path)
        if '.' == rel_path:
            return stat.S_IFDIR | 0755, self.tree  # FIXME: mode?
        mode, sha = self.tree.lookup_path(
            self.parent.repo.__getitem__, rel_path
        )
        return mode, self.parent.repo[sha]


class LegitFS(fuse.Fuse):
    def __init__(self, *args, **kwargs):
        super(LegitFS, self).__init__(*args, **kwargs)

        # add parser options
        self.parser.add_option(mountopt='root', metavar='ROOT', default='./',
                               help='Top-level dir to search for git '\
                                    'repositories')

    def __getattr__(self, name):
        def _(path, *args, **kwargs):
            endpoint = self.root.find_handler(path)
            #print "called %s(%r, %r, %r), endpoint %s" % (
            #    name, path, args, kwargs, endpoint)
            if not endpoint:
                return -errno.ENOENT
            func = getattr(endpoint, 'fuse_' + name, None)

            if not func:
                return -errno.ENOSYS

            return func(path, *args, **kwargs)
        return _

    def main(self):
        print "Collecting underpants..."
        root = os.path.abspath(self.cmdline[0].root)

        def make_node(path, relpath):
            try:
                dnode = RepoNode(relpath, path)
                return dnode
            except NotGitRepository:
                return DirNode(relpath)

        def walk_subtree(path, name):
            root = make_node(path, name)

            for sub in os.listdir(path):
                subpath = os.path.join(path, sub)
                if os.path.isdir(subpath):
                    root.add_child(walk_subtree(subpath, sub))

            return root

        root_node = walk_subtree(root, '')

        # prune tree
        queue = [node for node in root_node.dfs_iter() if node.leaf]
        while queue:
            node = queue.pop(0)
            if not node.primary:
                parent = node.parent.remove_child(node)
                if parent.leaf:
                    queue.append(parent)

        print root_node.dumps()

        self.root = root_node
        return super(LegitFS, self).main()


if __name__ == '__main__':
    import sys
    fs = LegitFS()
    fs.parse(errex=1)
    fs.main()
