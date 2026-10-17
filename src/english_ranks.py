# Career rank point ranges, keyed by base English rank name.
#
# Each base rank maps to an ordered list of (tier_suffix, [min, max]) tuples.
# tier_suffix is '' for a rank's lowest/base tier (no numeral shown in the
# role name), otherwise a Roman numeral ('V' is highest).
#
# Order matters, both the dict itself and each tier list: everything must
# stay descending by points (highest first) — ranks.py builds r_dict
# directly from this order, and role removal logic relies on it.
EN_RANK_TIERS = {
    'Veteran': [
        ('X', [5000, 5000]),
        ('IX', [4500, 4999]),
        ('VIII', [4000, 4499]),
        ('VII', [3500, 3999]),
        ('VI', [3000, 3499]),
        ('V', [2500, 2999]),
        ('IV', [2000, 2499]),
        ('III', [1500, 1999]),
        ('II', [1000, 1499]),
        ('', [500, 999]),
    ],
    'General': [
        ('V', [490, 499]),
        ('IV', [480, 489]),
        ('III', [470, 479]),
        ('II', [460, 469]),
        ('', [450, 459]),
    ],
    'Brigadier': [
        ('V', [440, 449]),
        ('IV', [430, 439]),
        ('III', [420, 429]),
        ('II', [410, 419]),
        ('', [400, 409]),
    ],
    'Colonel': [
        ('V', [390, 399]),
        ('IV', [380, 389]),
        ('III', [370, 379]),
        ('II', [360, 369]),
        ('', [350, 359]),
    ],
    'Lieutenant Colonel': [
        ('V', [340, 349]),
        ('IV', [330, 339]),
        ('III', [320, 329]),
        ('II', [310, 319]),
        ('', [300, 309]),
    ],
    'Major': [
        ('V', [290, 299]),
        ('IV', [280, 289]),
        ('III', [270, 279]),
        ('II', [260, 269]),
        ('', [250, 259]),
    ],
    'Captain': [
        ('V', [240, 249]),
        ('IV', [230, 239]),
        ('III', [220, 229]),
        ('II', [210, 219]),
        ('', [200, 209]),
    ],
    'First Lieutenant': [
        ('V', [190, 199]),
        ('IV', [180, 189]),
        ('III', [170, 179]),
        ('II', [160, 169]),
        ('', [150, 159]),
    ],
    'Second Lieutenant': [
        ('V', [140, 149]),
        ('IV', [130, 139]),
        ('III', [120, 129]),
        ('II', [110, 119]),
        ('', [100, 109]),
    ],
    'Chief Warrant Officer': [
        ('IV', [95, 99]),
        ('III', [90, 94]),
        ('II', [85, 89]),
        ('', [80, 84]),
    ],
    'Senior Warrant Officer': [
        ('III', [75, 79]),
        ('II', [70, 74]),
        ('', [65, 69]),
    ],
    'Warrant Officer': [
        ('III', [60, 64]),
        ('II', [55, 59]),
        ('', [50, 54]),
    ],
    'Sergeant Major': [
        ('V', [49, 49]),
        ('IV', [48, 48]),
        ('III', [47, 47]),
        ('II', [46, 46]),
        ('', [45, 45]),
    ],
    'Master Sergeant': [
        ('V', [44, 44]),
        ('IV', [43, 43]),
        ('III', [42, 42]),
        ('II', [41, 41]),
        ('', [40, 40]),
    ],
    'Sergeant First Class': [
        ('V', [39, 39]),
        ('IV', [38, 38]),
        ('III', [37, 37]),
        ('II', [36, 36]),
        ('', [35, 35]),
    ],
    'Staff Sergeant': [
        ('V', [34, 34]),
        ('IV', [33, 33]),
        ('III', [32, 32]),
        ('II', [31, 31]),
        ('', [30, 30]),
    ],
    'Sergeant': [
        ('V', [29, 29]),
        ('IV', [28, 28]),
        ('III', [27, 27]),
        ('II', [26, 26]),
        ('', [25, 25]),
    ],
    'Corporal': [
        ('V', [24, 24]),
        ('IV', [23, 23]),
        ('III', [22, 22]),
        ('II', [21, 21]),
        ('', [20, 20]),
    ],
    'Lance Corporal': [
        ('V', [19, 19]),
        ('IV', [18, 18]),
        ('III', [17, 17]),
        ('II', [16, 16]),
        ('', [15, 15]),
    ],
    'Private First Class': [
        ('V', [14, 14]),
        ('IV', [13, 13]),
        ('III', [12, 12]),
        ('II', [11, 11]),
        ('', [10, 10]),
    ],
    'Private Second Class': [
        ('V', [9, 9]),
        ('IV', [8, 8]),
        ('III', [7, 7]),
        ('II', [6, 6]),
        ('', [5, 5]),
    ],
    'Private': [
        ('III', [4, 4]),
        ('II', [3, 3]),
        ('', [2, 2]),
    ],
    'Recruit': [
        ('', [1, 1]),
    ],
}