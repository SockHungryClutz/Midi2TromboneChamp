import mido.midifiles as mido
from mido import MidiFile, MetaMessage, MidiTrack

import sys
import json
import os
import sys
import configparser
import math
from pydub import AudioSegment
from PIL import Image, ImageFilter
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import re

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

def ticks2s(ticks, tempo, ticks_per_beat):
    """
        Converts ticks to seconds
    """
    return ticks/ticks_per_beat * tempo

def SetupNote(beat, length, noteNumber, endNoteNumber):
    startPitch = (noteNumber-60)*13.75
    endPitch = (endNoteNumber-60)*13.75
    return [beat, length , startPitch , endPitch - startPitch , endPitch]

# Substitute lyrics with stuff
def subLyrics(lyric):
    l = lyric.replace("=","-")
    l = l.replace("+","")
    l = l.replace("#","")
    l = l.replace("^","")
    l = l.replace("`",'"')
    return l

# Lotta stuff to remove
def StripStr(str, chars):
    for char in chars:
        str = str.replace(char,'')
    return str

# Compensation for the fact that TromboneChamp doesn't change tempo
# These tempo values are in seconds per beat except bpm what and why
def DynamicBeatToTromboneBeat(tempoEvents, midiBeat, bpm):
    baseTempo = 60 / bpm
    idx = 0
    if tempoEvents[0][1] == 0:
        baseTempo = tempoEvents[0][0]
        idx = 1
    previousMark = 0
    time = 0
    for i in range(idx,len(tempoEvents) + 1):
        if i < len(tempoEvents) and midiBeat >= tempoEvents[i][1]:
            time += baseTempo * (tempoEvents[i][1] - previousMark)
            previousMark = tempoEvents[i][1]
            baseTempo = tempoEvents[i][0]
        else:
            time += baseTempo * (midiBeat - previousMark)
            break
    return round((time * bpm) / 60, 3)

