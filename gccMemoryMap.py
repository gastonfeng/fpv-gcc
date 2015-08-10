
# Copyright (C) 2015 Quazar Technologies Pvt. Ltd.
#               2015 Chintalagiri Shashank
#
# This file is part of fpv-gcc.
#
# fpv-gcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# fpv-gcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with fpv-gcc.  If not, see <http://www.gnu.org/licenses/>.


import logging
from ntreeSize import SizeNTree, SizeNTreeNode

memory_regions = None


class LinkAliases(object):
    def __init__(self):
        self._aliases = {}

    def register_alias(self, target, alias):
        if alias in self._aliases.keys():
            if target != self._aliases[alias]:
                logging.warn("Alias Collision : " + alias + ' :: ' + target + '; ' + self._aliases[alias])
        else:
            self._aliases[alias] = target

    def encode(self, name):
        for key in self._aliases.keys():
            if name.startswith(key):
                # if alias.startswith(linkermap_section.gident):
                # alias = alias[len(linkermap_section.gident):]
                return self._aliases[key] + name
        return name


aliases = LinkAliases()


class GCCMemoryMapNode(SizeNTreeNode):
    def __init__(self, parent=None, node_t=None,
                 name=None, address=None, size=None, fillsize=None,
                 arfile=None, objfile=None, arfolder=None):
        super(GCCMemoryMapNode, self).__init__(parent, node_t)
        self._leaf_property = '_size'
        self._ident_property = 'name'
        self._size = None
        if name is None:
            if objfile is not None:
                name = objfile
            else:
                name = ""
        self.name = name
        if address is not None:
            self._address = int(address, 16)
        else:
            self._address = None
        if size is not None:
            self._defsize = int(size, 16)
        else:
            self._defsize = None
        self.arfolder = arfolder
        self.arfile = arfile
        self.objfile = objfile
        self.fillsize = fillsize

    @property
    def address(self):
        if self._address is not None:
            return format(self._address, '#010x')
        else:
            return ""

    @address.setter
    def address(self, value):
        self._address = int(value, 16)

    @property
    def defsize(self):
        return self._defsize

    @defsize.setter
    def defsize(self, value):
        self._defsize = int(value, 16)

    @property
    def osize(self):
        return self._size

    @osize.setter
    def osize(self, value):
        if len(self.children):
            logging.warn("Setting leaf property at a node which has children : " + self.gident)
        newsize = int(value, 16)
        if self._size is not None:
            if newsize != self._size:
                logging.warn("Overwriting leaf property at node : " +
                             self.gident + ' :: ' + str(self._size) + '->' + str(newsize))
            else:
                logging.warn("Possibly missing leaf node with same name : " + self.gident)
        self._size = newsize

    def add_child(self, newchild=None, name=None,
                  address=None, size=None, fillsize=0,
                  arfile=None, objfile=None, arfolder=None):
        if newchild is None:
            nchild = GCCMemoryMapNode(name=name, address=None, size=None,
                                      fillsize=0, arfile=None, objfile=None,
                                      arfolder=None)
            newchild = super(GCCMemoryMapNode, self).add_child(nchild)
        else:
            newchild = super(GCCMemoryMapNode, self).add_child(newchild)
        return newchild

    def push_to_leaf(self):
        if not self.objfile:
            logging.warn("No objfile defined. Can't push to leaf : " + self.gident)
            return
        for child in self.children:
            if child.name == self.objfile.replace('.', '_'):
                return
        newleaf = self.add_child(name=self.objfile.replace('.', '_'))
        if self._defsize is not None:
            newleaf.defsize = hex(self._defsize)
        if self._address is not None:
            newleaf.address = hex(self._address)
        if self.fillsize is not None:
            newleaf.fillsize = self.fillsize
        if self.objfile is not None:
            newleaf.objfile = self.objfile
        if self.arfile is not None:
            newleaf.arfile = self.arfile
        if self.arfolder is not None:
            newleaf.arfolder = self.arfolder
        newleaf.osize = hex(self._size)
        return newleaf

    @property
    def leafsize(self):
        # if 'DISCARDED' in self.region:
        # return 0
        # if len(self.children) > 0:
        #     raise AttributeError
        if self.fillsize is not None:
            if self._size is not None:
                return self._size + self.fillsize
            else:
                return self.fillsize
        return self._size

    @leafsize.setter
    def leafsize(self, value):
        raise AttributeError

    @property
    def region(self):
        if self.parent is not None and self.parent.region == 'DISCARDED':
            return 'DISCARDED'
        if self._address is None:
            return 'UNDEF'
        # tla = self.get_top_level_ancestor
        # if tla is not None and tla is not self:
        # if tla.region == 'DISCARDED':
        # return 'DISCARDED TLA'
        if self._address == 0:
            return "DISCARDED"
        for region in memory_regions:
            if self._address in region:
                return region.name
        raise ValueError(self._address)

    def __repr__(self):
        r = '{0:.<60}{1:<15}{2:>10}{6:>10}{3:>10}    {5:<15}{4}'.format(self.gident, self.address or '',
                                                                        self.defsize or '', self.size or '',
                                                                        self.objfile or '', self.region,
                                                                        self._size or '')
        return r


