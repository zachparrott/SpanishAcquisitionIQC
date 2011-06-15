import logging

from devices.abstract_device import AbstractDevice
from devices.tools import Synchronized
from interface.resources import Resource

"""
Agilent 34410A Digital Multimeter

Obtain measurements from the multimeter.
"""


log = logging.getLogger(__name__)


class DM34410A(AbstractDevice):
	"""
	Interface for Agilent 34410A DM.

	Note: Currently supports only DC voltage readings.
	"""

	allowed_nplc = set([0.006, 0.02, 0.06, 0.2, 1, 2, 10, 100])
	allowed_auto_zero = set(['off', 'on', 'once'])

	def _setup(self):
		AbstractDevice._setup(self)

		# Resources.
		read_only = ['reading']
		for name in read_only:
			self.resources[name] = Resource(self, name)

		read_write = ['integration_time', 'auto_zero']
		for name in read_write:
			self.resources[name] = Resource(self, name, name)

		self.resources['integration_time'].converter = float
		self.resources['integration_time'].allowed_values = self.allowed_nplc
		self.resources['auto_zero'].allowed_values = self.allowed_auto_zero

	@Synchronized()
	def _connected(self):
		AbstractDevice._connected(self)

		self.reset()

		self.write('configure:voltage:dc')

	@Synchronized()
	def reset(self):
		"""
		Reset the device to its default state.
		"""

		log.info('Resetting "{0}".'.format(self.name))
		self.write('*rst')

	@property
	def integration_time(self):
		"""
		The integration time of the multimeter in terms of PLC.
		"""

		return float(self.ask('sense:voltage:dc:nplc?'))

	@integration_time.setter
	def integration_time(self, value):
		if value not in self.allowed_nplc:
			raise ValueError('Invalid NPLC value: {0}'.format(value))

		self.write('sense:voltage:dc:nplc {0}'.format(value))

	@property
	def auto_zero(self):
		"""
		The auto zero state.
		"""

		result = self.ask('sense:voltage:dc:zero:auto?')

		if result == '0':
			return 'off'
		elif result == '1':
			return 'on'

	@auto_zero.setter
	def auto_zero(self, value):
		if value not in self.allowed_auto_zero:
			raise ValueError('Invalid setting: {0}'.format(value))

		self.write('sense:voltage:dc:zero:auto {0}'.format(value))

	@property
	@Synchronized()
	def reading(self):
		"""
		The value measured by the device.
		"""

		log.debug('Getting DC voltage.')
		result = float(self.ask('read?'))
		log.debug('Got DC voltage: {0}'.format(result))

		return result


implementation = DM34410A


if __name__ == '__main__':
	import unittest

	from tests.server import test_dm34410a as my_server_tests

	unittest.main(module=my_server_tests)
