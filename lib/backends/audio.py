# -*- coding: utf-8 -*-
import os, subprocess, wave, time, threading

import xbmc
from lib import util

class PlayerHandler:
	def setSpeed(self,speed): pass
	def player(self): return None
	def getOutFile(self): raise Exception('Not Implemented')
	def play(self): raise Exception('Not Implemented')
	def isPlaying(self): raise Exception('Not Implemented')
	def stop(self): raise Exception('Not Implemented')
	def close(self): raise Exception('Not Implemented')

class PlaySFXHandler(PlayerHandler):
	_xbmcHasStopSFX = hasattr(xbmc,'stopSFX')
	def __init__(self):
		self.outDir = os.path.join(xbmc.translatePath(util.xbmcaddon.Addon().getAddonInfo('profile')).decode('utf-8'),'playsfx_wavs')
		if not os.path.exists(self.outDir): os.makedirs(self.outDir)
		self.outFileBase = os.path.join(self.outDir,'speech%s.wav')
		self.outFile = ''
		self._isPlaying = False 
		self.event = threading.Event()
		self.event.clear()
		
	@staticmethod
	def hasStopSFX():
		return PlaySFXHandler._xbmcHasStopSFX
		
	def _nextOutFile(self):
		self.outFile = self.outFileBase % time.time()
		return self.outFile
		
	def player(self): return 'playSFX'
	
	def getOutFile(self):
		return self._nextOutFile()

	def play(self):
		if not os.path.exists(self.outFile):
			util.LOG('playSFXHandler.play() - Missing wav file')
			return
		self._isPlaying = True
		xbmc.playSFX(self.outFile)
		f = wave.open(self.outFile,'r')
		frames = f.getnframes()
		rate = f.getframerate()
		f.close()
		duration = frames / float(rate)
		self.event.clear()
		self.event.wait(duration)
		self._isPlaying = False
		
	def isPlaying(self):
		return self._isPlaying
		
	def stop(self):
		if self._xbmcHasStopSFX:
			self.event.set()
			xbmc.stopSFX()
		
	def close(self):
		for f in os.listdir(self.outDir):
			if f.startswith('.'): continue
			os.remove(os.path.join(self.outDir,f))

class CommandInfo:
	_advanced = False
	ID = 'info'
	name = 'Info'
	available = None
	play = None
	speed = None
	speedMultiplier = 1
	kill = False
	
	@classmethod
	def speedArg(cls,speed):
		return str(speed * cls.speedMultiplier)
		
	@classmethod
	def playArgs(cls,outFile,speed):
		args = []
		args.extend(cls.play)
		args[args.index(None)] = outFile
		return args
	
class AdvancedCommandInfo(CommandInfo):
	_advanced = True
	@classmethod
	def playArgs(cls,outFile,speed):
		args = []
		args.extend(cls.play)
		args[args.index(None)] = outFile
		if speed:
			args.extend(cls.speed)
			args[args.index(None)] = cls.speedArg(speed)
		return args

class aplay(CommandInfo):
	ID = 'aplay'
	name = 'aplay'
	available = ('aplay','--version')
	play = ('aplay','-q',None)

class paplay(CommandInfo):
	ID = 'paplay'
	name = 'paplay'
	available = ('paplay','--version')
	play = ('paplay',None)

class sox(AdvancedCommandInfo):
	ID = 'sox'
	name = 'SOX'
	available = ('sox','--version')
	play = ('play','-q',None)
	speed = ('tempo','-s',None)
	speedMultiplier = 0.01
	kill = True

class mplayer(AdvancedCommandInfo):
	ID = 'mplayer'
	name = 'MPlayer'
	available = ('mplayer','--help')
	play = ('mplayer','-really-quiet',None)
	speed = ('-af','scaletempo','-speed',None)
	speedMultiplier = 0.01