class GCCMemoryMap(SizeNTree):
    def __init__(self):
        node_t = GCCMemoryMapNode
        super(GCCMemoryMap, self).__init__(node_t)

    @property
    def used_regions(self):
        ur = ['UNDEF']
        for node in self.root.all_nodes():
            if node.region not in ur:
                ur.append(node.region)
        ur.remove('UNDEF')
        ur.remove('DISCARDED')
        return ur

    @property
    def used_objfiles(self):
        of = []
        for node in self.root.all_nodes():
            if node.objfile is None and node.leafsize is not None \
                    and node.region not in ['DISCARDED', 'UNDEF']:
                logging.warn("Object unaccounted for : {0:<40} {1:<15} {2:>5}".format(node.gident, node.region,
                                                                                      str(node.leafsize)))
                continue
            if node.objfile not in of:
                of.append(node.objfile)
        return of

    @property
    def used_arfiles(self):
        af = []
        for node in self.root.all_nodes():
            if node.arfile is None and node.leafsize is not None \
                    and node.region not in ['DISCARDED', 'UNDEF']:
                logging.warn("Object unaccounted for : {0:<40} {1:<15} {2:>5}".format(node.gident, node.region,
                                                                                      str(node.leafsize)))
                continue
            if node.arfile not in af:
                af.append(node.arfile)
        return af

    @property
    def used_files(self):
        af = []
        of = []
        for node in self.root.all_nodes():
            if node.arfile is None and node.leafsize is not None \
                    and node.region not in ['DISCARDED', 'UNDEF']:
                if node.objfile is None and node.leafsize is not None \
                        and node.region not in ['DISCARDED', 'UNDEF']:
                    logging.warn("Object unaccounted for : {0:<40} {1:<15} {2:>5}".format(node.gident, node.region,
                                                                                          str(node.leafsize)))
                    continue
                else:
                    if node.objfile not in of:
                        of.append(node.objfile)
            if node.arfile not in af:
                af.append(node.arfile)
        if None in af:
            af.remove(None)
        if None in of:
            of.remove(None)
        return of, af

    @property
    def used_sections(self):
        sections = [node.gident for node in self.top_level_nodes if node.size > 0 and node.region not in ['DISCARDED', 'UNDEF']]
        sections += [node.gident for node in sum([n.children for n in self.top_level_nodes if n.region == 'UNDEF'], []) if node.region != 'DISCARDED' and node.size > 0]
        return sections

    @property
    def all_symbols(self):
        asym = []
        for node in self.root.all_nodes():
            if node.name not in asym:
                asym.append(node.name)
        return asym

    def get_objfile_fp(self, objfile):
        r = []
        for rgn in self.used_regions:
            r.append(self.get_objfile_fp_rgn(objfile, rgn))
        return r

    def get_objfile_fp_rgn(self, objfile, region):
        rv = 0
        for node in self.root.all_nodes():
            if node.objfile == objfile:
                if node.region == region:
                    if node.leafsize is not None:
                        rv += node.leafsize
        return rv

    def get_objfile_fp_secs(self, objfile):
        r = []
        for section in self.used_sections:
            r.append(self.get_objfile_fp_sec(objfile, section))
        return r

    def get_arfile_fp_secs(self, arfile):
        r = []
        for section in self.used_sections:
            r.append(self.get_arfile_fp_sec(arfile, section))
        return r

    def get_objfile_fp_sec(self, objfile, section):
        rv = 0
        for node in self.get_node(section).all_nodes():
            if node.objfile == objfile:
                if node.leafsize is not None:
                    rv += node.leafsize
        return rv

    def get_arfile_fp_sec(self, arfile, section):
        rv = 0
        for node in self.get_node(section).all_nodes():
            if node.arfile == arfile:
                if node.leafsize is not None:
                    rv += node.leafsize
        return rv

    def get_arfile_fp(self, arfile):
        r = []
        for rgn in self.used_regions:
            r.append(self.get_arfile_fp_rgn(arfile, rgn))
        return r

    def get_arfile_fp_rgn(self, arfile, region):
        rv = 0
        for node in self.root.all_nodes():
            if node.arfile == arfile:
                if node.region == region:
                    if node.leafsize is not None:
                        rv += node.leafsize
        return rv


class MemoryRegion(object):
    def __init__(self, name, origin, size, attribs):
        self.name = name
        self.origin = int(origin, 16)
        self.size = int(size, 16)
        self.attribs = attribs

    def __repr__(self):
        r = '{0:.<20}{1:>20}{2:>20}   {3:<20}'.format(self.name, format(self.origin, '#010x'),
                                                      self.size or '', self.attribs)
        return r

    def __contains__(self, value):
        if not isinstance(value, int):
            value = int(value, 16)
        if self.origin <= value < (self.origin + self.size):
            return True
        else:
            return False
