#!/usr/bin/env python
#   
# Copyright (c) 2002, Pontus Sköld (pont_elf@soua.net)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

#
# This code requires Python 1.6 or later.
#

"""Provide easy access to ELF

EVERYTHING IN HERE IS SUBJECT TO CHANGE"""

import struct

# Constant definitions

# File types (e_type)

ET_NONE = 0   # No file type
ET_REL = 1    # Relocatable file
ET_EXEC = 2   # Executable file
ET_DYN = 3    # Shared object file
ET_CORE = 4   # Core file
ET_LOPROC = 0xff00 # Processor specific
ET_HIPROC = 0xffff # Processor specific

# Machine types

EM_NONE = 0         # No machine
EM_M32 = 1          # AT&T WE32100 
EM_SPARC = 2        # SPARC
EM_386 = 3          # Intel 80386
EM_68K = 4          # Motorola 68000
EM_88K = 5          # Motorola 88000
EM_860 = 7          # Intel 860
EM_MIPS = 8         # MIPS RS3000

# Special section indexes

SHN_UNDEF = 0
SHN_LORESERVE = 0xff00
SHN_LOPROC = 0xff00
SHN_HIPROC = 0xff1f
SHN_ABS = 0xfff1
SHN_COMMON = 0xfff2
SHN_HIRESERVE = 0xffff

# Section types

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_HASH = 5
SHT_DYNAMIC = 6
SHT_NOTE = 7
SHT_NOBITS = 8
SHT_REL = 9
SHT_SHLIB = 10
SHT_DYNSYM = 11
SHT_LOPROC = 0x70000000
SHT_HIPROC = 0x7fffffff
SHT_LOUSER = 0x80000000
SHT_HIUSER = 0xffffffff

# Segment types

PT_NULL = 0
PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3
PT_NOTE = 4
PT_SHLIB = 5
PT_PHDR = 6
PT_LOPROC = 0x70000000
PT_LOPROC = 0x7fffffff


# Section attribute flags

SHF_WRITE = 1
SHF_ALLOC = 2
SHF_EXECINSTR = 4
SHF_MASKPROX = 0xf0000000


# Handle generic types in structs

StUChar = 0
StHalf = 1
StWrd = 2
StSWrd = 2
StAddr = 3
StOff = 4

# Identity structure

EI_NIDENT = 16
EI_CLASS = 4
EI_DATA = 5
EI_VERSION = 6

# Machine type

ELFCLASS32 = 1
ELFCLASS64 = 2

ELFDATA2LSB = 1
ELFDATA2MSB = 2


# Versions

EV_NONE = 0
EV_CURRENT = 1





class ELFerror( Exception ):
    "Generic error class"


    def __init__( self, s ):
        self.s = s

    def __str__( self ):
        return self.s


    

