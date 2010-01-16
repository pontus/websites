#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-
#
# telefonisten - your phone book for KOM.
#
# Copyright (c) 2002  Pontus Sköld <pont_tel@soua.net>
# based on alarm_archiver by Peter Åstrand,
# Copyright (C) 2001  Peter Åstrand <astrand@lysator.liu.se>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#

import sys
import os
import encodings

os.chdir('../lyspython')
sys.path.append('../lyspython')
sys.path.append('../python-lyskom')

import inspect
import time
import kom
import komparam
import string
import telkat
import traceback

homed = os.getenv("HOME")

if not homed:   # No such environment variable
    homed = ""
    
AGENT_PERSON = "telefonisten"
AGENT_PASSWORD = open( homed + "/."+ AGENT_PERSON + "_password" ).readline().strip()

person = -1  # Will be looked up

KOMSERVER = "sno.pp.se"
VERSION = "0.1"

def retno( s, prefix ):

# Remove spaces and dashes
    s = string.join( s.split(), '' )
    s = string.join( s.split( '-' ), '' )

    news = ""
    
    t = s[ s.find( prefix ) :].strip() # Remove anything before the number

    if t[0] == '+':
        news = '+'
        t = t[ 1: ]
        
    for p in t:
        if p.isdigit():
            news = news+p  # Another digit in the number
        else:
            return news    # No, return what we have

    return news
        
def find_no( s ):

    if s.find( "0" ) != -1:
        return retno( s, "0" )

    elif s.find( "+46" ) != -1:
        return retno( s, "+46" )

    return




def find_name( s ):

    area = ""
    address = ""

    first = ""
    last = ""
    
    # First handle any area given

    if s.find( " i " ) != -1:
        area = s[ s.find( " i " )+3: ]

        if area.find( " " ) != -1:
            area = area[ :area.find( " " ) ]

        s = s[ : s.find( " i " )] + s[ s.find( " i " )+3+len(area):]         

    # And an address
    if s.find( encodings.codecs.latin_1_decode( " på ")[0] ) != -1:
        address = s[ s.find( " på " )+4: ]

        if address.find( " " ) != -1:
            address = address[ :address.find( " " ) ]

        s = s[ : s.find( " på " )] + s[ s.find( " på " )+4+len(address):]         

    if s.find( "," ) != -1:
        # Contains a comma, assume Sköld, Pontus

        first = s[ s.find( "," )+1 :]
        last = s[ :s.find( "," ) ]

    elif s.find( " " ) != -1:
        # Pontus Sköld

        first = s[ :s.find( " " ) ]
        last = s[ s.find( " " )+1 :]
    else:
        return            # Give up

    return ( first.strip(), last.strip(), area.strip(), address.strip() )
    
def qualifier( s, d ):
    "Return the correct qualifier for a string or the default d if not found"
    
    if not s:
        return d
    
    if s[-1] == '*' :
        return 'trunc'
    elif s[-1] == '~':
        return 'fuzzy'
    return d

def qf( s ):
    "Return the string, cleared from qualifiers."
    
    if not s:
        return ""
    
    if s[-1:] == '*' or s[-1:] == '~':
        return s[:-1]
    return s

   

def send_letter( to, conn, subj, message ):
    "Send a letter to the given person with subj as Subject and message as body"
    
    misc_info = kom.CookedMiscInfo()
    misc_info.recipient_list.append(kom.MIRecipient( kom.MIR_TO, int(to) ))

    aux_items = [] # FIXME!

    # creating-software [15] (text)

    ai = kom.AuxItem(kom.AI_CREATING_SOFTWARE)
    ai.data = "telefonisten %s" % VERSION
    aux_items.append(ai)

    ai2 = kom.AuxItem(kom.AI_CONTENT_TYPE)
    ai2.data = "text/plain"
    aux_items.append(ai2)
    
    text = subj + "\n" + message  
    kom.ReqCreateText(conn, text, misc_info, aux_items).response()
                            

    
