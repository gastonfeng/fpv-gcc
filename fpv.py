"""
This file is part of fpv-gcc
See the COPYING, README, and INSTALL files for more information

"""

from __future__ import with_statement
import re
import logging

from gccMemoryMap import GCCMemoryMap, MemoryRegion

logging.basicConfig(level=logging.DEBUG)

# Processor Globals (Create a better way to deal with this)


def reinitialize_states():
    global state
    global IDEP_STATE
    global idep_archive
    global COMSYM_STATE
    global comsym_name
    global LINKERMAP_STATE
    global linkermap_section
    global linkermap_symbol
    global linkermap_lastsymbol

    global idep_archives
    global idep_symbols
    global common_symbols
    global memory_regions
    global memory_map
    global loaded_files
    global linker_defined_addresses

    state = 'START'

    IDEP_STATE = 'START'
    idep_archive = None
    COMSYM_STATE = 'NORMAL'
    comsym_name = None
    LINKERMAP_STATE = 'NORMAL'
    linkermap_section = None
    linkermap_symbol = None
    linkermap_lastsymbol = None

    idep_archives = []
    idep_symbols = []
    common_symbols = []
    memory_regions = []

    loaded_files = []
    linker_defined_addresses = []
    memory_map = GCCMemoryMap()


# Regular Expressions
re_headings = {'IN_DEPENDENCIES': re.compile("Archive member included because of file \(symbol\)"),
               'IN_COMMON_SYMBOLS': re.compile("Allocating common symbols"),
               'IN_DISCARDED_INPUT_SECTIONS': re.compile("Discarded input sections"),
               'IN_MEMORY_CONFIGURATION': re.compile("Memory Configuration"),
               'IN_LINKER_SCRIPT_AND_MEMMAP': re.compile("Linker script and memory map")}

re_b1_archive = re.compile(ur'^(?P<folder>.*/)?(?P<archive>:|(.+?)(?:(\.[^.]*)))\((?P<symbol>.*)\)$')
re_b1_file = re.compile(ur'^\s+(?P<folder>.*/)?(?P<file>:|(.+?)(?:(\.[^.]*)))\((?P<symbol>.*)\)$')

re_comsym_normal = re.compile(ur'^(?P<symbol>\S*)\s+(?P<size>0[xX][0-9a-fA-F]+)\s+(?P<filefolder>.*/)?(?P<archivefile>:|.+?(?:\.[^.]*))\((?P<objfile>.*)\)$')
re_comsym_nameonly = re.compile(ur'^(?P<symbol>\S*)$')
re_comsym_detailonly = re.compile(ur'^\s+(?P<size>0[xX][0-9a-fA-F]+)\s+(?P<filefolder>.*/)?(?P<archivefile>:|.+?(?:\.[^.]*))\((?P<objfile>.*)\)$')

re_sectionelem = re.compile(ur'^(?P<treepath>\.\S*)\s+(?P<address>0[xX][0-9a-fA-F]+)\s+(?P<size>0[xX][0-9a-fA-F]+)\s+(?P<filefolder>.*/)?(?P<archivefile>:|.+?(?:\.[^.]*))\((?P<objfile>.*)\)$')
re_sectionelem_nameonly = re.compile(ur'^(?P<symbol>\.\S*)$')
re_sectionelem_detailonly = re.compile(ur'^\s+(?P<address>0[xX][0-9a-fA-F]+)\s+(?P<size>0[xX][0-9a-fA-F]+)\s+(?P<filefolder>.*/)?(?P<archivefile>:|.+?(?:\.[^.]*))\((?P<objfile>.*)\)$')

re_memregion = re.compile(ur'^(?P<region>\S*)\s+(?P<origin>0[xX][0-9a-fA-F]+)\s+(?P<size>0[xX][0-9a-fA-F]+)\s*(?P<attribs>\S*)$')