class ELFhandler:

    def __init__( self, fname = "" ):

        if not fname:
            raise ELFerror( "Must supply filename" )

        f = open( fname )

        e_ident = f.read( EI_NIDENT )

        if e_ident[0:4] != "\177ELF":
            raise ELFerror( "Not an ELF file" )

        ei_class = ord( e_ident[ EI_CLASS ] )        # Get arhcitecture size and endianess
        ei_data = ord( e_ident[ EI_DATA ] )

        if ei_class == 0 or ei_class > 2:
            ELFerror( "Invalid EI_CLASS" )

        if ei_data == 0 or ei_data > 2:
            ELFerror( "Invalid EI_DATA" )

        self.version = ord( e_ident[ EI_VERSION ] )

        if self.version != EV_CURRENT:       #
            ELFerror( "Can only work with current version!" )
            
        self.machineflags = ( ei_class, ei_data )
        
        self.e_type = self.getdata( f, StHalf )
        self.e_machine =  self.getdata( f, StHalf )
        self.e_version =  self.getdata( f, StWrd )
        self.e_entry =  self.getdata( f, StAddr )
        
        e_phoff =  self.getdata( f, StOff ) # Subject to be removed?
        e_shoff =  self.getdata( f, StOff )

        self.e_flags =  self.getdata( f, StWrd )
        
        self.e_ehsize = self.getdata( f, StHalf )

        e_phentsize = self.getdata( f, StHalf )
        e_phnum = self.getdata( f, StHalf )

        e_shentsize = self.getdata( f, StHalf )
        e_shnum = self.getdata( f, StHalf )

        e_shstrndx = self.getdata( f, StHalf )

        self.sections = []
        self.progs = []

        if e_shoff:       # Any section headers to read?
            for p in range( e_shnum ): # p =  0 .. e_shnum 
                f.seek( e_shoff + e_shentsize * p ) # Find the start of this entry
                self.getsection( f )

        if e_phoff:       # Any rogram headers?
            for p in range( e_phnum ): # p =  0 .. e_shnum 
                f.seek( e_phoff + e_phentsize * p ) # Find the start of this entry
                self.getprog( f )


        self.sections[e_shstrndx]['is_shstr'] = 1 # Signal which is string table
        f.close()


    def write_elf( self, fname ):
        f = open( fname, "w" )

        secthead = ( StWrd, StWrd, StWrd, StAddr, StOff, StWrd, StWrd, StWrd, StWrd, StWrd )
        proghead = ( StWrd, StOff, StAddr, StAddr, StWrd, StWrd, StWrd, StWrd )
        elfhead = ( StHalf, StHalf, StWrd, StAddr, StOff, StOff, StWrd, StHalf, StHalf, StHalf, StHalf, StHalf, StHalf )

        e_shentsize = self.calclen( secthead )
        e_phentsize = self.calclen( proghead )

        e_phnum = len( self.progs )
        e_shnum = len( self.sections )

        start_offset = EI_NIDENT # System independent

        sh_offset = start_offset + self.calclen( elfhead )  # Calculate start of section headers
        ph_offset = sh_offset + e_shentsize * e_shnum

        image_offset = ph_offset + e_phentsize * e_phnum

        e_ehsize = sh_offset    # Header size = sh_offset
        
        # First we take all the sections and following them are the programs

        sect_offs = []
        prog_offs = []

        sect_pad = []
        prog_pad = []
        
        cur_offset = image_offset                 # Current offset


        print sh_offset
        print ph_offset
        print image_offset
        
        for p in self.sections:
            sect_offs.append( cur_offset )

            if p['sh_type'] != SHT_NOBITS:
                cur_offset = cur_offset + len( p['image'] )

            pad = 0
            if cur_offset % 4 != 0:
                pad = 4 - (cur_offset % 4)
                cur_offset = cur_offset + pad
            sect_pad.append( pad )
            
        for p in self.progs:
            pad = 0
            if p['p_type'] != PT_PHDR:          # Header table itself?
                prog_offs.append( ph_offset )

            else:
                prog_offs.append( cur_offset )
                cur_offset = cur_offset + len( p['image'] )

            
                if cur_offset % 4 != 0:
                    pad = 4 - (cur_offset % 4)
                    cur_offset = cur_offset + pad
            prog_pad.append( pad )
            

        if not self.sections:  # No sections?
            sh_offset = 0      # This is safe to nuke now

        if not self.progs:     # No progs?
            ph_offset = 0      # Safe to nuke now
        
        e_shstrndx = SHN_UNDEF

        if self.sections: # Any sections remaining
            for p in range( e_shnum ):  # For all valid indexes
                if self.sections[p]['is_shstr']:   # This is the string section?
                    e_shstrndx = p                 # Mark it



        f.write( "\177ELF" )
        ei_class = chr( self.machineflags[0] )
        ei_data = chr( self.machineflags[1] )
        ei_version = chr( self.version )

        f.write( "%s%s%s" % ( ei_class, ei_data, ei_version ) )

        f.write( chr( 0 ) * 9 )  # Padding

        self.putdata( f, StHalf, self.e_type )
        self.putdata( f, StHalf, self.e_machine)
        self.putdata( f, StWrd, self.e_version )
        self.putdata( f, StAddr, self.e_entry )
        self.putdata( f, StOff, ph_offset )
        self.putdata( f, StOff, sh_offset )
        self.putdata( f, StWrd, self.e_flags )
        self.putdata( f, StHalf, e_ehsize )
        self.putdata( f, StHalf, e_phentsize )
        self.putdata( f, StHalf, e_phnum )
        self.putdata( f, StHalf, e_shentsize )
        self.putdata( f, StHalf, e_shnum )
        self.putdata( f, StHalf, e_shstrndx )

        if e_shnum:
            for p in range( e_shnum ):
                self.putsection( f, self.sections[p], sect_offs[p] ) # Pass the dictionary and the offset as parameters

        if e_phnum:
            for p in range( e_phnum ):
                self.putprog( f, self.progs[p], prog_offs[p] ) # Pass the dictionary and the offset as parameters

        if e_shnum:
            for p in range( e_shnum ):
                if self.sections[p]['sh_type'] != SHT_NOBITS:
                    f.write( self.sections[p]['image'] )
                if sect_pad[p]:
                    f.write( chr(0) * sect_pad[p] )

        if e_phnum:
            for p in range( e_phnum ):
                if self.progs[p]['p_type'] != PT_PHDR:         # Don't write PT_PHDR segment
                    f.write( self.progs[p]['image'] )

                    if prog_pad[p]:
                        f.write( chr(0) * prog_pad[p] )
        
        f.close()


    def getsection( self, f ):
        thissect = {}

        thissect['sh_name'] = self.getdata( f, StWrd )
        thissect['sh_type'] = self.getdata( f, StWrd )
        thissect['sh_flags'] = self.getdata( f, StWrd )
        thissect['sh_addr'] = self.getdata( f, StAddr )
        sh_offset = self.getdata( f, StOff )
        sh_size = self.getdata( f, StWrd )
        thissect['sh_link'] = self.getdata( f, StWrd )
        thissect['sh_info'] = self.getdata( f, StWrd )
        thissect['sh_addralign'] = self.getdata( f, StWrd )
        thissect['sh_entsize'] = self.getdata( f, StWrd )

        thissect['is_shstr'] = 0; # Extra flag to be set to 0 for all but the string index
        
        f.seek( sh_offset )
        thissect[ 'image' ] = f.read( sh_size )

        thissect[ 'sh_size_UNUSED' ] = sh_size
        thissect[ 'sh_offset_UNUSED' ] = sh_offset
        
        self.sections.append( thissect )

    def putsection( self, f, s, offset ):
        self.putdata( f, StWrd, s['sh_name'] )
        self.putdata( f, StWrd, s['sh_type'] )
        self.putdata( f, StWrd, s['sh_flags'] )
        self.putdata( f, StAddr, s['sh_addr'] )
        self.putdata( f, StOff, offset )
        self.putdata( f, StWrd, len( s['image'] ) )
        self.putdata( f, StWrd, s['sh_link'] )
        self.putdata( f, StWrd, s['sh_info'] )
        self.putdata( f, StWrd, s['sh_addralign'] )
        self.putdata( f, StWrd, s['sh_entsize'] )


    def getprog( self, f ):
        thisp = {}

        thisp['p_type'] = self.getdata( f, StWrd )
        p_offset = self.getdata( f, StOff )
        thisp['p_vaddr'] = self.getdata( f, StAddr )
        thisp['p_paddr'] = self.getdata( f, StAddr )
        p_filesz = self.getdata( f, StWrd )
        thisp['p_mesz'] = self.getdata( f, StWrd )
        thisp['p_flags'] = self.getdata( f, StWrd )
        thisp['p_align'] = self.getdata( f, StWrd )

        if thisp['p_type'] != SHT_NOBITS:
            f.seek( p_offset )
            thisp[ 'image' ] = f.read( p_filesz )
        else:
            thisp[ 'image' ] = chr(0) * p_filesz 

        thisp['p_filesz_UNUSED'] = p_filesz
        thisp['p_offset_UNUSED'] = p_offset
        
        self.progs.append( thisp )

    def putprog( self, f, p, offset ):
        
        self.putdata( f, StWrd, p['p_type'] )
        self.putdata( f, StOff, offset )
        self.putdata( f, StAddr, p['p_vaddr'] )
        self.putdata( f, StAddr, p['p_paddr'] )
        self.putdata( f, StWrd, len( p['image'] ) )
        self.putdata( f, StWrd, p['p_mesz'] )
        self.putdata( f, StWrd, p['p_flags'] )
        self.putdata( f, StWrd, p['p_align'] )


    def calclen( self, s ):
        "Calculate the length of the structured represnted by s"
        l = 0
        
        for p in s:
            fmt = self.formatstring( p )
            l = l + struct.calcsize( fmt )

        return l



    def formatstring( self, what ):
        if self.machineflags[0] == ELFCLASS32:      # FIXME: Currently ignore size
            fmt = ""
        elif self.machineflags[0] == ELFCLASS64:
            fmt = ""
            
        if self.machineflags[1] == ELFDATA2LSB:
            fmt = fmt + "<"
        elif self.machineflags[1] == ELFDATA2MSB:
            fmt = fmt + ">"

        if what == StUChar:
            fmt = fmt+"B" # Close enough?
        elif what == StHalf:
            fmt = fmt+"H"
        elif what == StOff:
            fmt = fmt+"I"
        elif what == StAddr:
            fmt = fmt+"I"
        elif what == StSWrd:
            fmt = fmt+"i"
        elif what == StWrd:
            fmt = fmt+"I"

        return fmt
    

    def getdata( self, f, what ):
        # First build a format string 
        fmt = self.formatstring( what )
        
        l = struct.calcsize( fmt ) # How long?
        s = f.read( l )

        return struct.unpack( fmt, s )[0]


    def putdata( self, f, what, data ):
        # First build a format string 
        fmt = self.formatstring( what )

        s = struct.pack( fmt, data )

        f.write( s )
        
