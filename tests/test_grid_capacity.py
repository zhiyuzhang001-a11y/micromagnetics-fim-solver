"""Capacity boundaries: no field evaluation or kernel creation."""
import os
import unittest
from unittest.mock import patch
from fimrun.capacity import geometry_capacity, require_memory
from fimrun.micromagnetics import Grid


class CapacityTests(unittest.TestCase):
    def test_user_and_larger_shapes(self):
        g = Grid(size=(500e-9,500e-9,3e-9), cell_size=(1e-9,1e-9,3e-9),
                 boundary='periodic_xy',mirrors=(10,10))
        self.assertEqual(g.cells,(500,500,1))
        self.assertEqual(geometry_capacity(1000,1000,True,(10,10))['cells'],1000000)
        self.assertEqual(geometry_capacity(500,500,False,fm=True)['fft_shape'],(1024,1024))

    def test_actual_index_and_displacement_limits(self):
        for n,p,m in [((50000,50000),True,(0,0)),((24000,24000),False,(0,0)),
                      ((60_000_000,3),True,(40,0)),((2**31-1,2**31-1),True,(0,0))]:
            with self.subTest(n=n), self.assertRaisesRegex(ValueError,'capacity'):
                geometry_capacity(*n,p,m)
        # An open FM grid may fit exact FiM padding but overflow power-of-two FFT.
        geometry_capacity(20000,16000,False)
        with self.assertRaisesRegex(ValueError,'Accelerate'):
            geometry_capacity(20000,16000,False,fm=True)

    def test_physics_and_integer_contracts_remain(self):
        for cells in [(500,500,2),(0,500,1),(True,500,1)]:
            with self.assertRaises(ValueError):
                Grid(cells=cells,cell_size=(1e-9,1e-9,3e-9))
        with self.assertRaisesRegex(ValueError,'integer multiple'):
            Grid(size=(500e-9,500e-9,3e-9),cell_size=(2.1e-9,2.1e-9,3e-9))
        with self.assertRaisesRegex(ValueError,'aspect'):
            Grid(cells=(500,500,1),cell_size=(.5e-9,.5e-9,3e-9))

    def test_explicit_budget_rejects_before_allocation(self):
        with patch.dict(os.environ,FIMRUN_MEMORY_BUDGET_BYTES='1024'):
            with self.assertRaisesRegex(MemoryError,'estimated working arrays'):
                require_memory(432096000,'test')