re_linkermap = {}
re_linkermap['LOAD'] = re.compile(ur'^LOAD\s+(?P<filefolder>.*/)?(?P<file>:|.+?(?:\.[^.]*))$')
re_linkermap['DEFN_ADDR'] = re.compile(ur'^\s+(?P<origin>0[xX][0-9a-fA-F]+)\s+(?P<name>.*)\s=\s+(?P<defn>0[xX][0-9a-fA-F]+)$')
re_linkermap['SECTION_HEADINGS'] = re.compile(ur'^(?P<name>[._]\S*)(?:\s+(?P<address>0[xX][0-9a-fA-F]+))?(?:\s+(?P<size>0[xX][0-9a-fA-F]+))?(?:\s+load address\s+(?P<loadaddress>0[xX][0-9a-fA-F]+))?$')
re_linkermap['SYMBOL'] = re.compile(ur'^\s(?P<name>\S+)(?:\s+(?P<address>0[xX][0-9a-fA-F]+))(?:\s+(?P<size>0[xX][0-9a-fA-F]+))\s+(?P<filefolder>.*/)?(?P<file>:|.+?(?:\.[^.\)]*))?(?:\((?P<file2>\S*)\))?$')
re_linkermap['FILL'] = re.compile(ur'^\s(?:\*fill\*)(?:\s+(?P<address>0[xX][0-9a-fA-F]+))(?:\s+(?P<size>0[xX][0-9a-fA-F]+))$')
re_linkermap['SYMBOLONLY'] = re.compile(ur'^\s(?P<name>[._]\S+)$')
re_linkermap['SYMBOLDETAIL'] = re.compile(ur'^\s+(?:\s+(?P<address>0[xX][0-9a-fA-F]+))(?:\s+(?P<size>0[xX][0-9a-fA-F]+))\s+(?P<filefolder>.*/)?(?P<file>:|.+?(?:\.[^.\)]*))?(?:\((?P<file2>\S*)\))?$')
re_linkermap['SECTIONDETAIL'] = re.compile(ur'^\s+(?:\s+(?P<address>0[xX][0-9a-fA-F]+))(?:\s+(?P<size>0[xX][0-9a-fA-F]+))$')
re_linkermap['SECTIONHEADINGONLY'] = re.compile(ur'^(?P<name>[._]\S+)$')


def check_line_for_heading(l):
    for key, regex in re_headings.iteritems():
        if regex.match(l):
            logging.info("Entering File Region : " + key)
            return key
    return None


class IDLArchive(object):
    # Rough draft. Needs much work to make it usable
    def __init__(self, folder, archive, objfile):
        self.folder = folder
        self.archive = archive
        self.objfile = objfile
        self.becauseof = None

    def __repr__(self):
        r = "\n\nAchive in Dependencies : \n"
        r += self.archive + "\n"
        r += self.objfile + "\n"
        r += self.folder + "\n"
        r += repr(self.becauseof)
        return r


class IDLSymbol(object):
    # Rough draft. Needs much work to make it usable
    def __init__(self, folder, objfile, symbol):
        self.folder = folder
        self.objfile = objfile
        self.symbol = symbol

    def __repr__(self):
        r = "Because of :: \n"
        r += self.symbol + "\n"
        r += self.objfile + "\n"
        r += self.folder + "\n"
        return r


def process_dependencies_line(l):
    # Rough draft. Needs much work to make it usable
    global IDEP_STATE
    global idep_archive
    if IDEP_STATE == 'START':
        res = re_b1_archive.findall(l)
        if len(res) and len(res[0]) == 5:
            archive = IDLArchive(res[0][1], res[0][1], res[0][4])
            idep_archives.append(archive)
            IDEP_STATE = 'ARCHIVE_DEFINED'
            idep_archive = archive
    if IDEP_STATE == 'ARCHIVE_DEFINED':
        res = re_b1_file.findall(l)
        if len(res) and len(res[0]) == 5:
            symbol = IDLSymbol(res[0][1], res[0][1], res[0][4])
            idep_symbols.append(symbol)
            IDEP_STATE = 'START'
            idep_archive.becauseof = symbol


class CommonSymbol(object):
    def __init__(self, symbol, size, filefolder, archivefile, objfile):
        self.symbol = symbol
        self.size = int(size, 16)
        self.filefolder = filefolder
        self.archivefile = archivefile
        self.objfile = objfile

    def __repr__(self):
        # Make this cleaner
        r = "\n\nCommon Symbol :: \n"
        r += self.symbol + "\n"
        r += str(self.size) + " bytes\n"
        r += self.filefolder + "\n"
        r += self.archivefile + "\n"
        r += self.objfile + "\n"
        return r


def process_common_symbols_line(l):
    global COMSYM_STATE
    global comsym_name
    if COMSYM_STATE == 'NORMAL':
        res = re_comsym_normal.findall(l)
        if len(res) and len(res[0]) == 5:
            sym = CommonSymbol(res[0][0], res[0][1], res[0][2], res[0][3], res[0][4])
            common_symbols.append(sym)
        else:
            res = re_comsym_nameonly.findall(l)
            if len(res) == 1:
                comsym_name = res[0]
                COMSYM_STATE = 'GOT_NAME'
    elif COMSYM_STATE == 'GOT_NAME':
        res = re_comsym_detailonly.findall(l)
        if len(res) and len(res[0]) == 4:
            sym = CommonSymbol(comsym_name, res[0][0], res[0][1], res[0][2], res[0][3])
            common_symbols.append(sym)
            COMSYM_STATE = 'NORMAL'