def async_message( msg, conn ):

    orgsearch = msg.message
    
    if not msg.recipient == person:   # Not a message to us?
        return
    
    letterflag = 0
    replyed = 0

    if msg.message and msg.message[0] == "!":         # Request for a long reply?
        letterflag = 1
        msg.message =  encodings.codecs.latin_1_decode( msg.message[1:] )[0]
        
    msg.message = encodings.codecs.latin_1_decode( msg.message.strip() )[0]  # Clean up whitespace
    
    t = find_no( msg.message )

    if t:      # We were given a number?
        try:
            s = telkat.NumberLookup( t )
            t = u"Det är %s, %s som har %s" % (s[0]['name'].strip(), s[0]['adress'].strip(), s[0]['number'].strip() )
        except:
            t = u"Tyvärr, ingen aning om vem som har %s " % t

    else:     # Name search
        n = find_name( msg.message )

        if n:
            try:
                s = telkat.NameLookup( first = encodings.codecs.latin_1_encode( qf( n[0] ))[0],
                                       firsttype = qualifier( n[0], 'exact' ), \
                                       last = encodings.codecs.latin_1_encode( qf( n[1] ))[0],
                                       lasttype = qualifier( n[1], 'exact' ), \
                                       area = encodings.codecs.latin_1_encode( n[2])[0], \
                                       adress = encodings.codecs.latin_1_encode( qf( n[3] ) )[0], \
                                       addresstype = qualifier( n[3], 'trunc' ))

                if len(s) > 1 and letterflag:
                    txt = u"Följande träffar hittades (max 250 träffar kan returneras)\n\n"
                   
                    for p in s:
                        txt = txt+"%s har telefon %s och adress %s\n" % ( p['name'].strip(), p['number'].strip(), p['adress'].strip() )
                       
                    send_letter( msg.sender, conn, "Resultat av sökning (%s)" %
                                 encodings.codecs.latin_1_encode(msg.message)[0],
                                 encodings.codecs.latin_1_encode(txt)[0] )
                    replyed = 1

                else:  # One match or no reply? send a message
                    t = u"%s har telefon %s och adress %s" % ( s[0]['name'].strip(), s[0]['number'].strip(), s[0]['adress'].strip() )

                    if len(s) > 1:
                        t = t + u"\n(Det finns fler träffar, skicka mig !%s för att få ett brev med alla träffar.)" % msg.message
                    
            except:
                t = u"Tyvärr, hittar inget nummer till %s %s (det kanske blev fel någonstans)" % (
                    qf( n[0] ),
                    qf( n[1] ))
                print traceback.print_exc()
                #print orgsearch
                            
    # Here, we should  have a good reply

    if not t:
        if msg.message == "help" or msg.message == "?" or msg.message == encodings.codecs.latin_1_decode("hjälp")[0]:
            t = encodings.codecs.latin_1_decode( "Återse min presentation för hjälp." )[0]
        else:
            t = encodings.codecs.latin_1_decode( "Asså, ba, jag förstår inte vad du snackar om" )[0]

    if not replyed:
        try:
            kom.ReqSendMessage(conn, msg.sender,   encodings.codecs.latin_1_encode(t)[0] ).response()
        except:
            print traceback.print_exc()
            #print orgsearch

conn = kom.CachedConnection(KOMSERVER, 4894, "telefonisten")


persons = conn.lookup_name(AGENT_PERSON, want_pers = 1, want_confs = 0)
if len(persons) != 1:
    print "Not just one match"
else:
    person = persons[0][0]

                                  
kom.ReqLogin(conn, person, AGENT_PASSWORD, invisible = 1).response()

conn.add_async_handler(kom.ASYNC_SEND_MESSAGE, async_message)
kom.ReqAcceptAsync(conn, [kom.ASYNC_SEND_MESSAGE,]).response()

kom.ReqSetClientVersion(conn, "telefonist.py", VERSION)

while 1:
    conn.parse_present_data()
    time.sleep(0.5)

