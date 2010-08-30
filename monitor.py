import time
import os
import re
import sys
import string
import logging
import logging.handlers
import yaml
import getopt

from os.path import getmtime, getsize, normpath, join

logger = None

def init_logger(verbose=True, 
                filelogging=False, 
                logfilename='filemonitor.out', 
                logfilesize=100000, 
                backupcount=5):
    # Set up a specific logger with our desired output level
    logger = logging.getLogger('logger')
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    if verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    if filelogging == True:
        # File logger
        filehandler = logging.handlers.RotatingFileHandler(logfilename, 
                                                           maxBytes=logfilesize, 
                                                           backupCount=cackupcount)
        filehandler.setFormatter(formatter)
        logger.addHandler(filehandler)
    
    # Console logger
    consolehandler =  logging.StreamHandler()
    consolehandler.setFormatter(formatter)
    logger.addHandler(consolehandler)
    return logger

class EventDef:
    def __init__(self, dir, pattern, action, maxerrors=2, minsize=0, tracking_interval=10):
        self.dir = dir
        self.pattern = pattern
        self.action = action
        self.maxerrors = maxerrors
        self.minsize = minsize
        self.tracking_interval = tracking_interval

    def __eq__(self, other):
        if not other: return False
        return (self.dir == other.dir) and (self.pattern == other.pattern)

    def __repr__(self):
        return "EventDef: dir='%s', pattern='%s', action='%s', minsize='%s', maxerrors='%s', tracking_interval='%s'" % (
            self.dir, self.pattern, self.action, self.minsize, self.maxerrors, self.tracking_interval)


class Event:
    CANDIDATE = 'CANDIDATE'
    ACTIVE = 'ACTIVE'
    RETRY = 'RETRY'
    DISABLED = 'DISABLED'

    def __init__(self, eventdef, filename):
        self.eventdef = eventdef
        self.filename = filename
        self.state = Event.CANDIDATE
        self.errors = 0
        self.last_mtime = 0
        self.last_changed = time.time()
        self.last_filesize = 0

    def __repr__(self):
        return "Event/Candidate: , filename='%s', state='%s', errors='%s', eventdef='%s'" % (
            self.filename, self.state, self.errors, self.eventdef)

    def __eq__(self, other):
        return (self.filename == other.filename) and (self.eventdef == other.eventdef)


def remove_obsolete_events(eventdefs, existing_events, names):
    events = []
    for event in existing_events:
        if event.filename not in names:
            logger.info("%s is obsolete, file does no more exist. Removing event from event list" % 
                        (event))
            pass
        else:
            events.append(event)
    return events


def find_candidates(eventdefs, existing_candidates, existing_events):
    candidates = names = []
    logger.debug("find_candidates() with:\nexisting events = %s,\nexisting candidates = %s" % 
                 (existing_events, existing_candidates))

    for eventdef in eventdefs:
        names = os.listdir(eventdef.dir)
        logger.debug("Looking for pattern %s" % (eventdef.pattern))
        for name in names:
            if re.match(eventdef.pattern, name):
                candidate = Event(eventdef, name)
                logger.debug("---->   matched %s" % (name))
                
                if (candidate not in existing_events) and (candidate not in existing_candidates):
                    logger.info("New candidate found: %s" % (candidate,))
                    candidates.append(candidate)
                elif (candidate in existing_candidates):
                    logger.debug("candidate already exists")
                    candidates.append(existing_candidates[existing_candidates.index(candidate)])
                else:
                    logger.debug("candidate already in existing events list")

    events = remove_obsolete_events(eventdefs, existing_events, names)
    logger.debug("--> New candidates list len = %d" % (
            len(candidates)))
    return (candidates, events)


def promote_candidates(existing_candidates, events, now):
    candidates = []

    logger.debug("Promoting candidates to events ...")
    logger.debug("Existing candidates list len = %d" % (
            len(existing_candidates)))
    logger.debug(existing_candidates)
    logger.debug(80*"-")

    for candidate in existing_candidates:
        abspath = normpath(join(candidate.eventdef.dir, candidate.filename))
        mtime = getmtime(abspath)
        filesize = getsize(abspath)
        logger.debug("modification time of %s = %s, " 
                     "last_access_time = %s, size = %s" % 
                     (candidate.filename, mtime, candidate.last_mtime, filesize))
        if (candidate.last_mtime != mtime) or (filesize != candidate.last_filesize):
            logger.debug("Not promoting %s - file was changed or just created." % (candidate))
            candidate.last_mtime = mtime
            candidate.last_change = now
            candidate.last_filesize = filesize
            candidates.append(candidate)
        elif (candidate.eventdef.minsize > filesize):
            logger.debug("Not promoting %s - file smaller than minsize." % (candidate))
            candidates.append(candidate)
        else:
            if (now - candidate.last_change) > candidate.eventdef.tracking_interval:
                logger.debug("Promoting %s" % (candidate))
                candidate.state = Event.ACTIVE
                events.append(candidate)
            else:
                logger.debug("Not yet promoting %s - tracking interval active." % (candidate))
                candidates.append(candidate)
            
    logger.debug("--> New candidates list len = %d" % (
            len(candidates)))
    return (candidates, events)