def process_discarded_input_section_line(l):
    pass


def process_memory_configuration_line(l):
    res = re_memregion.findall(l)
    if len(res) and len(res[0]) == 4:
        region = MemoryRegion(res[0][0], res[0][1], res[0][2], res[0][3])
        memory_regions.append(region)
        import gccMemoryMap
        gccMemoryMap.memory_regions = memory_regions


def process_linkermap_load_line(l):
    res = re_linkermap['LOAD'].findall(l)
    if len(res) and len(res[0]) == 2:
        loaded_files.append((res[0][0] + res[0][1]).strip())


class LinkerDefnAddr(object):
    def __init__(self, symbol, address, defn_addr):
        self.symbol = symbol
        self.address = int(address, 16)
        self.defn_addr = int(defn_addr, 16)

    def __repr__(self):
        r = self.symbol
        r += " :: " + hex(self.address)
        return r


def process_linkermap_defn_addr_line(l):
    res = re_linkermap['DEFN_ADDR'].findall(l)
    if len(res) and len(res[0]) == 3:
        linker_defined_addresses.append(LinkerDefnAddr(res[0][1], res[0][0], res[0][2]))


def process_linkermap_section_headings_line(l):
    match = re_linkermap['SECTION_HEADINGS'].match(l)
    name = match.group('name').strip()
    if name.startswith('_'):
        name = ('.' + name).strip()
    newnode = memory_map.get_node(name, create=True)
    if match.group('address') is not None:
        newnode.address = match.group('address').strip()
    if match.group('size') is not None:
        newnode.defsize = match.group('size').strip()
    global linkermap_section
    global LINKERMAP_STATE
    if match.group('address') is not None:
        linkermap_section = newnode
        LINKERMAP_STATE = 'IN_SECTION'
    else:
        linkermap_section = newnode
        LINKERMAP_STATE = 'GOT_SECTION_NAME'


def process_linkermap_section_heading_detail_line(l):
    match = re_linkermap['SECTIONDETAIL'].match(l)
    newnode = linkermap_section
    if match:
        if match.group('address') is not None:
            newnode.address = match.group('address').strip()
        if match.group('size') is not None:
            newnode.defsize = match.group('size').strip()
    global linkermap_section
    global LINKERMAP_STATE
    LINKERMAP_STATE = 'IN_SECTION'


def process_linkermap_symbol_line(l):
    global linkermap_symbol
    if linkermap_symbol is not None:
        logging.warn("Probably Missed Symbol Detail : " + linkermap_symbol)
        linkermap_symbol = None
    match = re_linkermap['SYMBOL'].match(l)
    name = match.group('name').strip()
    if name.startswith('COMMON'):
        name = '.' + name
    if name.startswith('_'):
        name = '.' + name
    if not name.startswith('.'):
        print 'Skipping :' + l.rstrip()
        return
    if not name.startswith(linkermap_section.gident):
        logging.warn("Possibly mismatched section : " + name + " ; " + linkermap_section.gident)
        name = linkermap_section.gident + name
    arfile = None
    objfile = None
    arfolder = None
    if match.group('file2') is not None:
        arfile = match.group('file').strip()
        objfile = match.group('file2').strip()
        if match.group('filefolder') is not None:
            arfolder = match.group('filefolder').strip()
    elif match.group('file') is not None:
        objfile = match.group('file').strip()
        if match.group('filefolder') is not None:
            arfolder = match.group('filefolder').strip()
    if len(name.split('.')) == 2 or name.startswith('.bss.COMMON') or name.startswith('.MSP430.attributes'):
        disambig = objfile.replace('.', '_')
        try:
            name = name + '.' + disambig
        except TypeError:
            print name, objfile
            raise TypeError
    newnode = memory_map.get_node(name, create=True)
    if arfile is not None:
        newnode.arfile = arfile
    if objfile is not None:
        newnode.objfile = objfile
    if arfolder is not None:
        newnode.arfolder = arfolder
    if match.group('address') is not None:
        newnode.address = match.group('address').strip()
    if match.group('size') is not None:
        newnode.osize = match.group('size').strip()
    global linkermap_lastsymbol
    linkermap_lastsymbol = newnode


def process_linkermap_fill_line(l):
    global linkermap_symbol
    if linkermap_symbol is not None:
        logging.warn("Probably Missed Symbol Detail : " + linkermap_symbol)
        linkermap_symbol = None

    if linkermap_lastsymbol is None or linkermap_symbol is not None:
        logging.warn("Fill Container Unknown : ", l)
        return
    match = re_linkermap['FILL'].match(l)
    if match.group('size') is not None:
        linkermap_lastsymbol.fillsize = int(match.group('size').strip(), 16)


