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

class VNode(object):
    primary = False

    def __init__(self, name):
        self.name = name
        self.children = {}
        self.parent = None

    def add_child(self, child):
        self.children[child.name] = child
        child.parent = self

    def attach_child(self, child, path):
        cur = self
        while path:
            sub_name = path.pop(0)
            if not sub_name in cur.children:
                cur.add_child(DirNode(sub_name))

            cur = cur.children[sub_name]

        cur.add_child(child)

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


class FileNode(VNode):
    pass


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

        # also add refs
        for ref_name in self.repo.refs.allkeys():
            components = ref_name.split('/')
            try:
                ref_sha = self.repo.refs[ref_name]
            except KeyError:
                warn('%r not found in %r' % (ref_name, self.repo))
            else:
                ref_node = GitRefNode(components[-1],
                                      self.repo,
                                      ref_sha,
                                      os.path.join(
                                          self.path, 'commits', ref_sha
                                      ))
                self.attach_child(ref_node, components[:-1])

        commits = DirNode('commits')
        for commit in  filter(lambda obj: obj.type_name == 'commit',
                             (self.repo[sha] for sha in
                                             self.repo.object_store)):
            commits.add_child(GitCommitNode(commit.id, self.repo, commit.id))

        self.add_child(commits)


class GitCommitNode(VirtualDirNode):
    primary = True

    def __init__(self, name, repo, commit):
        super(GitCommitNode, self).__init__(name)
        self.repo = repo
        self.commit_sha = commit

    def fuse_getattr(self, path):
        if self.path == path:
            return super(GitCommitNode, self).fuse_getattr(path)

        try:
            mode, blob = self._get_object(path)
        except KeyError:
            return -errno.ENOENT

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
        for de in super(GitCommitNode, self).fuse_readdir(path, offset):
            yield de

        mode, tree = self._get_object(path)

        for mode, path, sha in tree.entries():
            yield fuse.Direntry(path)

        # FIXME: symbolic links!
        # "supported": O_NOATIME, O_NOCTTY, O_NOFOLLOW, O_SYNC, O_ASYNC

    def fuse_release(self, path, flags):
        return 0  # always succeed

    @property
    def commit(self):
        if not hasattr(self, '_commit'):
            self._load()

        return self._commit

    @property
    def tree(self):
        if not hasattr(self, '_tree'):
            self._load()

        return self._tree

    def _load(self):
        if not hasattr(self, 'commit'):
            self._commit = self.repo[self.commit_sha]
            self._tree = self.repo[self.commit.tree]

    def _get_object(self, path):
        rel_path = self._get_rel_path(path)
        if '.' == rel_path:
            return stat.S_IFDIR | 0755, self.tree  # FIXME: mode?
        mode, sha = self.tree.lookup_path(
            self.repo.__getitem__, rel_path
        )
        return mode, self.repo[sha]


class GitRefNode(FileNode):
    primary = True

    def __init__(self, name, repo, sha, target_path):
        super(GitRefNode, self).__init__(name)
        self.repo = repo
        self.sha = sha
        self.target_path = target_path

    def fuse_getattr(self, path):
        s = fuse.Stat(
            st_mode=stat.S_IFLNK | 0777,
            st_ino=0,
            st_dev=0,
            st_nlink=1,
            st_uid=0,  # FIXME
            st_gid=0,  # FIXME,
            st_size=4096,
            st_atime=0,  # FIXME
            st_mtime=0,  # FIXME,
            st_ctime=0,  # FIXME
        )
        return s

    def fuse_readlink(self, path):
        return os.path.relpath(self.target_path, self.parent.path)



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
            print "called %s(%r, %r, %r), endpoint %s" % (
                name, path, args, kwargs, endpoint)
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
