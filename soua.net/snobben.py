#! /usr/bin/env python
#
# Snobben - LysKOM/IRC-gateway, largely based on Joel Rosdahls example bot.
#

import sys
import os

os.chdir('../lyspython')
sys.path.append('../lyspython')
sys.path.append('../python-lyskom')
sys.path.append('../python-irclib')

import inspect
import threading
import time
import re
import kom
import komparam
import traceback
import string
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_uh, irc_lower

homed = os.getenv("HOME")

if not homed:   # No such environment variable
    homed = ""
    
AGENT_PERSON = "snobben"
AGENT_PASSWORD = open( homed + "/."+ AGENT_PERSON + "_password" ).readline().strip()

MAX_HANDLE_LEN = 9
person = -1  # Will be looked up

# Aux-item that may contain the handle

HANDLE_AUX_NO = 20000

KOMSERVER = "kom.sno.pp.se"
KOMVERSION = "0.1"
IRCSERVERS = "irc.swipnet.se", 
IRCPORT = 6667

CHANNELS = { "#blomsterflicka":"#blomsterflicka",
             "#blomster2":"testmerblom" }

nextircserver = 0

def ircserver():
    global nextircserver
    l = nextircserver
    print "ircserver"
    print nextircserver
    nextircserver = (nextircserver+1) % len(IRCSERVERS)
    print IRCSERVERS[l]
    return IRCSERVERS[l]


class listenBot(SingleServerIRCBot):
    def __init__(self, conn, channels, nickname, server, port=6667):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
        
        self.komconn = conn
        self.rlock = threading.RLock()
        self.channelstouse = list(channels[:])
        self.welcomed = 0
        
        print dir(self.connection)
        print "init"
        
    def on_welcome(self, c, e):
        print dir(self.connection)
        print "welcome"

        self.welcomed = 1

        for p in self.channelstouse:
            c.join(p)
            print "Joining %s" % p
        print "Joined channels"

    def join(self, channel):
        if channel in self.channelstouse:
            return
        
        self.channelstouse.append(channel)

        if self.welcomed:
            self.connection.join(self,channel)

    def on_ctcp(self, c, e):
        print "ctcp"
        print e.arguments()

        if not e.arguments()[0]=='ACTION':
            SingleServerIRCBot.on_ctcp(self, c,e)
        else:
            if nm_to_n( e.source() ) not in self.komconn.bot.keys():
                #send_message( self.komconn, self.komconn.confs[ e.target() ],
                # str(e.source()) + " " + str( e.arguments()[0] ))
                send_comment( self.komconn, self.komconn.confs[ e.target().lower() ],
                              str(e.source())+" gör något",
                              nm_to_n(e.source()) + " " + str( e.arguments()[1] ),
                              nm_to_n(e.source()), nm_to_uh(e.source()), 1)

        
    def on_pubmsg(self, c, e):
        print "pubmsg"

        print e
        print dir(e)
        print e.target()
        
        print "From %s " % nm_to_n( e.source() )
        print self.komconn.bot.keys()

        if nm_to_n( e.source() ) not in self.komconn.bot.keys():
            #send_message( self.komconn, self.komconn.confs[ e.target() ], str(e.source()) + " " + str( e.arguments()[0] ))
            send_comment( self.komconn,  self.komconn.confs[ e.target().lower() ], str(e.source()) + " säger ", str( e.arguments()[0] ),
                          nm_to_n(e.source()), nm_to_uh(e.source()), 1)

        return

    def send_notice(self, msg):
        return
    
    def on_privmsg(self, c, e):
        return
    
class sendBot(listenBot):
    def __init__(self, conn, channels, nickname, server, port=6667):
        listenBot.__init__(self, conn, channels, nickname, server, port)
        print dir(self.connection)
        self.nickname = nickname
        print server
        print "sendBot init"
        
    def on_pubmsg(self, c, e):
        return

    def on_ctcp(self, c, e): # We don't want to handle ACTIONs
        SingleServerIRCBot.on_ctcp(self, c,e)
           
    def on_privmsg(self, c, e):
        send_comment( self.komconn, self.komconn.confs[ e.target().lower() ], str(e.source()) + " säger ", str( e.arguments()[0] ),
                      nm_to_n(e.source()), nm_to_uh(e.source()), 0)
        send_message( self.komconn, self.komconn.confs[ e.target().lower() ], str(e.source()) + " " + str( e.arguments()[0] ))
        return
    
    def send_notice( self, channel, msg ):

        print "%s is sending message %s" % ( self.nickname, msg ) 
        self.join( channel)
        self.connection.privmsg( channel, msg)

        