def process_linkermap_symbolonly_line(l):
    global linkermap_symbol
    if linkermap_symbol is not None:
        logging.warn("Probably Missed Symbol Detail : " + linkermap_symbol)
        linkermap_symbol = None
    match = re_linkermap['SYMBOLONLY'].match(l)
    name = match.group('name').strip()
    if name.startswith('COMMON'):
        name = '.' + name
    if name.startswith('_'):
        name = '.' + name
    if not name.startswith('.'):
        print 'Skipping :' + l.rstrip()
        return
    if not name.startswith(linkermap_section.gident):
        if name != linkermap_section.gident:
            logging.warn("Possibly mismatched section : " + name + " ; " + linkermap_section.gident)
            name = linkermap_section.gident + name
    # print "Waiting for : " + name
    linkermap_symbol = name


def process_linkermap_section_detail_line(l):
    global linkermap_symbol
    match = re_linkermap['SYMBOLDETAIL'].match(l)
    name = linkermap_symbol
    if name.startswith('COMMON'):
        name = '.' + name.strip()
        print name
    if name.startswith('_'):
        name = '.' + name.strip()
    if not name.startswith('.'):
        print 'Skipping :' + l.rstrip()
        return
    if not name.startswith(linkermap_section.gident):
        logging.warn("Possibly mismatched section : " + name + " ; " + linkermap_section.gident)
        name = linkermap_section.gident + name
    arfile = None
    objfile = None
    arfolder = None
    if match.group('file2') is not None:
        arfile = match.group('file').strip()
        objfile = match.group('file2').strip()
        if match.group('filefolder') is not None:
            arfolder = match.group('filefolder').strip()
    elif match.group('file') is not None:
        objfile = match.group('file').strip()
        if match.group('filefolder') is not None:
            arfolder = match.group('filefolder').strip()
    if len(name.split('.')) == 2 or name.startswith('.bss.COMMON') or name.startswith('.MSP430.attributes'):
        disambig = objfile.replace('.', '_')
        try:
            name = name + '.' + disambig
        except TypeError:
            print name, objfile
            raise TypeError
    newnode = memory_map.get_node(name, create=True)
    if arfile is not None:
        newnode.arfile = arfile
    if objfile is not None:
        newnode.objfile = objfile
    if arfolder is not None:
        newnode.arfolder = arfolder
    if match.group('address') is not None:
        newnode.address = match.group('address').strip()
    if match.group('size') is not None:
        newnode.osize = match.group('size').strip()
    global linkermap_lastsymbol
    linkermap_lastsymbol = newnode
    linkermap_symbol = None


def process_linkermap_line(l):
    if LINKERMAP_STATE == 'GOT_SECTION_NAME':
        process_linkermap_section_heading_detail_line(l)
    elif LINKERMAP_STATE == 'NORMAL':
        for key, regex in re_linkermap.iteritems():
            if regex.match(l):
                if key == 'LOAD':
                    process_linkermap_load_line(l)
                    return
                if key == 'DEFN_ADDR':
                    process_linkermap_defn_addr_line(l)
                    return
                if key == 'SECTION_HEADINGS':
                    process_linkermap_section_headings_line(l)
                    return
                print "Unhandled line : " + l.strip()
    elif LINKERMAP_STATE == 'IN_SECTION':
        if linkermap_symbol is not None:
            if re_linkermap['SYMBOLDETAIL'].match(l):
                process_linkermap_section_detail_line(l)
                return
        if re_linkermap['SECTION_HEADINGS'].match(l):
            process_linkermap_section_headings_line(l)
            return
        if re_linkermap['FILL'].match(l):
            process_linkermap_fill_line(l)
            return
        if re_linkermap['SYMBOL'].match(l):
            process_linkermap_symbol_line(l)
            return
        if re_linkermap['SYMBOLONLY'].match(l):
            process_linkermap_symbolonly_line(l)
            return
    return None


def process_map_file(fname):
    reinitialize_states()
    with open(fname) as f:
        for line in f:
            rval = check_line_for_heading(line)
            if rval is not None:
                state = rval
            else:
                if state == 'IN_DEPENDENCIES':
                    process_dependencies_line(line)
                elif state == 'IN_COMMON_SYMBOLS':
                    process_common_symbols_line(line)
                elif state == 'IN_DISCARDED_INPUT_SECTIONS':
                    process_discarded_input_section_line(line)
                elif state == 'IN_MEMORY_CONFIGURATION':
                    process_memory_configuration_line(line)
                elif state == 'IN_LINKER_SCRIPT_AND_MEMMAP':
                    process_linkermap_line(line)
    return memory_map

if __name__ == '__main__':
    process_map_file('avrcpp.map')
