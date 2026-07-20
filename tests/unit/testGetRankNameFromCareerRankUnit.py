import unittest
from ranks import getRankNameFromCareerRank

# Assuming your function and r_dict are in the same scope or imported
class TestGetRankName(unittest.TestCase):

    def test_rank_mapping(self):
        """Test representative values for various ranks."""
        self.assertEqual(getRankNameFromCareerRank(4000), 'Vanemveteran')
        self.assertEqual(getRankNameFromCareerRank(400), 'Brigadir')
        self.assertEqual(getRankNameFromCareerRank(23), 'Kapral')
        self.assertEqual(getRankNameFromCareerRank(1), 'Reamees')

    def test_boundary_values(self):
        """Test the minimum and maximum boundaries for specific ranks."""
        # Testing 'Seersant' (25-44)
        self.assertEqual(getRankNameFromCareerRank(25), 'Seersant')
        self.assertEqual(getRankNameFromCareerRank(44), 'Seersant')
        
        # Testing 'Major' (250-299)
        self.assertEqual(getRankNameFromCareerRank(250), 'Major')
        self.assertEqual(getRankNameFromCareerRank(299), 'Major')

    def test_out_of_bounds(self):
        """Ensure logic handles values outside the defined dictionary."""
        # Currently, your function returns None if no match is found
        self.assertIsNone(getRankNameFromCareerRank(0))
        self.assertIsNone(getRankNameFromCareerRank(6000))

if __name__ == '__main__':
    unittest.main()