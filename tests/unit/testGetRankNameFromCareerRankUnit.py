import unittest
from src.ranks.ranks import get_rank_name

# Assuming your function and r_dict are in the same scope or imported
class TestGetRankName(unittest.TestCase):

    def test_rank_mapping(self):
        """Test representative values for various ranks."""
        self.assertEqual(get_rank_name(5002), 'Veteran X')
        self.assertEqual(get_rank_name(5000), 'Veteran X')
        self.assertEqual(get_rank_name(4999), 'Veteran IX')

        self.assertEqual(get_rank_name(4000), 'Veteran VIII')
        self.assertEqual(get_rank_name(400), 'Brigaadikindral')
        self.assertEqual(get_rank_name(23), 'Kapral IV')
        self.assertEqual(get_rank_name(2), 'Reamees')
        self.assertEqual(get_rank_name(1), 'Nekrut')

    def test_boundary_values(self):
        """Test the minimum and maximum boundaries for specific ranks."""
        self.assertEqual(get_rank_name(25), 'Seersant')
        self.assertEqual(get_rank_name(44), 'Veebel V')

        self.assertEqual(get_rank_name(250), 'Major')
        self.assertEqual(get_rank_name(299), 'Major V')

    def test_out_of_bounds(self):
        """Ensure logic handles values outside the defined dictionary."""
        # Currently, your function returns None if no match is found
        self.assertIsNone(get_rank_name(0))

if __name__ == '__main__':
    unittest.main()