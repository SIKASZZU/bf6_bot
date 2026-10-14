import unittest
from ranks import getRankNameFromCareerRank

# Assuming your function and r_dict are in the same scope or imported
class TestGetRankName(unittest.TestCase):

    def test_rank_mapping(self):
        """Test representative values for various ranks."""
        self.assertEqual(getRankNameFromCareerRank(5002), 'BF6 Veteran X')
        self.assertEqual(getRankNameFromCareerRank(5000), 'BF6 Veteran X')
        self.assertEqual(getRankNameFromCareerRank(4999), 'BF6 Veteran IX')

        self.assertEqual(getRankNameFromCareerRank(4000), 'BF6 Veteran VIII')
        self.assertEqual(getRankNameFromCareerRank(400), 'BF6 Brigaadikindral')
        self.assertEqual(getRankNameFromCareerRank(23), 'BF6 Kapral IV')
        self.assertEqual(getRankNameFromCareerRank(2), 'BF6 Reamees')
        self.assertEqual(getRankNameFromCareerRank(1), 'BF6 Nekrut')

    def test_boundary_values(self):
        """Test the minimum and maximum boundaries for specific ranks."""
        self.assertEqual(getRankNameFromCareerRank(25), 'BF6 Seersant')
        self.assertEqual(getRankNameFromCareerRank(44), 'BF6 Veebel V')

        self.assertEqual(getRankNameFromCareerRank(250), 'BF6 Major')
        self.assertEqual(getRankNameFromCareerRank(299), 'BF6 Major V')

    def test_out_of_bounds(self):
        """Ensure logic handles values outside the defined dictionary."""
        # Currently, your function returns None if no match is found
        self.assertIsNone(getRankNameFromCareerRank(0))

if __name__ == '__main__':
    unittest.main()