def send_message( conn, to, message ):
    "Send a message to the given conference"

    print "send_message, get lock"
    conn.rlock.acquire()
    kom.ReqSendMessage( conn, to, message ).response()
    conn.rlock.release()
    print "send_message,release lock"
    
def send_comment( conn, to, subj, message, fromname, fromaddr, comment ):
    "Send a letter to the given conference with subj as Subject and message as body"

    print "Sending comment, get lock"
    conn.rlock.acquire()

    misc_info = kom.CookedMiscInfo()
    print "Cooked MI OK"
    misc_info.recipient_list.append(kom.MIRecipient( kom.MIR_TO, int(to) ))
    print "Fixed recipient"
    
    if comment and time.time() - conn.conferences[ to ].last_written.to_python_time() < 10*60:
        print "We shall comment"
        c = conn.conferences[ to ]

        author = 0
        authors = ""
        
        if message[:message.find(":")] in conn.authors.keys():
            author = conn.authors[ message[:message.find(":")] ] #
        else:
            r = re.compile( r"^[^ ]*:" ) # Match destination handle
            m = r.match( message )

            print m
            if m:
                if m.start() == 0 and m.end() != 0: #Sensible
                    authors = message[:m.end()-1]
            
        print "Got conf info"
        print "%d, %d, %d" % (to, c.first_local_no, 255)

        print message
        print author
        print authors
        
        tno = 0
        # Ignore old messages the dirty way 
        try:
            tnomap = kom.ReqLocalToGlobal(conn, to,
                                          max(1,
                                              c.first_local_no+c.no_of_texts-255),
                                          255).response()

            print "Got local-to-global mapping"
 
            for p in tnomap.list:
                if author or authors:       # Not a comment to anybody particular?
                    ts = conn.textstats[ p[1] ]
                    if author == ts.author:
                        tno = max( p[1], tno )
                    else:                             # Imported comment?
                        for ai in ts.aux_items:
                            if ai.tag == kom.AI_MX_AUTHOR and ai.data == authors:
                                tno = p[1]
                                # Remove header
                                if message[:m.end()-1] == authors: #Only remove the first
                                    print "Msg %s" % message
                                    message = message[ m.end(): ].strip()
                                    print "msg %s" % message


                else:
                    tno = max( p[1], tno)


        except kom.NoSuchLocalText:
            pass

        print message
        #Make it a comment?
        if tno:
            misc_info.recipient_list.append(kom.MICommentTo( kom.MIC_COMMENT, int(tno) ))

        if author and tno: # Found the text and made a comment link? remove foo:
            message = message[message.find(":")+1:].strip()
        print "Added comment info"
        
    print "Checked whatever to comment OK"
    aux_items = [] # FIXME!

    # creating-software [15] (text)

    ai = kom.AuxItem(kom.AI_CREATING_SOFTWARE)
    ai.data = "snobben %s" % KOMVERSION
    aux_items.append(ai)
    print "First aux"
        
    ai2 = kom.AuxItem(kom.AI_CONTENT_TYPE)
    ai2.data = "text/plain"
    aux_items.append(ai2)

    print "Second"

    ai = kom.AuxItem(kom.AI_MX_FROM)
    ai.data = fromaddr
    aux_items.append(ai)
    print "First aux"

    ai = kom.AuxItem(kom.AI_MX_AUTHOR)
    ai.data = fromname
    aux_items.append(ai)
    print "First aux"

    text = subj + "\n" + message  
    kom.ReqCreateText(conn, text, misc_info, aux_items).response()
    print "Sent!"
    conn.rlock.release()
    print "Sending comment, release lock"
                 
def get_subject( t ):
    return t[:t.find("\n")]

def get_text( t ):
    return t[t.find("\n")+1:]

def safechar( s ):
    if s in string.letters+string.digits:
        return s
    return ""
    
def wash_name( s ):
    return string.join( map(safechar, s), '')[:MAX_HANDLE_LEN]

def assert_bot( conn, orgname, conf ):
    name = wash_name(orgname)
        
    if not name in conn.bot.keys() or not conn.bot[name].connection.socket:
        print "Creating sendbot %s" % ircserver() 
        b = sendBot(conn, [], name, ircserver(), IRCPORT )
        conn.bot[name] = b
        conn.authors[ name ] = conf
        conn.confs[ name.lower() ] = conf
        threading.Thread( None, b.start, name ).start()


        # Wait for the connection
        while 'socket' not in dir(b.connection) or not b.connection.socket:
            time.sleep(0.5) 
            
