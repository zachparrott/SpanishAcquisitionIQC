from nose.tools import assert_raises, eq_
from numpy.testing import assert_array_almost_equal
from os import path
from unittest import main, TestCase

from ...units import Quantity
from ..parser import Parser

from .. import tree


resource_dir = path.join(path.dirname(__file__), 'resources')


class ValidTreeTest(TestCase):
	prog = Parser()("""
		int repeat = 2
		delay abc1 = 100 ns, def2
		pulse ghi1, jkl2 = {{shape: 'square'}}
		output mno1, pqr2

		ghi1.shape = '{0}'
		ghi1.length = 8 ns
		ghi1.amplitude = 1 mV

		abc1
		(10 ns):pqr2

		times repeat {{
			def2
			ghi1:mno1
			(ghi1 abc1 10 ns jkl2):mno1 (def2 jkl2 def2):pqr2
		}}

		acquire

		5 ns
	""".format(path.join(resource_dir, 'non-square')))

	def testDeclarations(self):
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(self.prog, env)

		expected = {
			'_acq_marker': 'acq_marker',
			'abc1': 'delay',
			'def2': 'delay',
			'ghi1': 'pulse',
			'jkl2': 'pulse',
			'mno1': 'output',
			'pqr2': 'output',
			'repeat': 'int',
		}

		eq_(env.errors, [])
		eq_(env.variables, expected)

	def testValues(self):
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(self.prog, env)

		env.stage = env.stages.values
		tree.traverse_tree(self.prog, env)

		expected = {
			('abc1',): Quantity('100 ns'),
			('ghi1', 'amplitude'): Quantity(1, 'mV'),
			('ghi1', 'length'): Quantity(8, 'ns'),
			('ghi1', 'shape'): path.join(resource_dir, 'non-square'),
			('jkl2', 'shape'): 'square',
			('repeat',): 2,
		}

		missing = set([('_acq_marker', 'num'), ('_acq_marker', 'output'), ('def2',),
				('jkl2', 'amplitude'), ('jkl2', 'length')])

		eq_(env.errors, [])
		eq_(env.values, expected)
		eq_(env.missing_values, missing)

		# Later additions (perhaps from the UI).
		updates = {
			('_acq_marker', 'num'): 1,
			('_acq_marker', 'output'): 'mno1',
			('def2',): Quantity('7 ns'),
			('jkl2', 'amplitude'): Quantity(1, 'V'),
			('jkl2', 'length'): Quantity(50, 'ns'),
		}

		for name, value in updates.items():
			env.set_value(name, value)

		expected.update(updates)

		eq_(env.errors, [])
		eq_(env.values, expected)

	def testCommands(self):
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(self.prog, env)

		env.stage = env.stages.commands
		tree.traverse_tree(self.prog, env)

		eq_(env.errors, [])
		assert env.acquisition

	def testWaveforms(self):
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(self.prog, env)

		env.stage = env.stages.values
		tree.traverse_tree(self.prog, env)

		env.stage = env.stages.commands
		tree.traverse_tree(self.prog, env)

		updates = {
			('_acq_marker', 'num'): 1,
			('_acq_marker', 'output'): 'mno1',
			('def2',): Quantity(7, 'ns'),
			('jkl2', 'amplitude'): Quantity(1, 'V'),
			('jkl2', 'length'): Quantity(50, 'ns'),
		}

		for name, value in updates.items():
			env.set_value(name, value)

		env.stage = env.stages.waveforms
		tree.traverse_tree(self.prog, env)

		eq_(env.errors, [])

		mno1 = env.waveforms['mno1']
		non_square = [0.0001, 0.0005, 0.0007, 0.001] + [0.0042] * 3 + [0.0036, 0.0099]
		loop = [0.0] * 7 + non_square * 2 + [0.0] * 108 + [1.0] * 50 + [0.0]
		assert_array_almost_equal(mno1.wave, [0.0] * 110 + loop * 2 + [0.0] * 5, 2)

		eq_(mno1.get_marker(1), [False] * 478 + [True] * 5)
		eq_(mno1.get_marker(2), [False] * 483)

		pqr2 = env.waveforms['pqr2']
		loop = [0.0] * 22 + [1.0] * 50 + [0.0] * 112
		assert_array_almost_equal(pqr2.wave, [0.0] * 110 + loop * 2 + [0.0] * 5, 2)


class InvalidTreeTest(TestCase):
	def testDeclarations(self):
		prog = Parser()("""
			int repeat = 2
			delay abc1 = 100 ns, def2
			pulse ghi1, jkl2 = {shape: 'square'}
			output mno1, pqr2

			delay abc1, def2 = 10 ms, stu3

			vwx4

			times 5 {
				int x = 9
			}
		""")

		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(prog, env)

		expected_errors = ['Re-decl'] * 2 + ['Declara']

		eq_(len(env.errors), len(expected_errors))

		for error, expected_error in zip(env.errors, expected_errors):
			assert error[0].startswith(expected_error), error

	def testValues(self):
		prog = Parser()("""
			int repeat = 2
			delay abc1 = 100 ns, def2
			pulse ghi1, jkl2 = {shape: 'square'}
			output mno1, pqr2

			delay abc1 = 50 ms, def2
			mno1 = "test"
			def2 = 6 ; def2 = 6 Hz
			ghi1 = 0
			ghi1.shape = 50 ms
			jkl2.amplitude = 8
			jkl2.length = 1234 A
			repeat = 6 s
			repeat = 2.0
			zzz1 = 5 ms
			zzz1.foo = 5 ms
			ghi1.something_else = 5

			times 5 {
				int x = 9
				y = 10
			}
		""")

		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(prog, env)

		env.errors = []
		env.stage = env.stages.values
		tree.traverse_tree(prog, env)

		expected_errors = (['Re-assi'] + ['Cannot a'] + ['Must assi'] * 8 + ['Undecla'] * 2 +
				['Assig'] + ['Undecla'] + ['Unrec'])

		eq_(len(env.errors), len(expected_errors))

		for error, expected_error in zip(env.errors, expected_errors):
			assert error[0].startswith(expected_error), (error, expected_error)

		assert_raises(KeyError, env.set_value, ('xyz',), 'zyx')

	def testCommands(self):
		prog = Parser()("""
			int repeat = 2
			delay abc1 = 100 ns, def2
			pulse ghi1, jkl2 = {shape: 'square'}
			output mno1, pqr2

			abc1
			(10 ns):pqr2

			times repeat {
				def2
				ghi1:mno1
				(ghi1 abc1 10 ns jkl2):mno1 (def2 jkl2 def2):pqr2

				acquire
				mno1
			}

			acquire

			times ghi1 {}

			acquire

			5 ns
			1 A
		""")
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(prog, env)

		env.errors = []
		env.stage = env.stages.commands
		tree.traverse_tree(prog, env)

		expected_errors = ['Not a d'] + ['Repeate'] + ['Repeti'] + ['Repeate'] + ['Delay mu']

		eq_(len(env.errors), len(expected_errors))

		for error, expected_error in zip(env.errors, expected_errors):
			assert error[0].startswith(expected_error), (error, expected_error)

	def testWaveforms(self):
		prog = Parser()("""
			delay d1

			d1
		""")
		env = tree.Environment()

		env.stage = env.stages.declarations
		tree.traverse_tree(prog, env)

		env.stage = env.stages.values
		tree.traverse_tree(prog, env)

		env.stage = env.stages.commands
		tree.traverse_tree(prog, env)

		env.errors = []
		env.stage = env.stages.waveforms

		assert_raises(ValueError, tree.traverse_tree, prog, env)


if __name__ == '__main__':
	main()
