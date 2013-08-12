from struct import calcsize, pack, unpack
from array import array
from cStringIO import StringIO
from contextlib import closing, nested

# @UTF Table Constants Definition (From utf_table)
# Suspect that "type 2" is signed
COLUMN_STORAGE_MASK       = 0xf0
COLUMN_STORAGE_PERROW     = 0x50
COLUMN_STORAGE_CONSTANT   = 0x30
COLUMN_STORAGE_ZERO       = 0x10
COLUMN_TYPE_MASK          = 0x0f
COLUMN_TYPE_DATA          = 0x0b
COLUMN_TYPE_STRING        = 0x0a
# COLUMN_TYPE_FLOAT2      = 0x09 ?
# COLUMN_TYPE_DOUBLE      = 0x09 ?
COLUMN_TYPE_FLOAT         = 0x08
# COLUMN_TYPE_8BYTE2      = 0x07 ?
COLUMN_TYPE_8BYTE         = 0x06
COLUMN_TYPE_4BYTE2        = 0x05
COLUMN_TYPE_4BYTE         = 0x04
COLUMN_TYPE_2BYTE2        = 0x03
COLUMN_TYPE_2BYTE         = 0x02
COLUMN_TYPE_1BYTE2        = 0x01
COLUMN_TYPE_1BYTE         = 0x00

COLUMN_TYPE_MAP = {
    COLUMN_TYPE_DATA    : '>LL',
    COLUMN_TYPE_STRING  : '>L',
    COLUMN_TYPE_FLOAT   : '>f',
    COLUMN_TYPE_8BYTE   : '>Q',
    COLUMN_TYPE_4BYTE2  : '>l',
    COLUMN_TYPE_4BYTE   : '>L',
    COLUMN_TYPE_2BYTE2  : '>h',
    COLUMN_TYPE_2BYTE   : '>H',
    COLUMN_TYPE_1BYTE2  : '>b',
    COLUMN_TYPE_1BYTE   : '>B',
}

def UTFChiper(data, c=0x5f, m=0x15):
    """Chiper for @UTF Table"""

    v = array('B', data)
    for i in xrange(len(v)):
        v[i] = v[i] ^ c & 0b11111111
        c = c * m & 0b11111111
    return (c, m, v.tostring())

class UTFTableIO:

    def __init__(s, istream=None, ostream=None, encrypted=False, key=(0x5f, 0x15)):
        s.istream = istream
        s.ostream = ostream
        s._istart = 0
        s._ostart = 0
        s.encrypted = encrypted

        if s.encrypted:
            # key used for encrypt
            (s.ikeyc, s.ikeym) = key
            (s.okeyc, s.okeym) = key

    def read(s, fmt=None, n=-1):
        if int == type(fmt):
            fmt = None
            n = fmt
        if fmt:
            return unpack(fmt, s.read(calcsize(fmt)))
        else:
            data = s.istream.read(n)
            if s.encrypted:
                (s.ikeyc, s.ikeym, data) = UTFChiper(data, s.ikeyc, s.ikeym)
            return data

    def write(s, b, fmt=None):
        if fmt:
            return s.write(pack(fmt, *b))
        else:
            if s.encrypted:
                (s.okeyc, s.okeym, b) = UTFChiper(b, s.okeyc, s.okeym)
            return s.ostream.write(b)

    def istart(s):
        return s._istart = s.istream.tell()

    def ostart(s):
        return s._ostart = s.ostream.tell()

    def itell(s):
        return s.istream.tell() - s._istart

    def otell(s):
        return s.ostream.tell() - s._ostart

class AttributeDict(dict): 
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__

class StringTable:
    """@UTF Table String Table"""

    def __init__(s):
        s.bytecounter = 0
        s.entry = []
        s.__map_stoo = {}
        s.__map_otos = {}
    
    @classmethod
    def parse(cls, data):
        s = cls();
        init = data.strip('\x00').split('\x00')
        for entry in init:
            s.__getitem__(entry)    # Simply invoke __getitem__
        return s;

    def __getitem__(s, key):
        """string in offset out; offset in string out"""
        if type(key) == str:
            if s.__map_stoo.has_key(key):
                return s.__map_stoo[key]
            else:
                s.entry.append(key);
                s.__map_otos[s.bytecounter] = key
                s.__map_stoo[key] = s.bytecounter
                s.bytecounter += len(key) + 1 # For \x00 byte
                return s[key];
        else:
            # What if queried offset does not exists?
            return s.__map_otos[key]

    def dump(s, io):
        return io.write('\x00'.join(s.entry) + '\x00')