def async_message( msg, conn ):
    print "message"

    if msg.sender not in conn.ignoreconfs:
        print "async_message, get lock"
        conn.rlock.acquire()

        name = conn.conferences[ msg.sender ].name
        channel = conn.channels[ msg.recipient ]
         
        # Look through all aux-items for the handle
        for ai in conn.conferences[ msg.sender ].aux_items:
            if ai.tag == HANDLE_AUX_NO:
                name = ai.data

        assert_bot( conn, name, msg.sender )
        conn.bot[wash_name(name)].send_notice( channel, msg.message.strip() )
        conn.rlock.release()
        print "async_message, release lock"
    

def async_text( msg, conn ):
    print "text"
    
    if msg.text_stat.author not in conn.ignoreconfs:
        print "async_text, get lock"
        conn.rlock.acquire()
        text = kom.ReqGetText(conn, msg.text_no, 0, msg.text_stat.no_of_chars).response()

        channel = ''
        for p in msg.text_stat.misc_info.recipient_list:
            if conn.channels.has_key( p.recpt ):
                channel = conn.channels[ p.recpt ]

        print "Channel is %s" % channel
        name = conn.conferences[ msg.text_stat.author ].name
        
        # Look through all aux-items for the handle
        for ai in conn.conferences[ msg.text_stat.author ].aux_items:
            if ai.tag == HANDLE_AUX_NO:
                name = ai.data

        assert_bot( conn, name, msg.text_stat.author )
        prefix = nm_to_n( get_subject( text )).strip()

        if prefix:
            prefix = prefix + ": "

        print channel
        print get_text( text ).split("\n")

        q = get_text( text ).strip()

        if not q: # No body?
            conn.bot[wash_name(name)].send_notice( channel, prefix[:-2]) # Remove trailing ': '
        else:
            for p in q.split("\n"):
                conn.bot[wash_name(name)].send_notice( channel, "%s%s" % (prefix, p.strip()))

        conn.rlock.release()
        print "async_text, release lock"
            
def main():
        
    conn = kom.CachedConnection(KOMSERVER, 4894, "snobben")

# lookup_name thinks # in the first position means numerical

    conn.bot = {}
    conn.authors = {}
    conn.confs = {}
    conn.ignoreconfs = []
    conn.rlock = threading.RLock()
    conn.channels = {}

    bot = 0
    
    for p in CHANNELS.keys():
        nick = AGENT_PERSON
        confs = conn.lookup_name(" "+CHANNELS[p], want_pers = 0, want_confs = 1)
        if len(confs) != 1:
            print "Conferences: not just one match"
            raise SystemExit

        if not bot:
            bot = listenBot(conn, [p], nick, ircserver(), IRCPORT )
            conn.authors[nick] = bot 
            conn.bot[nick] = bot 
            threading.Thread( None, bot.start, nick ).start()        
        else:
            bot.join( p )
            
        conn.channels[ confs[0][0] ] = p
        conn.confs[ p.lower() ] = confs[0][0]
        
        conn.ignoreconfs.append([ confs[0][0] ])
    
        print "Connected to %s" % p
    
    conn.rlock.acquire()
    persons = conn.lookup_name(AGENT_PERSON, want_pers = 1, want_confs = 0)
    conn.rlock.release()

    print conn.channels
    
    if len(persons) != 1:
        print "Persons: not just one match"
        raise SystemExit

    person = persons[0][0]
    
    conn.ignoreconfs.append( person )

    conn.rlock.acquire()
    kom.ReqLogin(conn, person, AGENT_PASSWORD, invisible = 1).response()
    
    conn.add_async_handler(kom.ASYNC_SEND_MESSAGE, async_message)
    conn.add_async_handler(kom.ASYNC_NEW_TEXT, async_text)
    
    kom.ReqAcceptAsync(conn, [kom.ASYNC_SEND_MESSAGE,kom.ASYNC_NEW_TEXT,]).response()
    
    kom.ReqSetClientVersion(conn, "snobben.py", KOMVERSION)
    conn.rlock.release()
    
    print "Starting main kom-loop"
    while 1:
        conn.rlock.acquire()
        conn.parse_present_data()
        conn.rlock.release()
        time.sleep(0.5)    
    

if __name__ == "__main__":
    main()