def execute_events(existing_events):

    events=[]

    logger.debug("Executing events ...")
    logger.debug("Existing event list len = %d" % (
            len(existing_events)))
    logger.debug(existing_events)
    logger.debug(80*"-")
    for event in existing_events:
        if event.state == Event.DISABLED:
            logger.info("Event %s is disabled; skipping." % (event))
            events.append(event) # keep that event??
            continue
            
        action = event.eventdef.action.format(event=event, eventdef=event.eventdef)
        logger.info("Execution action ' %s ' for event %s" % (action, event))
        rc=os.system(action)
        logger.info("RC = %d" % (rc))
        if rc == 0:
            logger.info(" -> All OK, removing event from event list")
        elif event.errors < event.eventdef.maxerrors:
            logger.warning(" -> Error while executing action")
            event.errors += 1
            event.state = Event.RETRY
            events.append(event)
        else:
            logger.error(" -> Action failed %d times. Disabling event." % (event.errors))
            event.state=Event.DISABLED
            events.append(event)
    logger.debug("--> New event list len = %d" % (len(events)))
    return events


def monitor(config_filename, polling_interval=10,dynamic_reload=False):
    events = []
    candidates = []
    eventdefs = read_config(config_filename)
    
    while True:
        if dynamic_reload:
            eventdefs = read_config(config_filename)
        logger.debug(80*"#")
        (candidates, events) = find_candidates(eventdefs, candidates, events)
        (candidates, events) = promote_candidates(candidates, events, time.time())
        events = execute_events(events)
        time.sleep(polling_interval)

def read_config(filename):
    stream = open(filename)
    eventdefs = yaml.load(stream)
    stream.close()
    return eventdefs
    


def usage():
    print("Usage: %s\n"
          "          [-t|--test]             : Run test mode (use this to create a sample config file)\n"
          "          [-i N|--interval=N]     : Polling interval of N seconds [5]\n"
          "          [-c file|--config=file] : Use YAML config file [config.yaml]\n"
          "          [-d|--dynamic]          : Enable dynamic config file reload\n"
          "          [-v|--verbose]          : Print debug messages\n"
          "          [-h|--help]             : Print this help message\n"
          "          [-l|--logging]          : Enable file logging, default is console only\n"
          "          [--backupcount=N]       : Keep N logfiles (rotate) [5]\n"
          "          [--logfilesize=N]       : Rotate logfile when N bytes in size [100000]\n"
          "          [--logfilename=file]    : Log file name [monitor.out]\n" % (__file__))


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 
                                   "i:c:f:tlvh", 
                                   ["interval=", 
                                    "config=", 
                                    "logfilename=", 
                                    "logfilesize=", 
                                    "backupcount=", 
                                    "dynamic", "logging", "verbose", "help", "test",])
    except getopt.GetoptError, err:
        print str(err) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)
    global logger
    verbose = False      
    logging = False
    test = False
    logfilename = "monitor.out"
    config = "config.yaml"
    logfilesize = 100000
    backupcount = 5
    interval = 5
    dynamic = False

    for o, a in opts:
        if o in ("-v", "--verbose"):
            verbose = True
        elif o in ("-h", "--help"):
            usage()
            sys.exit(0)
        elif o in ("-i", "--interval"):
            interval = int(a)
        elif o in ("-l", "--logging"):
            logging = True
        elif o in ("-f", "--logfilename"):
            logfilename = a
        elif o in ("--logfilesize"):
            logfilesize = int(a)
        elif o in ("--backupcount"):
            backupcount = int(a)
        elif o in ("-c", "--config"):
            config = a
        elif o in ("-d", "--dynamic"):
            dynamic = True
        elif o in ("-t", "--test"):
            test = True
        else:
            assert False, "unhandled option"
    logger = init_logger(verbose, logging, logfilename, logfilesize, backupcount)
    eventdefs = []

    if test:
	if os.name == 'posix':
            # UNIX version
            os.system("touch /tmp/huhuralf.txt /tmp/halloralf.txt /tmp/hallo1234.txt")
            e1 = EventDef("/tmp", "huhu.*\.txt", "rm /tmp >> /tmp/huhu.out")
            e2 = EventDef("/tmp", "hallo.*\.txt", "echo \"{eventdef.dir}\" >> /tmp/hallo.out; rm /tmp/{event.filename}")
        elif os.name == 'nt': 
            # Windows version
            os.system("touch c:/temp/huhuralf.txt c:/temp/halloralf.txt c:/temp/hallo1234.txt")
            e1 = EventDef("c:/temp", "huhu.*\.txt", "del c:/tmp >> c:/temp/huhu.out", minsize=10000)
            e2 = EventDef("c:/temp", "hallo.*\.txt", "type \"{eventdef.dir}\" >> c:\\temp\\hallo.out & del c:\\temp\\{event.filename}")
        
        eventdefs.append(e1)
        eventdefs.append(e2)
        
        # store config
        stream = open(config, 'w')
        yaml.dump(eventdefs, stream)
        stream.close()

    monitor(config, interval, dynamic)

    

if __name__ == '__main__':
    main()





