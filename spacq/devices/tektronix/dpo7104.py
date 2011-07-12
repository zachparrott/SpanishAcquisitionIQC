import logging
log = logging.getLogger(__name__)

from math import ceil
import struct

from spacq.interface.resources import Resource
from spacq.tool.box import Synchronized

from ..abstract_device import AbstractDevice, AbstractSubdevice
from ..tools import BlockData, str_to_bool

"""
Tektronix DPO7104 Digital Phosphor Oscilloscope

Control the DPO's settings and input waveforms.
"""


class Channel(AbstractSubdevice):
	"""
	Input channel of the DPO.
	"""

	def _setup(self):
		AbstractSubdevice._setup(self)

		# Resources.
		read_only = ['waveform']
		for name in read_only:
			self.resources[name] = Resource(self, name, name)

		read_write = ['enabled']
		for name in read_write:
			self.resources[name] = Resource(self, name, name)

		self.resources['enabled'].converter = str_to_bool

	def __init__(self, device, channel, *args, **kwargs):
		self.channel = channel

		AbstractSubdevice.__init__(self, device, *args, **kwargs)

	def normalize_waveform(self, waveform):
		"""
		Transform some curve data onto the amplitude interval [-1.0, 1.0].
		"""

		value_min, value_max = self.device.value_range
		value_diff = value_max - value_min

		return [2 * float(x - value_min) / value_diff - 1.0 for x in waveform]

	@property
	def enabled(self):
		"""
		The input state (on/off) of the channel.
		"""

		result = self.device.ask('select:ch{0}?'.format(self.channel))
		return bool(int(result))

	@enabled.setter
	def enabled(self, value):
		self.device.write('select:ch{0} {1}'.format(self.channel, 'on' if value else 'off'))

	@property
	@Synchronized()
	def waveform(self):
		"""
		A waveform acquired by the scope.
		"""

		self.device.data_source = self.channel

		# Receive in chunks.
		num_data_points = self.device.record_length
		num_transmissions = int(ceil(num_data_points / self.device.max_receive_samples))

		curve = []
		for i in xrange(num_transmissions):
			self.device.data_start = int(i * self.device.max_receive_samples) + 1
			self.device.data_stop = int((i + 1) * self.device.max_receive_samples)

			curve_raw = self.device.ask_raw('curve?')
			curve.append(BlockData.from_block_data(curve_raw))

		curve = ''.join(curve)

		format_code = self.device.byte_format_letters[self.device.waveform_bytes]
		curve_data = struct.unpack('!{0}{1}'.format(num_data_points, format_code), curve)

		return self.normalize_waveform(curve_data)


class DPO7104(AbstractDevice):
	"""
	Interface for Tektronix DPO7104 DPO.
	"""

	byte_format_letters = [None, 'b', 'h']

	# The upper limit to the number of samples to be received per transmission.
	max_receive_samples = 1e7

	allowed_stopafters = ['runstop', 'sequence']
	allowed_waveform_bytes = [1, 2] # Channel data only.

	def _setup(self):
		AbstractDevice._setup(self)

		self.channels = [None] # There is no channel 0.
		for chan in xrange(1, 5):
			channel = Channel(self, chan)
			self.channels.append(channel)
			self.subdevices['channel{0}'.format(chan)] = channel

		# Resources.
		read_only = ['value_range']
		for name in read_only:
			self.resources[name] = Resource(self, name)

		read_write = ['stopafter', 'waveform_bytes', 'sample_rate', 'horizontal_scale', 'acquiring']
		for name in read_write:
			self.resources[name] = Resource(self, name, name)

		self.resources['stopafter'].allowed_values = self.allowed_stopafters
		self.resources['waveform_bytes'].allowed_values = self.allowed_waveform_bytes
		self.resources['waveform_bytes'].converter = int
		self.resources['sample_rate'].converter = float
		self.resources['horizontal_scale'].converter = float
		self.resources['acquiring'].converter = str_to_bool

	def _connected(self):
		AbstractDevice._connected(self)

		self.reset()
		self.autoset()

		self.stopafter = 'sequence'

	@Synchronized()
	def reset(self):
		"""
		Reset the device to its default state.
		"""

		log.info('Resetting "{0}".'.format(self.name))
		self.write('*rst')

	def autoset(self):
		"""
		Autoset the scaling.
		"""

		self.write('autoset execute')

	@property
	def stopafter(self):
		"""
		The acqusition mode.
		"""

		value = self.ask('acquire:stopafter?')

		if value == 'RUNST':
			return 'runstop'
		elif value == 'SEQ':
			return 'sequence'

	@stopafter.setter
	def stopafter(self, value):
		if value not in self.allowed_stopafters:
			raise ValueError('Invalid acquisition mode: {0}'.format(value))

		self.write('acquire:stopafter {0}'.format(value))

	@property
	def waveform_bytes(self):
		"""
		Number of bytes per data point in the acquired waveforms.
		"""

		return int(self.ask('wfmoutpre:byt_nr?'))

	@waveform_bytes.setter
	def waveform_bytes(self, value):
		self.write('wfmoutpre:byt_nr {0}'.format(value))

	@property
	def value_range(self):
		"""
		Range of values possible for each data point.
		"""

		# The returned values are signed.
		bits = 8 * self.waveform_bytes - 1
		max_val = 2 ** bits

		return (-max_val, max_val - 1)

	@property
	def acquiring(self):
		"""
		Whether the device is currently acquiring data.
		"""

		result = self.ask('acquire:state?')
		return bool(int(result))

	@acquiring.setter
	def acquiring(self, value):
		self.write('acquire:state {0}'.format(str(int(value))))

	@property
	def sample_rate(self):
		"""
		The sample rate in s-1.
		"""

		return float(self.ask('horizontal:mode:samplerate?'))

	@sample_rate.setter
	def sample_rate(self, value):
		self.write('horizontal:mode:samplerate {0}'.format(value))

	@property
	def horizontal_scale(self):
		"""
		The horizontal time scale for each division in s.

		Note: There are 10 divisions, so a waveform will be 10 times as long.
		"""

		return float(self.ask('horizontal:mode:scale?'))

	@horizontal_scale.setter
	def horizontal_scale(self, value):
		self.write('horizontal:mode:scale {0}'.format(value))

	@property
	def data_source(self):
		"""
		The source from which to transfer data.
		"""

		result = self.ask('data:source?')
		assert len(result) == 3 and result.startswith('CH')

		return int(result[2])

	@data_source.setter
	def data_source(self, value):
		self.write('data:source ch{0}'.format(value))

	@property
	def data_start(self):
		"""
		The first data point to transfer.
		"""

		return int(self.ask('data:start?'))

	@data_start.setter
	def data_start(self, value):
		self.write('data:start {0}'.format(value))

	@property
	def data_stop(self):
		"""
		The last data point to transfer.
		"""

		return int(self.ask('data:stop?'))

	@data_stop.setter
	def data_stop(self, value):
		self.write('data:stop {0}'.format(value))

	@property
	def record_length(self):
		"""
		The number of data points in a waveform.
		"""

		return int(self.ask('horizontal:mode:recordlength?'))

	@Synchronized()
	def acquire(self):
		"""
		Cause the DPO to acquire a single waveform.
		"""

		self.acquiring = True
		self.opc


name = 'DPO7104'
implementation = DPO7104