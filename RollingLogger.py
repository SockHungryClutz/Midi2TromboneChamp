# Class for logging stuff.
# Made by SockHungryClutz
#
# To use:
#   logger = RollingLogger_Sync(LogFileName(str), MaxLogFileSize(int),
#                               MaxNumberOfLogFiles(int), LoggingLevel(int))
# From there, call logger.[debug/info/warning/error/critical](Message) to log
# Use logger.closeLog() when closing to clean up everything else
# Log Levels:
#   5 = debug
#   4 = info
#   3 = warning
#   2 = error
#   1 = critical
#
# Setting a level means no messages less important than the level you choose will be logged.
# Setting level to 0 means nothing will be logged and the logger is just a dummy.
# RollingLogger_Async can be used exactly the same way as the Sync logger, only difference
# is that the async logger will spin off a new process to handle the logging, which will
# improve performance over the sync logger (so it's multiprocess, not async, just to be clear)

import logging
from logging.handlers import RotatingFileHandler
import time
from datetime import datetime
from multiprocessing import Process, Queue

class RollingLogger_Sync:
    def __init__(self, name="logfile", fileSize=4194304, numFile=3, level=3):
        if level == 0:
            self.nologs = True
        else:
            self.logger = logging.getLogger(name)
            if level == 1:
                self.logger.setLevel(logging.CRITICAL)
            elif level == 2:
                self.logger.setLevel(logging.ERROR)
            elif level == 3:
                self.logger.setLevel(logging.WARNING)
            elif level == 4:
                self.logger.setLevel(logging.INFO)
            else:
                self.logger.setLevel(logging.DEBUG)
            self.nologs = False
            self.handler = RotatingFileHandler(name+".log", maxBytes=fileSize, backupCount=numFile)
            self.logger.addHandler(self.handler)
            self.logger.info(">Logger " + name + " initialized - " + str(datetime.now()) + "<")
    
    def debug(self, msg):
        if not self.nologs:
            self.logger.debug("[" + str(datetime.now()) + "] *   " +msg)
    
    def info(self, msg):
        if not self.nologs:
            self.logger.info("[" + str(datetime.now()) + "]     " +msg)
    
    def warning(self, msg):
        if not self.nologs:
            self.logger.warning("[" + str(datetime.now()) + "] !   " +msg)
    
    def error(self, msg):
        if not self.nologs:
            self.logger.error("[" + str(datetime.now()) + "] !!  " +msg)
    
    def critical(self, msg):
        if not self.nologs:
            self.logger.critical("[" + str(datetime.now()) + "] !!! " +msg)
    
    def closeLog(self):
        pass

class AsyncLoggerBackend:
    def __init__(self, name, fileSize, numFile, level, queue):
        self.queue = queue
        self.logger = logging.getLogger(name)
        if level == 1:
            self.logger.setLevel(logging.CRITICAL)
        elif level == 2:
            self.logger.setLevel(logging.ERROR)
        elif level == 3:
            self.logger.setLevel(logging.WARNING)
        elif level == 4:
            self.logger.setLevel(logging.INFO)
        else:
            self.logger.setLevel(logging.DEBUG)
        self.handler = RotatingFileHandler(name+".log", maxBytes=fileSize, backupCount=numFile)
        self.logger.addHandler(self.handler)
        self.logger.info(">Logger " + name + " initialized - " + str(datetime.now()) + "<")
        self.closing = False
    
    def checkQueue(self):
        while not self.queue.empty():
            msg = self.queue.get()
            if msg == None or self.closing:
                self.closing = True
                continue
            level = int(msg[0])
            msg = msg[1:]
            if level == 1:
                self.logger.critical(msg)
            elif level == 2:
                self.logger.error(msg)
            elif level == 3:
                self.logger.warning(msg)
            elif level == 4:
                self.logger.info(msg)
            else:
                self.logger.debug(msg)

def makeAsyncLogger(name, fileSize, numFile, level, queue):
    asynclog = AsyncLoggerBackend(name, fileSize, numFile, level, queue)
    while not asynclog.closing:
        asynclog.checkQueue()
        time.sleep(5)

class RollingLogger_Async:
    def __init__(self, name, fileSize, numFile, level):
        if level == 0:
            self.nologs = True
        else:
            self.nologs = False
            self.closed = False
            self.logQueue = Queue()
            self.p = Process(target=makeAsyncLogger, args=(name, fileSize, numFile, level, self.logQueue,))
            self.p.start()
            
    def debug(self, msg):
        if not self.nologs and not self.closed:
            self.logQueue.put("5[" + str(datetime.now()) + "] *   " +msg)
    
    def info(self, msg):
        if not self.nologs and not self.closed:
            self.logQueue.put("4[" + str(datetime.now()) + "]     " +msg)
    
    def warning(self, msg):
        if not self.nologs and not self.closed:
            self.logQueue.put("3[" + str(datetime.now()) + "] !   " +msg)
    
    def error(self, msg):
        if not self.nologs and not self.closed:
            self.logQueue.put("2[" + str(datetime.now()) + "] !!  " +msg)
    
    def critical(self, msg):
        if not self.nologs and not self.closed:
            self.logQueue.put("1[" + str(datetime.now()) + "] !!! " +msg)
    
    def closeLog(self):
        if not self.nologs and not self.closed:
            self.closed = True
            self.logQueue.put(None)
            self.logQueue.close()
            self.p.join()