if __name__ == '__main__':
    log = RollingLogger_Sync(level=4)
    os.makedirs("./_output", exist_ok=True)
    with open("./_output/songlist.csv",'w') as f:
            f.write("Name,Artist,Genre,Difficulty")
    for entry in os.scandir():
        if not entry.is_dir(): continue
        basepath = entry.path
        path = os.path.join(basepath, "notes.mid")
        dicc = dict()
        filename = os.path.basename(path)
        filename = os.path.splitext(filename)[0]
        defaultLength = 0.2
        bpm = 120
        DEFAULT_TEMPO = 60 / bpm

        # Load configuration defaults
        config = configparser.ConfigParser()
        config.read(os.path.join(basepath, 'song.ini'), encoding="utf-8")

        try:
            foldername = config["song"]["name"]
            foldername = StripStr(foldername, "'\"\\/?:><|*.")
            namesplice = foldername.split()
            shortname = ""
            for word in namesplice:
                if len(shortname) >= 20: break
                if word.lower() in ["the","of","a","or"]: continue
                if word.lower() == "and": shortname += " &"
                if len(shortname) + len(word) > 20 and shortname != "": break
                shortname += " " + word
            foldername = config["song"]["artist"] + foldername
            foldername = StripStr(foldername, "'\"\\/?:><|*. ")
            foldername = foldername[:48]
            dicc["name"]= config["song"]["name"]
            dicc["shortName"]= shortname.strip()
            dicc["trackRef"]= foldername
            dicc["year"] = int(re.findall(r'\d{4}',config["song"]["year"])[0]) # I hate Beatles Rock Band and its DLC
            dicc["author"] = config["song"]["artist"]
            dicc["genre"] = config["song"]["genre"]
            dicc["description"] = config["song"]["icon"]
            dicc["difficulty"] = int(config["song"]["diff_vocals"]) + 3
            dicc["timesig"] = 4
        except:
            log.warning("No ini or missing section: " + str(basepath))
            continue
        try:
            dicc["description"] = config["song"]["loading_phrase"]
        except:
            dicc["description"] = config["song"]["icon"]
            pass

        if dicc["difficulty"] <= 2:
            log.warning("No vocal track indicated in ini: " + str(basepath))
            continue

        # Import the MIDI file...
        mid = MidiFile(path, clip=True)

        log.info("DIR: " + str(basepath))
        log.info("TYPE: " + str(mid.type))
        log.info("LENGTH: " + str(mid.length))
        log.info("TICKS PER BEAT: " + str(mid.ticks_per_beat))

        if mid.type == 3:
            log.warning("Unsupported midi type.")
            continue

        """
            First read all the notes in the MIDI file
        """
        tick_duration = 60/(mid.ticks_per_beat*bpm)
        notes = []
        log.info("Tick Duration:")
        log.info(str(tick_duration))

        log.info("Tempo:" + str(DEFAULT_TEMPO))
        final_bar = 0

        allMidiEventsSorted = []
        tempoEvents = []
        lyricEvents = []
        skipOtherTracks = False

        for i, track in enumerate(mid.tracks):
            tempo = DEFAULT_TEMPO
            totaltime = 0
            globalTime = 0
            glissyHints = dict()
            globalBeatTime = 0
            for message in track:
                t = ticks2s(message.time, tempo, mid.ticks_per_beat)
                tromboneBeat = message.time/mid.ticks_per_beat
                totaltime += t
                globalTime+= message.time
                globalBeatTime+= tromboneBeat
                currTime = globalTime*tick_duration*1000

                if isinstance(message, MetaMessage):
                    if message.type == "set_tempo":
                        # Tempo change
                        tempo = message.tempo / 10**6
                        if globalBeatTime == 0:
                            bpm = 60 / tempo
                            tick_duration = 60/(mid.ticks_per_beat*bpm)
                            dicc["tempo"]= round(60 / tempo)
                            notespacing = 60 / tempo
                            if notespacing < 50: notespacing += 100
                            elif notespacing < 100: notespacing *= 2
                            dicc["savednotespacing"] = round(notespacing)
                        tempoEvents += [(tempo, globalBeatTime)]
                        log.debug("Tempo Event: " + str(tempo) + " spb | " + str(globalBeatTime))
                    elif message.type == "time_signature" and globalBeatTime == 0:
                        dicc["timesig"] = message.numerator
                    elif message.type == "track_name":
                        if (message.name in ["PART VOCALS", "PART_VOCALS", "BAND VOCALS", "BAND_VOCALS"]):
                            # Special track label for rockband/guitar hero tracks. All other events void.
                            allMidiEventsSorted = []
                            lyricEvents = []
                            glissyHints = {}
                            # Nothing important should be skipped, first track should be tempo and stuff
                            skipOtherTracks = True
                    elif message.type == "lyrics" or message.type == "text":
                        if len(message.text) == 0 or message.text[0] in ["["," "]:
                            continue
                        if message.text == "+":
                            # Used in RB to hint that notes are slurred together
                            glissyHints[globalBeatTime] = None
                        else:
                            lyricEvents += [(i, message.text, DynamicBeatToTromboneBeat(tempoEvents, globalBeatTime, dicc["tempo"]))]
                    elif message.type == "end_of_track":
                        pass
                    else:
                        log.warning("Unsupported metamessage: " + str(message))

                else:
                    allMidiEventsSorted += [(i, message, globalBeatTime)]
            if skipOtherTracks:
                break

        allMidiEventsSorted = sorted(allMidiEventsSorted, key=lambda x: x[2] )

        # Sort out lyric events
        lyricsOut = []
        for i, lyric, beat in lyricEvents:
            l = subLyrics(lyric)
            if l == "":
                continue
            lyricEvent = dict()
            lyricEvent["text"] = l
            lyricEvent["bar"] = round(beat, 3)
            lyricsOut += [lyricEvent]

        tempo = DEFAULT_TEMPO
        totaltime = 0
        globalTime = 0
        currentNote = []
        currentPhrase = []
        # oh boy, how do I explain this?
        # TC has a pretty limited range
        # If a bunch of notes are outside the range, the notes need to be shifted
        # Shifting just one note sounds weird, but vocals in rockband mark phrases
        # If more notes are currently out of range than would be if the range was shifted, then its ok to shift
        # Acts sort of like voting with which direction to shift (if at all)
        # 4 sections for votes for moving up/against and votes for moving down vs against
        shiftVotes = [0,0,0,0]
        phraseOpen = False
        globalBeatTime = 0
        noteToUse = 0
        lastNote = -1000
        defaultLength = 0.2
        defaultSpacing = 0.2
        noteTrimming = 0.0
        currBeat = 0
        noteHeld = False
        lastNoteOffBeat = 0
        heldNoteChannel = -1

        for i, message, currBeat in allMidiEventsSorted:
            currentBeat2 = DynamicBeatToTromboneBeat(tempoEvents, currBeat, dicc["tempo"])
            if isinstance(message, MetaMessage):
                if message.type == "end_of_track":
                    pass
                else:
                    log.info("Unsupported metamessage: " + str(message))
            else:  # Note
                if (message.type in ["note_on", "note_off"] and (message.note >= 96 or message.note < 16)):
                    if (message.type == "note_on" and message.velocity > 0) and (message.note == 105 or message.note == 106):
                        if shiftVotes[2] > shiftVotes[3]:
                            for note in currentPhrase:
                                note[2] = round(((note[2]/13.75)-12)*13.75,3)
                                note[4] = round(((note[4]/13.75)-12)*13.75,3)
                                note[3] = round(note[4]-note[2],3)
                        elif shiftVotes[0] > shiftVotes[1]:
                            for note in currentPhrase:
                                note[2] = round(((note[2]/13.75)+12)*13.75,3)
                                note[4] = round(((note[4]/13.75)+12)*13.75,3)
                                note[3] = round(note[4]-note[2],3)
                        notes += currentPhrase
                        currentPhrase = []
                        shiftVotes = [0,0,0,0]
                    continue
                if (message.type == "note_on" and message.velocity > 0):
                    if message.note < 47:
                        shiftVotes[0] += 1
                    elif message.note > 73:
                        shiftVotes[2] += 1
                    elif message.note < 59:
                        shiftVotes[3] += 1
                    elif message.note > 61:
                        shiftVotes[1] += 1
                    noteToUse = min(max(47, message.note),73)
                    lastNote = noteToUse
                    if (lastNoteOffBeat == currentBeat2): noteHeld = True
                    try:
                        glissyHints[currBeat]
                        noteHeld = True
                    except:
                        pass
                    # Truncate previous note if this next note is a little too close
                    try:
                        spacing = currentBeat2 - (currentPhrase[-1][1] + currentPhrase[-1][0])
                        if (not noteHeld and spacing < defaultSpacing):
                            currentPhrase[-1][1] = round(min(max(defaultLength, currentPhrase[-1][1] - (defaultSpacing - spacing)), currentPhrase[-1][1]), 3)
                    except:
                        pass
                    if (not noteHeld):
                        #No notes being held, so we set it up
                        currentNote = SetupNote(currentBeat2, 0, noteToUse, noteToUse)
                        heldNoteChannel = message.channel
                    else:
                        #If we are holding one, we add the previous note we set up, and set up a new one
                        log.debug("Cancelling Previous note! " + str(currentBeat2) + " old is " + str(currentNote[0]))
                        # if currentNote has a length, that means that the previous note was already terminated
                        # and this is a special condition to force a glissando
                        if (currentNote[1] > defaultLength * 2):
                            currentPhrase.pop()
                            # it looks better if the slide starts in the middle of the previous note
                            # but this isn't always best if the note is too short
                            currentNote[1] = round(max(defaultLength,currentNote[1] / 2),3)
                            currentPhrase += [currentNote]
                            currentNote = [round(currentNote[0] + currentNote[1], 3),0,currentNote[2],0,0]
                        elif (currentNote[1] > 0):
                            # remove previous note, new note becomes a slide
                            currentPhrase.pop()
                        currentNote[1] = round(currentBeat2-currentNote[0],3)
                        currentNote[4] = (noteToUse-60)*13.75
                        currentNote[3] = currentNote[4]-currentNote[2]

                        for noteParam in range(len(currentNote)):
                                currentNote[noteParam] = round(currentNote[noteParam],3)
                        if (currentNote[1] == 0):
                                currentNote[1] = defaultLength
                        currentPhrase += [currentNote]
                        currentNote = SetupNote(currentBeat2, 0, noteToUse, noteToUse)
                    log.debug(str(currentNote))
                    noteHeld = True

                if (message.type == "note_off" or (message.type == "note_on" and message.velocity == 0)):
                    noteToUse = min(max(47, message.note),73)
                    lastNoteOffBeat = currentBeat2
                    # The original intention was to terminate the held note when there was a noteoff event on channel 0
                    # Other channels could be used for adding glissando. The issue is rock band charts frequently use
                    # channel 3. As a compromise, note is terminated when a noteoff on the original channel is found.
                    # This allows both to function as intended. And perhaps some people who accidentally use channel 1
                    # will have a bit less of a headache
                    if (message.channel == heldNoteChannel and noteToUse == lastNote and noteHeld):
                        currentNote[1] = round(currentBeat2-currentNote[0] - noteTrimming,3)
                        currentNote[4] = currentNote[4]
                        currentNote[3] = 0
                        for noteParam in range(len(currentNote)):
                            currentNote[noteParam] = round(currentNote[noteParam],3)
                        if (currentNote[1] <= 0):
                            currentNote[1] = defaultLength
                        #log.info(currentNote)
                        currentPhrase += [currentNote]
                        noteHeld = False

            final_bar = max(final_bar, currentBeat2)
            #log.info("totaltime: " + str(totaltime)+"s")

        if len(currentPhrase) > 0:
            notes += currentPhrase
        notes = sorted(notes, key=lambda x: x[0] )

        if len(notes) == 0 or len(lyricsOut) == 0:
            log.warning("No notes or lyrics in current file, skipping")
            continue

        dicc["notes"] = notes
        dicc["endpoint"]= int(final_bar+4)
        dicc["lyrics"]= lyricsOut
        dicc["UNK1"]= 0

        chartjson = json.dumps(dicc)

        csvdata = [dicc["name"].strip(','),
                    dicc["author"],
                    dicc["genre"],
                    str(dicc["difficulty"])]

        outdir = os.path.join("./_output", dicc["trackRef"])
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "song.tmb"),"w",encoding="utf-8") as file:
            print("Writing chart for song " + dicc["trackRef"])
            file.write(chartjson)
        # Initializing shit at the scope I need it and setting it to NULL is a habit from C++
        combinedAudio = None
        tempAudio = None
        print("Combining audio...")
        for entry in os.scandir(basepath):
            if entry.is_file() and entry.name[-4:].lower() == ".ogg":
                log.info("Combining ogg file " + entry.name)
                if combinedAudio == None:
                    combinedAudio = AudioSegment.from_ogg(entry.path)
                    combinedAudio = combinedAudio - 5
                else:
                    tempAudio = AudioSegment.from_ogg(entry.path)
                    tempAudio = tempAudio - 5
                    combinedAudio = combinedAudio.overlay(tempAudio)
        print("Writing combined song.ogg")
        combinedAudio.export(os.path.join(outdir,"song.ogg"), format="ogg")#, codec="libvorbis", bitrate="1441k")
        # Make a cool BG that fills the 1920x1080 space smartly
        print("Creating bg image")
        bg = Image.new("RGBA", (1920, 1080))
        with Image.open(os.path.join(basepath, "album.png")) as img1:
            h = round((img1.size[1]/img1.size[0]) * 2100)
            w = round((img1.size[0]/img1.size[1]) * 1080)
            img2 = img1.resize((2100,h))
            if img2.mode != "RGBA":
                img2 = img2.convert("RGBA")
            img2 = img2.filter(filter=ImageFilter.BoxBlur(radius=90))
            h2 = math.floor((h - 1080) / 2)
            bg.paste(img2.crop((90, h2, 1960, h - h2)))
            img2 = img1.resize((w,1080))
            if img2.mode not in ["RGB", "RGBA"]:
                img2 = img2.convert("RGBA")
            bg.paste(img2, (math.floor((1920 - w)/2),0))
        bg.save(os.path.join(outdir,"bg.png"), "PNG")
        with open("./_output/songlist.csv",'a') as f:
            f.write("\n" + ",".join(csvdata))

sys.exit()
