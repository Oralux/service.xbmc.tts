# -*- coding: utf-8 -*-
import xbmc, time, threading, Queue
from lib import util
import audio

class TTSBackendBase:
	"""The base class for all speech engine backends
		
	Subclasses must at least implement the say() method, and can use whatever
	means are available to speak text.
	"""
	provider = 'auto'
	displayName = 'Auto'
	pauseInsert = u'...'
	extras = None
	interval = 400
	broken = False
	
	def say(self,text,interrupt=False):
		"""Method accepting text to be spoken
		
		Must be overridden by subclasses.
		text is unicode and the text to be spoken.
		If interrupt is True, the subclass should interrupt all previous speech.
		
		"""
		raise Exception('Not Implemented')

	def sayList(self,texts,interrupt=False):
		"""Accepts a list of text strings to be spoken
		
		May be overriden by subclasses. The default implementation calls say()
		for each item in texts, calling insertPause() between each.
		If interrupt is True, the subclass should interrupt all previous speech.
		"""
		self.say(texts.pop(0),interrupt=interrupt)
		for t in texts:
			self.insertPause()
			self.say(t)
		
	def voices(self):
		"""Returns a list of voice string names
		
		May be overridden by subclasses. Default implementation returns None.
		"""
		return None
	
	def userVoice(self):
		"""Returns a user saved voice name
		"""
		self._voice = util.getSetting('voice.{0}'.format(self.provider),'')
		return self._voice
		
	def userSpeed(self):
		"""Returns a user saved speed integer
		"""
		self._speed = util.getSetting('speed.{0}'.format(self.provider),0)
		return self._speed

	def userExtra(self,extra,default=None):
		"""Returns a user saved extra setting named key, or default if not set
		"""
		setattr(self,extra,util.getSetting('{0}.{1}'.format(extra,self.provider),default))
		return getattr(self,extra)
		
	def insertPause(self,ms=500):
		"""Insert a pause of ms milliseconds
		
		May be overridden by sublcasses. Default implementation sleeps for ms.
		"""
		xbmc.sleep(ms)
	
	def isSpeaking(self):
		"""Returns True if speech engine is currently speaking, False if not 
		and None if unknown
		
		Subclasses should override this respond accordingly
		"""
		return None
		
	def update(self,voice_name,speed):
		"""Called when the user has changed voice or speed
		
		Voice will be the new voice name or None if not changed.
		Speed will be the speed integer on None if not changed.
		Subclasses should override this to react to user changes.
		"""
		pass
	
	def stop(self):
		"""Stop all speech, implicitly called when close() is called
		
		Subclasses shoud override this to respond to requests to stop speech.
		Default implementation does nothing.
		"""
		pass
	
	def close(self):
		"""Close the speech engine
		
		Subclasses shoud override this to clean up after themselves.
		Default implementation does nothing.
		"""
		pass
	
	def _update(self):
		voice = self._updateVoice()
		speed = self._updateSpeed()
		extras = self._updateExtras()
		if voice or speed or extras: self.update(voice,speed)
		
	def _updateVoice(self):
		old = hasattr(self,'_voice') and self._voice or None
		voice = self.userVoice()
		if old != None:
			if voice == old: return None
		else:
			return None
		return voice
		
	def _updateSpeed(self):
		old = hasattr(self,'_speed') and self._speed or None
		speed = self.userSpeed()
		if old != None:
			if speed == old: return None
		else:
			return None
		return speed
			
	def _updateExtras(self):
		if not self.extras: return False
		for (extra,default) in self.extras:
			old = None
			if hasattr(self, extra): old = getattr(self,extra)
			new = self.userExtra(extra,default)
			if old != None and new != old: return True
		return False
		
	def _stop(self):
		self.stop()
	
	def _close(self):
		self._stop()
		self.close()

	@classmethod
	def _available(cls):
		if cls.broken and util.getSetting('disable_broken_backends',True): return False
		return cls.available()
		
	@staticmethod
	def available():
		"""Static method representing the the speech engines availability
		
		Subclasses should override this and return True if the speech engine is
		capable of speaking text in the current environment.
		Default implementation returns False.
		"""
		return False