class ExternalPlayerHandler(PlayerHandler):
	players = None
	def __init__(self,preferred=None,advanced=False):
		outDir = os.path.join(xbmc.translatePath(util.xbmcaddon.Addon().getAddonInfo('profile')).decode('utf-8'),'playsfx_wavs')
		if not os.path.exists(outDir): os.makedirs(outDir)
		self.outFile = os.path.join(outDir,'speech.wav')
		self._wavProcess = None
		self._player = False
		self.speed = 0
		self.active = True
		self.hasAdvancedPlayer = False
		self.getAvailablePlayers()
		self.setPlayer(preferred,advanced)
			
	def getCommandInfoByID(self,ID):
		for i in self.availablePlayers:
			if i.ID == ID: return i
		return None

	def player(self):
		return self._player and self._player.ID or None

	def playerAvailable(self):
		return bool(self.availablePlayers)
	
	def getAvailablePlayers(self):
		self.availablePlayers = []
		for p in self.players:
			try:
				subprocess.call(p.available)
				self.availablePlayers.append(p)
				if p._advanced: self.hasAdvancedPlayer = True
			except:
				pass
			
	def setPlayer(self,preferred=None,advanced=False):
		old = self._player
		if preferred: preferred = self.getCommandInfoByID(preferred)
		if preferred:
			self._player = preferred
		elif advanced and self.hasAdvancedPlayer:
			for p in self.availablePlayers:
				if p._advanced:
					self._player = p
					break
		elif self.availablePlayers:
			self._player = self.availablePlayers[0]
		else:
			self._player = None
			
		if self._player and old != self._player: util.LOG('External Player: %s' % self._player.name)
		return self._player
	
	def _deleteOutFile(self):
		if os.path.exists(self.outFile): os.remove(self.outFile)
		
	def getOutFile(self):
		return self.outFile
		
	def setSpeed(self,speed):
		self.speed = speed
		
	def play(self):
		self._wavProcess = subprocess.Popen(self._player.playArgs(self.outFile,self.speed))
		
		while self._wavProcess.poll() == None and self.active: xbmc.sleep(10)
		
	def isPlaying(self):
		return self._wavProcess and self._wavProcess.poll() == None

	def stop(self):
		if not self._wavProcess: return
		try:
			if self._player.kill:
				self._wavProcess.kill()
			else:
				self._wavProcess.terminate()
		except:
			pass
		
	def close(self):
		self.active = False
		if not self._wavProcess: return
		try:
			self._wavProcess.kill()
		except:
			pass

class UnixExternalPlayerHandler(ExternalPlayerHandler):
	players = (aplay,paplay,sox,mplayer)
	
class WavPlayer:
	def __init__(self,external_handler=None,preferred=None,advanced=False):
		self.handler = None
		self.preferred = preferred
		self.advanced = advanced
		self.externalHandler = external_handler
		self.setPlayer(preferred)
		
	def initPlayer(self):
		if not self.usePlaySFX():
			util.LOG('stopSFX not available')
			self.useExternalPlayer()

	def usePlaySFX(self):
		if PlaySFXHandler.hasStopSFX():
			util.LOG('stopSFX available - Using xbmcPlay()')
			self.handler = PlaySFXHandler()
			return True
		return False

	def useExternalPlayer(self):
		external = None
		if self.externalHandler: external = self.externalHandler(advanced=self.advanced)
		if external and external.playerAvailable():
			self.handler = external
			util.LOG('Using external player')
		else:
			self.handler = PlaySFXHandler()
			util.LOG('No external player - falling back to playSFX()')
		
	def setPlayer(self,preferred=None):
		self.preferred = preferred
		if self.handler and preferred == self.handler.player(): return 
		if preferred and self.externalHandler:
			external = self.externalHandler(preferred,self.advanced)
			if external.player() == preferred:
				self.handler = external
				return
		self.initPlayer()
	
	def setSpeed(self,speed):
		return self.handler.setSpeed(speed)
		
	def getOutFile(self):
		return self.handler.getOutFile()
			
	def play(self):
		return self.handler.play()
		
	def isPlaying(self):
		return self.handler.isPlaying()

	def stop(self):
		return self.handler.stop()
		
	def close(self):
		return self.handler.close()