class Column:
    """@UTF Table Column"""

    STRUCT_SCHEMA_DEF = '>BL'

    def __init__(s, utf):
        s.utf = utf

    @classmethod
    def parse(cls, utf, io):
        s = cls(utf)

        (typeid, s.nameoffset) = io.read(STRUCT_SCHEMA_DEF);

        s.storagetype = typeid & COLUMN_STORAGE_MASK
        s.fieldtype = typeid & COLUMN_TYPE_MASK

        if s.feature(COLUMN_STORAGE_CONSTANT):
            pattern = COLUMN_TYPE_MAP[s.fieldtype]
            if not pattern:
                raise Exception("Unknown Type 0x%02x" % s.fieldtype)
            col_data = io.read(pattern)
            s.const = col_data

        return s;

    def value(s, io):
        val = None
        if s.feature(COLUMN_STORAGE_CONSTANT):
            val = s.const
        elif s.feature(COLUMN_STORAGE_ZERO):
            val = ()
        elif s.feature(COLUMN_STORAGE_PERROW):
            pattern = COLUMN_TYPE_MAP[s.fieldtype]
            if not pattern:
                raise Exception("Unknown Type 0x%02x" % s.fieldtype)
            val = io.read(pattern)
        # if s.feature(COLUMN_TYPE_STRING):
        #     val = (utf.getstring(f, col_data[0]), col_data[0])
        return val

    def feature(s, typeid):
        if type(typeid) == list:
            return s.storagetype in typeid or s.fieldtype in typeid or s.typeid in typeid
        else:
            return s.storagetype == typeid or s.fieldtype == typeid or s.typeid == typeid

    def dump(s, io):
        typeid = s.storagetype | s.fieldtype
        return io.write((typeid, s.nameoffset), fmt=STRUCT_SCHEMA_DEF)

class Row(AttributeDict):
    """@UTF Table Data Row (Mutable)"""

    def __init__(s, utf):
        pass

    @classmethod
    def parse(cls, utf, data):
        pass


    def dump(s, io):
        pass

class UTFTable:
    """@UTF Table Structure"""

    STRUCT_UTF_HEADER = '>4sL'
    STRUCT_CONTENT_HEADER = '>LLLLHHL'

    def __init__(s):
        s.string_table = None
        s.rows = []
        s.cols = []

    @classmethod
    def parse(cls, f):
        s = cls();

        # @UTF Header Validation
        marker = f.read(4)
        if marker == '\x1F\x9E\xF3\xF5':
            s.encrypted = True
        else if marker == '@UTF':
            s.encrypted = False
        else:
            raise Exception("Invalid UTF Table Marker")
        f.seek(-4, 1);

        # IO Wrapper
        io = s.io = UTFTableIO(f, encrypted=s.encrypted)

        # @UTF Headers
        (
                s.marker, 
                s.table_size, 
        ) = io.read(STRUCT_UTF_HEADER)

        assert s.marker == '@UTF'

        # assert len(table_content) == s.table_size

        # Setup start flag for new section
        io.istart()

        # Table Headers
        (
                s.rows_offset, 
                s.string_table_offset, 
                s.data_offset, # always == s.table_size
                s.table_name_string, 
                s.column_length, 
                s.row_width, 
                s.row_length
        ) = io.read(STRUCT_CONTENT_HEADER)

        assert s.data_offset == s.table_size

        ## Columns

        while len(s.cols) < s.column_length:
            s.cols.append(Column.parse(s, io));

        assert io.itell() == s.rows_offset

        ## Rows

        while len(s.rows) < s.row_length:
            s.rows.append(Row.parse(s, io));

        assert io.itell() == s.string_table_offset

        ## String Table

        string_table_sz = s.table_size - s.string_table_offset

        s.string_table = StringTable.parse(io.read(string_table_sz))

        assert io.itell() == s.data_offset

        return s

    def dump(s, io):
        pass