class ThreadedTTSBackend(TTSBackendBase):
	"""A threaded speech engine backend
		
	Handles all the threading mechanics internally.
	Subclasses must at least implement the threadedSay() method, and can use
	whatever means are available to speak text.
	They say() and sayList() and insertPause() methods are not meant to be overridden.
	"""
	
	def __init__(self):
		self.threadedInit()
		
	def threadedInit(self):
		"""Initialize threading
		
		Must be called if you override the __init__() method
		"""
		self.active = True
		self._threadedIsSpeaking = False
		self.queue = Queue.Queue()
		self.thread = threading.Thread(target=self._handleQueue,name='TTSThread: %s' % self.provider)
		self.thread.start()
		
	def _handleQueue(self):
		util.LOG('Threaded TTS Started: {0}'.format(self.provider))
		while self.active and not xbmc.abortRequested:
			try:
				text = self.queue.get(timeout=0.5)
				self.queue.task_done()
				if isinstance(text,int):
					time.sleep(text/1000.0)
				else:
					self._threadedIsSpeaking = True
					self.threadedSay(text)
					self._threadedIsSpeaking = False
			except Queue.Empty:
				pass
		util.LOG('Threaded TTS Finished: {0}'.format(self.provider))
			
	def _emptyQueue(self):
		try:
			while True:
				self.queue.get_nowait()
				self.queue.task_done()
		except Queue.Empty:
			return
			
	def say(self,text,interrupt=False):
		if not self.active: return
		if interrupt: self._stop()
		self.queue.put_nowait(text)
		
	def sayList(self,texts,interrupt=False):
		if interrupt: self._stop()
		self.queue.put_nowait(texts.pop(0))
		for t in texts: 
			self.insertPause()
			self.queue.put_nowait(t)
		
	def isSpeaking(self):
		return self._threadedIsSpeaking or not self.queue.empty()
		
	def _stop(self):
		self._emptyQueue()
		TTSBackendBase._stop(self)

	def insertPause(self,ms=500):
		self.queue.put(ms)
	
	def threadedSay(self,text):
		"""Method accepting text to be spoken
		
		Subclasses must override this method and should speak the unicode text.
		Speech interruption is implemented in the stop() method.
		"""
		raise Exception('Not Implemented')
		
	def _close(self):
		self.active = False
		TTSBackendBase._close(self)
		self._emptyQueue()
			
class SimpleTTSBackendBase(ThreadedTTSBackend):
	WAVOUT = 0
	ENGINESPEAK = 1
	"""Handles speech engines that output wav files

	Subclasses must at least implement the runCommand() method which should
	save a wav file to outFile and/or the runCommandAndSpeak() method which
	must play the speech directly.
	"""
	def __init__(self,player=None,mode=WAVOUT):
		self._simpleIsSpeaking = False
		self.setMode(mode)
		self.player = player or audio.WavPlayer()
		self.threadedInit()

	def setMode(self,mode):
		assert isinstance(mode,int), 'Bad mode'
		self.mode = mode
		if mode == self.WAVOUT:
			util.LOG('Mode: WAVOUT')
		else:
			util.LOG('Mode: ENGINESPEAK')

	def setPlayer(self,preferred):
		self.player.setPlayer(preferred)
	 
	def setSpeed(self,speed):
		self.player.setSpeed(speed)
		
	def runCommand(text,outFile):
		"""Convert text to speech and output to a .wav file
		
		If using WAVOUT mode, subclasses must override this method
		and output a .wav file to outFile.
		"""
		raise Exception('Not Implemented')
		
	def runCommandAndSpeak(self,text):
		"""Convert text to speech and output to a .wav file
		
		If using ENGINESPEAK mode, subclasses must override this method
		and speak text.
		"""
		raise Exception('Not Implemented')
	
	def threadedSay(self,text):
		if not text: return
		if self.mode == self.WAVOUT:
			outFile = self.player.getOutFile()
			self.runCommand(text,outFile)
			self.player.play()
		else:
			self._simpleIsSpeaking = True
			self.runCommandAndSpeak(text)
			self._simpleIsSpeaking = False

	def isSpeaking(self):
		return self._simpleIsSpeaking or self.player.isPlaying() or ThreadedTTSBackend.isSpeaking(self)
		
	def _stop(self):
		self.player.stop()
		ThreadedTTSBackend._stop(self)
		
	def _close(self):
		ThreadedTTSBackend._close(self)
		self.player.close()

class LogOnlyTTSBackend(TTSBackendBase):
	provider = 'log'
	displayName = 'Log'
	def say(self,text,interrupt=False):
		util.LOG('say(Interrupt={1}): {0}'.format(repr(text),interrupt))
		
	@staticmethod
	def available():
		return True
